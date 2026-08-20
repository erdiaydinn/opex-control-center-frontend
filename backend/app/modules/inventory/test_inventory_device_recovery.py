from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
import os
import unittest
from unittest.mock import patch
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .device_recovery import replace_managed_device
from .production import InventoryPrincipal, connect
from .service import InventoryRuleError


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryDeviceRecoveryPostgresTests(unittest.TestCase):
    @staticmethod
    def public_pem() -> str:
        key = ec.generate_private_key(ec.SECP256R1())
        return key.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def seed_replacement_case(self, *, replacement_scope=frozenset({"WH-1"})):
        tenant = os.getenv("INVENTORY_TEST_TENANT", f"device-recovery-{uuid4()}")
        employee_id = "EMP-RECOVERY"
        old_device_id = uuid4()
        new_device_id = uuid4()
        document_id = uuid4()
        old_attempt_id = uuid4()
        old_lease_id = uuid4()
        activation_code = f"replacement-{uuid4()}-{uuid4()}"
        pepper = f"pepper-{uuid4()}"
        activation_hash = hashlib.sha256(
            f"{pepper}:{activation_code}".encode()
        ).hexdigest()
        new_public_pem = self.public_pem()
        now = datetime.now(UTC)

        principal = InventoryPrincipal(
            tenant,
            "employee-subject",
            employee_id,
            replacement_scope,
            new_device_id,
        )

        with connect() as db:
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                (
                    tenant,
                    old_device_id,
                    employee_id,
                    self.public_pem(),
                    f"old-mdm-{uuid4()}",
                ),
            )
            db.execute(
                """INSERT INTO inventory_device_activation_codes(
                     tenant_id,activation_hash,employee_id,expires_at
                   ) VALUES(%s,%s,%s,%s)""",
                (
                    tenant,
                    activation_hash,
                    employee_id,
                    now + timedelta(minutes=15),
                ),
            )
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-1','Device replacement count','COUNTING','seed')""",
                (tenant, document_id),
            )
            db.execute(
                "INSERT INTO inventory_document_locations(tenant_id,document_id,location_id) VALUES(%s,%s,'A01')",
                (tenant, document_id),
            )
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,warehouse_id,location_id,
                     created_by_subject,created_by_employee_id,created_at
                   ) VALUES(%s,%s,%s,'WH-1','A01','seed',%s,%s)""",
                (tenant, old_attempt_id, document_id, employee_id, now - timedelta(minutes=5)),
            )
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until,issued_at
                   ) VALUES(%s,%s,%s,%s,%s,'SHIFT-RECOVERY','WH-1',%s,%s,%s)""",
                (
                    tenant,
                    old_lease_id,
                    old_attempt_id,
                    employee_id,
                    old_device_id,
                    now - timedelta(minutes=5),
                    now + timedelta(minutes=10),
                    now - timedelta(minutes=5),
                ),
            )
            db.commit()

        return {
            "tenant": tenant,
            "principal": principal,
            "old_device_id": old_device_id,
            "new_device_id": new_device_id,
            "document_id": document_id,
            "old_attempt_id": old_attempt_id,
            "old_lease_id": old_lease_id,
            "activation_code": activation_code,
            "pepper": pepper,
            "new_public_pem": new_public_pem,
        }

    def test_replacement_revokes_old_device_and_starts_clean_attempt(self):
        case = self.seed_replacement_case()
        with patch.dict(
            os.environ,
            {"INVENTORY_MDM_ACTIVATION_PEPPER": case["pepper"]},
            clear=False,
        ):
            result = replace_managed_device(
                case["principal"],
                case["old_device_id"],
                case["activation_code"],
                case["new_public_pem"],
            )
            replay = replace_managed_device(
                case["principal"],
                case["old_device_id"],
                case["activation_code"],
                case["new_public_pem"],
            )

        self.assertFalse(result["idempotent"])
        self.assertEqual(result["evidence_policy"], "PRESERVE_NO_REBIND")
        self.assertEqual(len(result["recovered_locations"]), 1)
        self.assertEqual(result["supervisor_reassignment_required"], [])
        self.assertTrue(replay["idempotent"])

        new_attempt_id = result["recovered_locations"][0]["new_attempt_id"]
        with connect() as db:
            old_device = db.execute(
                """SELECT status,replaced_by,revoked_at
                   FROM inventory_devices WHERE tenant_id=%s AND device_id=%s""",
                (case["tenant"], case["old_device_id"]),
            ).fetchone()
            new_device = db.execute(
                """SELECT status,employee_id
                   FROM inventory_devices WHERE tenant_id=%s AND device_id=%s""",
                (case["tenant"], case["new_device_id"]),
            ).fetchone()
            old_attempt = db.execute(
                """SELECT state,close_reason
                   FROM inventory_mission_attempts WHERE tenant_id=%s AND attempt_id=%s""",
                (case["tenant"], case["old_attempt_id"]),
            ).fetchone()
            new_attempt = db.execute(
                """SELECT state,document_id,location_id
                   FROM inventory_mission_attempts WHERE tenant_id=%s AND attempt_id=%s""",
                (case["tenant"], new_attempt_id),
            ).fetchone()
            old_closure = db.execute(
                """SELECT state,reason
                   FROM inventory_mission_lease_closures
                   WHERE tenant_id=%s AND lease_id=%s""",
                (case["tenant"], case["old_lease_id"]),
            ).fetchone()
            new_lease_count = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_mission_leases
                   WHERE tenant_id=%s AND attempt_id=%s""",
                (case["tenant"], new_attempt_id),
            ).fetchone()["n"]
            audit_count = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_audit
                   WHERE tenant_id=%s AND action='INVENTORY_DEVICE_REPLACED'
                     AND record->>'replaced_device_id'=%s
                     AND record->>'device_id'=%s""",
                (
                    case["tenant"],
                    str(case["old_device_id"]),
                    str(case["new_device_id"]),
                ),
            ).fetchone()["n"]
            outbox_count = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_outbox
                   WHERE tenant_id=%s AND event_type='INVENTORY_DEVICE_REPLACED'
                     AND payload->>'replaced_device_id'=%s
                     AND payload->>'device_id'=%s""",
                (
                    case["tenant"],
                    str(case["old_device_id"]),
                    str(case["new_device_id"]),
                ),
            ).fetchone()["n"]

        self.assertEqual(old_device["status"], "REPLACED")
        self.assertEqual(str(old_device["replaced_by"]), str(case["new_device_id"]))
        self.assertIsNotNone(old_device["revoked_at"])
        self.assertEqual(new_device["status"], "ACTIVE")
        self.assertEqual(new_device["employee_id"], "EMP-RECOVERY")
        self.assertEqual(old_attempt["state"], "SUPERSEDED")
        self.assertIn("previous evidence preserved", old_attempt["close_reason"])
        self.assertEqual(old_closure["state"], "SUPERSEDED")
        self.assertEqual(new_attempt["state"], "ACTIVE")
        self.assertEqual(str(new_attempt["document_id"]), str(case["document_id"]))
        self.assertEqual(new_attempt["location_id"], "A01")
        self.assertEqual(new_lease_count, 0, "new device must claim fresh server lease")
        self.assertEqual(audit_count, 1)
        self.assertEqual(outbox_count, 1)

    def test_replacement_never_mints_attempt_outside_current_warehouse_scope(self):
        case = self.seed_replacement_case(replacement_scope=frozenset({"WH-2"}))
        with patch.dict(
            os.environ,
            {"INVENTORY_MDM_ACTIVATION_PEPPER": case["pepper"]},
            clear=False,
        ):
            result = replace_managed_device(
                case["principal"],
                case["old_device_id"],
                case["activation_code"],
                case["new_public_pem"],
            )

        self.assertEqual(result["recovered_locations"], [])
        self.assertEqual(len(result["supervisor_reassignment_required"]), 1)
        with connect() as db:
            active_attempts = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND document_id=%s AND location_id='A01' AND state='ACTIVE'""",
                (case["tenant"], case["document_id"]),
            ).fetchone()["n"]
        self.assertEqual(active_attempts, 0)

    def test_same_device_cannot_replace_itself_before_database_mutation(self):
        device_id = uuid4()
        principal = InventoryPrincipal(
            "tenant",
            "subject",
            "employee",
            frozenset({"WH-1"}),
            device_id,
        )
        with self.assertRaises(InventoryRuleError):
            replace_managed_device(
                principal,
                device_id,
                f"replacement-{uuid4()}-{uuid4()}",
                self.public_pem(),
            )
