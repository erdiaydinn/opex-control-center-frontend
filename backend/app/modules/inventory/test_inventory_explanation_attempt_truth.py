from __future__ import annotations

from datetime import UTC, datetime, timedelta
import os
import unittest
from uuid import uuid4

from .explanation import explanation_context
from .production import InventoryPrincipal, connect


@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class InventoryExplanationAttemptTruthTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenant = os.getenv("INVENTORY_TEST_TENANT", f"test-{uuid4()}")
        self.document_id = uuid4()
        self.location_id = "A01"
        self.device_abandoned = uuid4()
        self.device_completed = uuid4()
        self.attempt_abandoned = uuid4()
        self.attempt_completed = uuid4()
        self.lease_abandoned = uuid4()
        self.lease_completed = uuid4()
        self.now = datetime.now(UTC)

        with connect() as db:
            for device_id, employee_id in (
                (self.device_abandoned, "EMP-ABANDONED"),
                (self.device_completed, "EMP-COMPLETED"),
            ):
                db.execute(
                    """INSERT INTO inventory_devices(
                         tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                       ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                    (
                        self.tenant,
                        device_id,
                        employee_id,
                        "-----BEGIN PUBLIC KEY-----\nTEST\n-----END PUBLIC KEY-----",
                        f"mdm-{uuid4()}",
                    ),
                )
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by
                   ) VALUES(%s,%s,'WH-EXPLAIN','Jarvis truth test','COUNTING','maker')""",
                (self.tenant, self.document_id),
            )
            db.execute(
                "INSERT INTO inventory_document_locations VALUES(%s,%s,%s)",
                (self.tenant, self.document_id, self.location_id),
            )
            db.execute(
                """INSERT INTO inventory_expected_stock(
                     tenant_id,document_id,sku,barcode,expected_quantity,unit_cost
                   ) VALUES(%s,%s,'SKU-EXPLAIN','8690000000001',10,2)""",
                (self.tenant, self.document_id),
            )

            abandoned_created = self.now - timedelta(minutes=20)
            abandoned_valid_from = self.now - timedelta(minutes=19)
            abandoned_valid_until = self.now - timedelta(minutes=10)
            abandoned_event_at = self.now - timedelta(minutes=15)
            abandoned_closed_at = self.now - timedelta(minutes=9)
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,warehouse_id,location_id,
                     created_by_subject,created_by_employee_id,created_at
                   ) VALUES(%s,%s,%s,'WH-EXPLAIN',%s,'counter-a','EMP-ABANDONED',%s)""",
                (
                    self.tenant,
                    self.attempt_abandoned,
                    self.document_id,
                    self.location_id,
                    abandoned_created,
                ),
            )
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until,issued_at
                   ) VALUES(%s,%s,%s,'EMP-ABANDONED',%s,'SHIFT-A','WH-EXPLAIN',%s,%s,%s)""",
                (
                    self.tenant,
                    self.lease_abandoned,
                    self.attempt_abandoned,
                    self.device_abandoned,
                    abandoned_valid_from,
                    abandoned_valid_until,
                    abandoned_valid_from,
                ),
            )
            db.execute(
                """INSERT INTO inventory_events(
                     tenant_id,event_id,device_id,device_sequence,document_id,warehouse_id,
                     employee_id,event_type,location_id,barcode,quantity,symbology,
                     payload_hash,occurred_at,attempt_id,lease_id,active_shift_id
                   ) VALUES(%s,%s,%s,1,%s,'WH-EXPLAIN','EMP-ABANDONED','SCAN',%s,
                            '8690000000001',2,'EAN13',%s,%s,%s,%s,'SHIFT-A')""",
                (
                    self.tenant,
                    uuid4(),
                    self.device_abandoned,
                    self.document_id,
                    self.location_id,
                    "a" * 64,
                    abandoned_event_at,
                    self.attempt_abandoned,
                    self.lease_abandoned,
                ),
            )
            db.execute(
                """UPDATE inventory_mission_attempts
                   SET state='ABANDONED',closed_at=%s,close_reason='device replacement'
                   WHERE tenant_id=%s AND attempt_id=%s""",
                (abandoned_closed_at, self.tenant, self.attempt_abandoned),
            )

            completed_created = self.now - timedelta(minutes=8)
            completed_valid_from = self.now - timedelta(minutes=7)
            completed_valid_until = self.now + timedelta(minutes=5)
            completed_event_at = self.now - timedelta(minutes=5)
            completed_closed_at = self.now - timedelta(minutes=1)
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,warehouse_id,location_id,
                     created_by_subject,created_by_employee_id,created_at
                   ) VALUES(%s,%s,%s,'WH-EXPLAIN',%s,'counter-b','EMP-COMPLETED',%s)""",
                (
                    self.tenant,
                    self.attempt_completed,
                    self.document_id,
                    self.location_id,
                    completed_created,
                ),
            )
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until,issued_at
                   ) VALUES(%s,%s,%s,'EMP-COMPLETED',%s,'SHIFT-B','WH-EXPLAIN',%s,%s,%s)""",
                (
                    self.tenant,
                    self.lease_completed,
                    self.attempt_completed,
                    self.device_completed,
                    completed_valid_from,
                    completed_valid_until,
                    completed_valid_from,
                ),
            )
            db.execute(
                """INSERT INTO inventory_events(
                     tenant_id,event_id,device_id,device_sequence,document_id,warehouse_id,
                     employee_id,event_type,location_id,barcode,quantity,symbology,
                     payload_hash,occurred_at,attempt_id,lease_id,active_shift_id
                   ) VALUES(%s,%s,%s,1,%s,'WH-EXPLAIN','EMP-COMPLETED','SCAN',%s,
                            '8690000000001',5,'EAN13',%s,%s,%s,%s,'SHIFT-B')""",
                (
                    self.tenant,
                    uuid4(),
                    self.device_completed,
                    self.document_id,
                    self.location_id,
                    "b" * 64,
                    completed_event_at,
                    self.attempt_completed,
                    self.lease_completed,
                ),
            )
            db.execute(
                """UPDATE inventory_mission_attempts
                   SET state='COMPLETED',closed_at=%s,close_reason='location completed'
                   WHERE tenant_id=%s AND attempt_id=%s""",
                (completed_closed_at, self.tenant, self.attempt_completed),
            )
            db.commit()

        self.principal = InventoryPrincipal(
            tenant_id=self.tenant,
            subject="jarvis-reader",
            employee_id="EMP-COMPLETED",
            warehouse_scope=frozenset({"WH-EXPLAIN"}),
            device_id=self.device_completed,
        )

    def test_abandoned_attempt_is_visible_only_as_lifecycle_not_stock_truth(self) -> None:
        context = explanation_context(self.principal, self.document_id)

        self.assertEqual(context["schema_version"], 3)
        self.assertEqual(context["source"], "inventory_completed_attempt_truth")
        self.assertTrue(context["abandoned_attempt_events_excluded_from_stock_truth"])
        self.assertTrue(context["recovery_reasons_free_text_excluded"])
        self.assertTrue(context["superseded_attempt_evidence_preserved"])
        self.assertEqual(context["lease_closure_lifecycle"], [])
        self.assertEqual(context["events"], context["authoritative_events"])

        lifecycle = {
            row["state"]: row["attempt_count"]
            for row in context["attempt_lifecycle"]
        }
        self.assertEqual(lifecycle["ABANDONED"], 1)
        self.assertEqual(lifecycle["COMPLETED"], 1)

        scan_count = sum(
            row["event_count"]
            for row in context["authoritative_events"]
            if row["event_type"] in {"SCAN", "UNEXPECTED_SKU"}
        )
        self.assertEqual(scan_count, 1)
        self.assertEqual(float(context["variance_summary"]["absolute_quantity_variance"]), 5.0)
        self.assertEqual(float(context["variance_summary"]["absolute_value_variance"]), 10.0)


if __name__ == "__main__":
    unittest.main()
