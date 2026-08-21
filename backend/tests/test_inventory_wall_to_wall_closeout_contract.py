from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "011_inventory_wall_to_wall_closeout_authority.sql"
SCOPE_GUARD_FIX = ROOT / "backend" / "migrations" / "012_inventory_wall_to_wall_scope_guard_fix.sql"
RECONCILIATION = ROOT / "backend" / "app" / "modules" / "inventory" / "reconciliation.py"


class InventoryWallToWallCloseoutContractTest(unittest.TestCase):
    def test_v11_keeps_inventory_document_as_canonical_wall_to_wall_aggregate(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("inventory_document_closeouts", sql)
        self.assertIn("inventory_wall_to_wall_submit_guard_v11", sql)
        self.assertIn("inventory_wall_to_wall_closeout_v11", sql)
        self.assertIn("inventory_wall_to_wall_location_scope_v11", sql)
        self.assertIn("inventory_wall_to_wall_sku_scope_v11", sql)
        self.assertIn("inventory_location_completion_anchor_v11", sql)
        self.assertIn("inventory_mission_attempts", sql)
        self.assertIn("inventory_mission_lease_closures", sql)
        self.assertIn("state='COMPLETED'", sql)
        self.assertIn("state='ACTIVE'", sql)
        self.assertIn("valid_until>now()", sql)
        self.assertIn("inventory_schema_migrations(version,name)", sql)
        self.assertIn("VALUES (11,'inventory wall-to-wall scope freeze and closeout authority')", sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS inventory_campaign", sql)

    def test_v12_makes_shared_scope_trigger_record_shape_safe(self) -> None:
        sql = SCOPE_GUARD_FIX.read_text(encoding="utf-8")
        self.assertIn("CREATE OR REPLACE FUNCTION inventory_guard_wall_to_wall_scope_v11()", sql)
        self.assertIn("IF TG_TABLE_NAME='inventory_document_locations' THEN", sql)
        self.assertIn("NEW.location_id=OLD.location_id", sql)
        self.assertIn("ELSIF TG_TABLE_NAME<>'inventory_expected_stock' THEN", sql)
        self.assertIn("unsupported table", sql)
        self.assertIn("VALUES (12,'inventory wall-to-wall record-shape safe scope guard')", sql)
        location_branch = sql.index("IF TG_TABLE_NAME='inventory_document_locations' THEN")
        location_field = sql.index("NEW.location_id=OLD.location_id")
        expected_stock_branch = sql.index("ELSIF TG_TABLE_NAME<>'inventory_expected_stock' THEN")
        self.assertLess(location_branch, location_field)
        self.assertLess(location_field, expected_stock_branch)

    def test_closeout_evidence_is_immutable_server_generated_and_location_bound(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        self.assertIn("inventory_document_closeouts_immutable", sql)
        self.assertIn("inventory_immutable_row()", sql)
        self.assertIn("completion_event_id", sql)
        self.assertIn("e.event_type='LOCATION_COMPLETE'", sql)
        self.assertIn("e.location_id=l.location_id", sql)
        self.assertIn("e.event_id=l.completed_event_id", sql)
        self.assertIn("completion_evidence jsonb NOT NULL", sql)
        self.assertIn("payload_hash", sql)
        self.assertIn("attempt_id", sql)
        self.assertIn("lease_id", sql)
        self.assertIn("active_shift_id", sql)

    def test_reconciliation_exposes_explainable_wall_to_wall_blockers(self) -> None:
        tree = ast.parse(RECONCILIATION.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_wall_to_wall_status"
        )
        rendered = ast.unparse(function)
        for token in (
            "required_location_count",
            "completed_location_count",
            "active_attempt_count",
            "live_lease_count",
            "remaining_locations",
            "invalid_completion_locations",
            "LOCATIONS_REMAINING",
            "INVALID_COMPLETION_EVIDENCE",
            "ACTIVE_ATTEMPTS",
            "LIVE_LEASES",
            "ready_to_submit",
        ):
            self.assertIn(token, rendered)

    def test_reconciliation_returns_wall_to_wall_status_with_variance_truth(self) -> None:
        tree = ast.parse(RECONCILIATION.read_text(encoding="utf-8"))
        function = next(
            node for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "reconciliation"
        )
        rendered = ast.unparse(function)
        self.assertIn("_wall_to_wall_status", rendered)
        self.assertIn("'wall_to_wall': wall_to_wall", rendered)
        self.assertIn("inventory_expected_stock", rendered)
        self.assertIn("inventory_mission_attempts", rendered)


if __name__ == "__main__":
    unittest.main()
