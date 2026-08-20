import os
import unittest
from unittest.mock import MagicMock, patch
from uuid import uuid4

from .operational_mission import DEFINITIONS, event_hash_input, claim_operational_mission
from .production import InventoryPrincipal, canonical_payload_hash
from .production import connect

class OperationalMissionContractTests(unittest.TestCase):
    def test_all_workflows_end_once_with_complete(self):
        self.assertEqual(set(DEFINITIONS), {"PICKING","PUTAWAY","RECEIVING","TRANSFER"})
        for operation, steps in DEFINITIONS.values():
            self.assertTrue(operation.startswith("inventory."))
            self.assertEqual(steps[-1], "COMPLETE")
            self.assertEqual(steps.count("COMPLETE"), 1)

    def test_authority_fields_are_hash_bound(self):
        payload={"event_id":str(uuid4()),"mission_id":str(uuid4()),"claim_id":str(uuid4()),"active_shift_id":"S1","device_sequence":1,"step_kind":"ITEM","value_hash":"a"*64,"occurred_at":"2026-08-20T12:00:00+00:00"}
        original=canonical_payload_hash(event_hash_input(payload))
        self.assertNotEqual(original,canonical_payload_hash(event_hash_input({**payload,"active_shift_id":"S2"})))
        self.assertNotEqual(original,canonical_payload_hash(event_hash_input({**payload,"claim_id":str(uuid4())})))

    @patch("backend.app.modules.inventory.operational_mission.connect")
    @patch("backend.app.modules.inventory.operational_mission._assert_runtime_tenant")
    @patch("backend.app.modules.inventory.operational_mission._assert_active_device")
    def test_foreign_live_claim_is_rejected(self,_device,_tenant,connect):
        db=MagicMock(); connect.return_value.__enter__.return_value=db
        mission={"warehouse_id":"WH-1","state":"CLAIMED","steps":["ITEM","COMPLETE"]}
        foreign={"employee_id":"OTHER","device_id":uuid4(),"shift_id":"OTHER","claim_id":uuid4()}
        db.execute.return_value.fetchone.side_effect=[mission,foreign]
        principal=InventoryPrincipal("T","subject","EMP",frozenset({"WH-1"}),uuid4())
        with self.assertRaisesRegex(Exception,"başka aktör"):
            claim_operational_mission(principal,uuid4(),"SHIFT")

@unittest.skipUnless(os.getenv("INVENTORY_DATABASE_URL"), "requires PostgreSQL")
class OperationalMissionPostgresTests(unittest.TestCase):
    def test_v7_tables_and_append_only_event_trigger_exist(self):
        with connect() as db:
            self.assertTrue(db.execute("SELECT 1 FROM inventory_schema_migrations WHERE version=7").fetchone())
            tables=db.execute("""SELECT tablename FROM pg_tables WHERE schemaname=current_schema() AND tablename LIKE 'inventory_operational_%'""").fetchall()
            self.assertEqual({row["tablename"] for row in tables},{"inventory_operational_missions","inventory_operational_claims","inventory_operational_events","inventory_operational_event_responses"})
            trigger=db.execute("SELECT 1 FROM pg_trigger WHERE tgname='inventory_operational_events_immutable' AND NOT tgisinternal").fetchone()
            self.assertTrue(trigger)

if __name__ == "__main__":
    unittest.main()
