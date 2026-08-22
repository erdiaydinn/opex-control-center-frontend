from __future__ import annotations

import base64
from datetime import UTC, datetime
import os
import unittest
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .operational_claim import (
    claim_operational_mission_signed,
    operational_claim_hash,
)
from .operational_recovery import operational_release_hash, release_operational_claim
from .production import InventoryPrincipal, connect
from .service import InventoryRuleError


class OperationalRuntimeContractTests(unittest.TestCase):
    def test_claim_hash_matches_android_golden_vector(self):
        self.assertEqual(
            operational_claim_hash(
                "11111111-1111-4111-8111-111111111111",
                "SHIFT-A",
            ),
            "4dcba75ca8d3ab0e9fde4a33ea20454c7f1370bc2b87893f5deb153525455a1d",
        )

    def test_release_hash_binds_mission_and_reason(self):
        mission = "11111111-1111-4111-8111-111111111111"
        first = operational_release_hash(mission, "stale shift claim")
        self.assertNotEqual(first, operational_release_hash(mission, "device incident"))
        self.assertEqual(len(first), 64)


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class OperationalRuntimePostgresTests(unittest.TestCase):
    @staticmethod
    def public_pem(private_key: ec.EllipticCurvePrivateKey) -> str:
        return private_key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    @staticmethod
    def proof(
        principal: InventoryPrincipal,
        private_key: ec.EllipticCurvePrivateKey,
        command_hash: str,
        *,
        nonce: str | None = None,
    ) -> tuple[str, str, str]:
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        request_nonce = nonce or str(uuid4())
        message = (
            f"{principal.device_id}\n{timestamp}\n{request_nonce}\n{command_hash}"
        ).encode()
        signature = base64.b64encode(
            private_key.sign(message, ec.ECDSA(hashes.SHA256()))
        ).decode()
        return timestamp, request_nonce, signature

    def setUp(self):
        self.tenant = os.getenv("INVENTORY_TEST_TENANT", "eay-inventory-ci")
        suffix = uuid4().hex[:12]
        self.mission_id = uuid4()
        self.owner_device = uuid4()
        self.supervisor_device = uuid4()
        self.owner_key = ec.generate_private_key(ec.SECP256R1())
        self.supervisor_key = ec.generate_private_key(ec.SECP256R1())
        self.owner = InventoryPrincipal(
            self.tenant,
            f"owner-{suffix}",
            f"EMP-OP-{suffix}",
            frozenset({"WH-1"}),
            self.owner_device,
        )
        self.supervisor = InventoryPrincipal(
            self.tenant,
            f"supervisor-{suffix}",
            f"EMP-SUP-{suffix}",
            frozenset({"WH-1"}),
            self.supervisor_device,
        )
        with connect() as db:
            for principal, key in (
                (self.owner, self.owner_key),
                (self.supervisor, self.supervisor_key),
            ):
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,
                         mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                    (
                        self.tenant,
                        principal.device_id,
                        principal.employee_id,
                        self.public_pem(key),
                        f"op-runtime-{uuid4()}",
                    ),
                )
            db.execute(
                """INSERT INTO inventory_operational_missions(
                     tenant_id,mission_id,warehouse_id,mission_type,operation,
                     external_reference,steps,state,created_by,intent_version,
                     sku_id,item_value_hash,planned_quantity,source_location_id,
                     destination_location_id,container_id,allowed_conditions
                   ) VALUES(
                     %s,%s,'WH-1','PICKING','inventory.pick.capture',%s,
                     '[\"SOURCE_LOCATION\",\"ITEM\",\"QUANTITY\",\"CONTAINER\",\"COMPLETE\"]'::jsonb,
                     'OPEN',%s,1,'SKU-1',%s,1,'A01',NULL,'TOTE-1','[]'::jsonb
                   )""",
                (
                    self.tenant,
                    self.mission_id,
                    f"ORDER-{suffix}",
                    self.owner.subject,
                    "a" * 64,
                ),
            )
            db.commit()

    def test_v9_guards_and_schema_contract_are_installed(self):
        with connect() as db:
            migration = db.execute(
                "SELECT name FROM inventory_schema_migrations WHERE version=9"
            ).fetchone()
            self.assertIsNotNone(migration)
            trigger_names = {
                row["tgname"]
                for row in db.execute(
                    """SELECT tgname FROM pg_trigger
                       WHERE tgname IN (
                         'inventory_operational_claim_v9_guard',
                         'inventory_operational_responses_immutable',
                         'inventory_device_operational_recovery_v9'
                       ) AND NOT tgisinternal"""
                ).fetchall()
            }
            self.assertEqual(
                trigger_names,
                {
                    "inventory_operational_claim_v9_guard",
                    "inventory_operational_responses_immutable",
                    "inventory_device_operational_recovery_v9",
                },
            )
            default = db.execute(
                """SELECT column_default FROM information_schema.columns
                   WHERE table_name='inventory_operational_missions'
                     AND column_name='allowed_conditions'"""
            ).fetchone()["column_default"]
            self.assertIn("[]", default)

    def test_signed_claim_consumes_nonce_and_exact_nonce_replay_fails_closed(self):
        command_hash = operational_claim_hash(self.mission_id, "SHIFT-A")
        nonce = str(uuid4())
        timestamp, _, signature = self.proof(
            self.owner,
            self.owner_key,
            command_hash,
            nonce=nonce,
        )
        claimed = claim_operational_mission_signed(
            self.owner,
            self.mission_id,
            "SHIFT-A",
            timestamp,
            nonce,
            signature,
        )
        self.assertEqual(claimed["state"], "CLAIMED")
        self.assertEqual(claimed["next_step"], "SOURCE_LOCATION")

        replay_timestamp, _, replay_signature = self.proof(
            self.owner,
            self.owner_key,
            command_hash,
            nonce=nonce,
        )
        with self.assertRaises(InventoryRuleError):
            claim_operational_mission_signed(
                self.owner,
                self.mission_id,
                "SHIFT-A",
                replay_timestamp,
                nonce,
                replay_signature,
            )

    def test_supervisor_release_reopens_without_rebinding_evidence(self):
        command_hash = operational_claim_hash(self.mission_id, "SHIFT-A")
        timestamp, nonce, signature = self.proof(self.owner, self.owner_key, command_hash)
        claimed = claim_operational_mission_signed(
            self.owner,
            self.mission_id,
            "SHIFT-A",
            timestamp,
            nonce,
            signature,
        )
        claim_id = claimed["claim_id"]

        reason = "shift ended before mission completion"
        release_hash = operational_release_hash(self.mission_id, reason)
        release_timestamp, release_nonce, release_signature = self.proof(
            self.supervisor,
            self.supervisor_key,
            release_hash,
        )
        released = release_operational_claim(
            self.supervisor,
            self.mission_id,
            reason,
            release_timestamp,
            release_nonce,
            release_signature,
        )
        self.assertFalse(released["idempotent"])
        self.assertEqual(released["state"], "OPEN")
        self.assertEqual(released["released_claim_id"], claim_id)
        self.assertEqual(released["evidence_policy"], "PRESERVE_NO_REBIND")

        with connect() as db:
            claim = db.execute(
                """SELECT released_at,release_reason,employee_id,device_id,shift_id
                   FROM inventory_operational_claims
                   WHERE tenant_id=%s AND claim_id=%s""",
                (self.tenant, claim_id),
            ).fetchone()
            mission = db.execute(
                """SELECT state FROM inventory_operational_missions
                   WHERE tenant_id=%s AND mission_id=%s""",
                (self.tenant, self.mission_id),
            ).fetchone()
            self.assertIsNotNone(claim["released_at"])
            self.assertTrue(claim["release_reason"].startswith("SUPERVISOR:"))
            self.assertEqual(claim["employee_id"], self.owner.employee_id)
            self.assertEqual(claim["device_id"], self.owner.device_id)
            self.assertEqual(claim["shift_id"], "SHIFT-A")
            self.assertEqual(mission["state"], "OPEN")

            with self.assertRaises(Exception):
                db.execute(
                    "DELETE FROM inventory_operational_claims WHERE tenant_id=%s AND claim_id=%s",
                    (self.tenant, claim_id),
                )
            db.rollback()

    def test_managed_device_replacement_releases_operational_claim_transactionally(self):
        command_hash = operational_claim_hash(self.mission_id, "SHIFT-A")
        timestamp, nonce, signature = self.proof(self.owner, self.owner_key, command_hash)
        claimed = claim_operational_mission_signed(
            self.owner,
            self.mission_id,
            "SHIFT-A",
            timestamp,
            nonce,
            signature,
        )
        claim_id = claimed["claim_id"]
        replacement_device = uuid4()
        with connect() as db:
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,
                     mdm_enrollment_hash,status
                   ) VALUES(%s,%s,%s,'TEST-KEY',%s,'ACTIVE')""",
                (
                    self.tenant,
                    replacement_device,
                    self.owner.employee_id,
                    f"replacement-{uuid4()}",
                ),
            )
            db.execute(
                """UPDATE inventory_devices
                   SET status='REPLACED',replaced_by=%s,revoked_at=now()
                   WHERE tenant_id=%s AND device_id=%s""",
                (replacement_device, self.tenant, self.owner.device_id),
            )
            db.commit()

        with connect() as db:
            claim = db.execute(
                """SELECT released_at,release_reason FROM inventory_operational_claims
                   WHERE tenant_id=%s AND claim_id=%s""",
                (self.tenant, claim_id),
            ).fetchone()
            mission = db.execute(
                """SELECT state FROM inventory_operational_missions
                   WHERE tenant_id=%s AND mission_id=%s""",
                (self.tenant, self.mission_id),
            ).fetchone()
            self.assertIsNotNone(claim["released_at"])
            self.assertEqual(claim["release_reason"], "DEVICE_REPLACED")
            self.assertEqual(mission["state"], "OPEN")
