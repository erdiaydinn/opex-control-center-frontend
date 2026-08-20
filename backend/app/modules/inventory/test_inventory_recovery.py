from __future__ import annotations

import os
import unittest
from uuid import uuid4

from .production import InventoryPrincipal, connect
from .recovery import (
    disposition_recovery_case,
    list_open_recovery_cases,
    request_recovery_case,
)
from .service import InventoryRuleError


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryRecoveryPostgresTests(unittest.TestCase):
    def setUp(self):
        self.tenant = os.getenv("INVENTORY_TEST_TENANT", f"recovery-{uuid4()}")
        self.document_id = uuid4()
        self.maker_device = uuid4()
        self.checker_device = uuid4()
        self.event_id = uuid4()
        self.payload_hash = "a" * 64
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
            for principal in (self.maker, self.checker):
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,'test-public-key',%s,'ACTIVE')""",
                    (
                        self.tenant,
                        principal.device_id,
                        principal.employee_id,
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

    def test_request_is_idempotent_and_contains_no_raw_count_payload(self):
        first = request_recovery_case(self.maker, self.recovery_payload())
        replay = request_recovery_case(self.maker, self.recovery_payload())

        self.assertFalse(first["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(first["case_id"], replay["case_id"])
        self.assertEqual(first["evidence_policy"], "PRESERVE_NO_CLIENT_PROMOTION")
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

    def test_maker_checker_and_authoritative_confirmation_are_fail_closed(self):
        case = request_recovery_case(self.maker, self.recovery_payload())
        case_id = case["case_id"]

        open_cases = list_open_recovery_cases(self.checker)
        self.assertIn(case_id, {row["case_id"] for row in open_cases})

        with self.assertRaises(PermissionError):
            disposition_recovery_case(
                self.maker,
                case_id,
                "RECOUNT_REQUIRED",
                "maker cannot approve own recovery",
            )

        with self.assertRaises(InventoryRuleError):
            disposition_recovery_case(
                self.checker,
                case_id,
                "SERVER_EVIDENCE_CONFIRMED",
                "must fail because event is not authoritative",
            )

        result = disposition_recovery_case(
            self.checker,
            case_id,
            "RECOUNT_REQUIRED",
            "physical recount required after quarantined conflict",
        )
        replay = disposition_recovery_case(
            self.checker,
            case_id,
            "RECOUNT_REQUIRED",
            "physical recount required after quarantined conflict",
        )
        self.assertFalse(result["idempotent"])
        self.assertTrue(replay["idempotent"])
        self.assertEqual(result["next_action"], "SUPERVISOR_MISSION_REASSIGN")
        self.assertFalse(result["authoritative_event_match"])
        self.assertNotIn(case_id, {row["case_id"] for row in list_open_recovery_cases(self.checker)})

    def test_security_identity_quarantine_never_enters_business_supervisor_path(self):
        with self.assertRaises(InventoryRuleError):
            request_recovery_case(
                self.maker,
                self.recovery_payload(quarantine_reason="AUTH_BINDING_CHANGED"),
            )
