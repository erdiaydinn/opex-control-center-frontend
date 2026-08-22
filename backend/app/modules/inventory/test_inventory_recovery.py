from __future__ import annotations

import base64
from datetime import UTC, datetime
import os
import unittest
from uuid import uuid4

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .production import InventoryPrincipal, connect
from .recovery import (
    disposition_recovery_case,
    list_open_recovery_cases,
    recovery_disposition_hash,
    recovery_request_hash,
    request_recovery_case,
)
from .service import InventoryRuleError


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryRecoveryPostgresTests(unittest.TestCase):
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
        self.tenant = os.getenv("INVENTORY_TEST_TENANT", f"recovery-{uuid4()}")
        self.document_id = uuid4()
        self.maker_device = uuid4()
        self.checker_device = uuid4()
        self.event_id = uuid4()
        self.payload_hash = "a" * 64
        self.maker_key = ec.generate_private_key(ec.SECP256R1())
        self.checker_key = ec.generate_private_key(ec.SECP256R1())
        self.maker = InventoryPrincipal(
            self.tenant,
            "maker-subject",
            "EMP-RECOVERY-MAKER",
            frozenset({"WH-1"}),
            self.maker_device,
        )
        self.checker = InventoryPrincipal(
            self.tenant,
            "checker-subject",
            "EMP-RECOVERY-CHECKER",
            frozenset({"WH-1"}),
            self.checker_device,
        )
        with connect() as db:
            for principal, private_key in (
                (self.maker, self.maker_key),
                (self.checker, self.checker_key),
            ):
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                    (
                        self.tenant,
                        principal.device_id,
                        principal.employee_id,
                        self.public_pem(private_key),
                        f"recovery-mdm-{uuid4()}",
                    ),
                )
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-1','Quarantine recovery test','COUNTING','maker')""",
                (self.tenant, self.document_id),
            )
            db.execute(
                """INSERT INTO inventory_document_locations(
                     tenant_id,document_id,location_id
                   ) VALUES(%s,%s,'A01')""",
                (self.tenant, self.document_id),
            )
            db.commit()

    def recovery_payload(self, *, quarantine_reason="BUSINESS_CONFLICT"):
        return {
            "event_id": str(self.event_id),
            "document_id": str(self.document_id),
            "location_id": "A01",
            "payload_hash": self.payload_hash,
            "quarantine_reason": quarantine_reason,
            "server_code": "COUNT_REVISION_CONFLICT",
        }

    def request_case(
        self,
        principal: InventoryPrincipal,
        private_key: ec.EllipticCurvePrivateKey,
        payload: dict,
    ):
        timestamp, nonce, signature = self.proof(
            principal,
            private_key,
            recovery_request_hash(payload),
        )
        return request_recovery_case(
            principal,
            payload,
            timestamp,
            nonce,
            signature,
        )

    def disposition(
        self,
        principal: InventoryPrincipal,
        private_key: ec.EllipticCurvePrivateKey,
        case_id: str,
        decision: str,
        reason: str,
    ):
        timestamp, nonce, signature = self.proof(
            principal,
            private_key,
            recovery_disposition_hash(case_id, decision, reason),
        )
        return disposition_recovery_case(
            principal,
            case_id,
            decision,
            reason,
            timestamp,
            nonce,
            signature,
        )

    def test_request_is_idempotent_and_contains_no_raw_count_payload(self):
        payload = self.recovery_payload()
        first = self.request_case(self.maker, self.maker_key, payload)
        replay = self.request_case(self.maker, self.maker_key, payload)

        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(first["case_id"], replay["case_id"])
        self.assertEqual(first["evidence_policy"], "PRESERVE_NO_CLIENT_PROMOTION")
        self.assertEqual(first["command_hash"], recovery_request_hash(payload))
        serialized = str(first).lower()
        self.assertNotIn("barcode", serialized)
        self.assertNotIn("quantity", serialized)

        with connect() as db:
            request_count = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_audit
                   WHERE tenant_id=%s AND action='INVENTORY_RECOVERY_REQUESTED'
                     AND record->>'case_id'=%s""",
                (self.tenant, first["case_id"]),
            ).fetchone()["n"]
            outbox_count = db.execute(
                """SELECT count(*)::integer AS n FROM inventory_outbox
                   WHERE tenant_id=%s AND event_type='INVENTORY_RECOVERY_REQUESTED'
                     AND payload->>'case_id'=%s""",
                (self.tenant, first["case_id"]),
            ).fetchone()["n"]
        self.assertEqual(request_count, 1)
        self.assertEqual(outbox_count, 1)

    def test_recovery_request_nonce_replay_is_rejected_before_idempotent_lookup(self):
        payload = self.recovery_payload()
        command_hash = recovery_request_hash(payload)
        timestamp, nonce, signature = self.proof(
            self.maker,
            self.maker_key,
            command_hash,
        )
        first = request_recovery_case(
            self.maker,
            payload,
            timestamp,
            nonce,
            signature,
        )
        self.assertFalse(first["idempotent"])
        with self.assertRaises(InventoryRuleError):
            request_recovery_case(
                self.maker,
                payload,
                timestamp,
                nonce,
                signature,
            )

    def test_maker_checker_and_authoritative_confirmation_are_fail_closed(self):
        case = self.request_case(self.maker, self.maker_key, self.recovery_payload())
        case_id = case["case_id"]

        open_cases = list_open_recovery_cases(self.checker)
        self.assertIn(case_id, {row["case_id"] for row in open_cases})

        with self.assertRaises(PermissionError):
            self.disposition(
                self.maker,
                self.maker_key,
                case_id,
                "RECOUNT_REQUIRED",
                "maker cannot approve own recovery",
            )

        with self.assertRaises(InventoryRuleError):
            self.disposition(
                self.checker,
                self.checker_key,
                case_id,
                "SERVER_EVIDENCE_CONFIRMED",
                "must fail because event is not authoritative",
            )

        reason = "physical recount required after quarantined conflict"
        result = self.disposition(
            self.checker,
            self.checker_key,
            case_id,
            "RECOUNT_REQUIRED",
            reason,
        )
        replay = self.disposition(
            self.checker,
            self.checker_key,
            case_id,
            "RECOUNT_REQUIRED",
            reason,
        )
        self.assertFalse(result["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(
            result["command_hash"],
            recovery_disposition_hash(case_id, "RECOUNT_REQUIRED", reason),
        )
        self.assertEqual(result["next_action"], "SUPERVISOR_MISSION_REASSIGN")
        self.assertFalse(result["authoritative_event_match"])
        self.assertNotIn(case_id, {row["case_id"] for row in list_open_recovery_cases(self.checker)})

    def test_security_identity_quarantine_never_enters_business_supervisor_path(self):
        payload = self.recovery_payload(quarantine_reason="AUTH_BINDING_CHANGED")
        with self.assertRaises(InventoryRuleError):
            request_recovery_case(
                self.maker,
                payload,
                "2026-08-20T00:00:00Z",
                str(uuid4()),
                "invalid-before-proof-by-contract",
            )
