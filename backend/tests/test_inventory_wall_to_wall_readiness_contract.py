from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "014_inventory_wall_to_wall_readiness_authority.sql"
PRODUCTION = ROOT / "backend" / "app" / "modules" / "inventory" / "production.py"
SCHEMAS = ROOT / "backend" / "app" / "modules" / "inventory" / "schemas.py"


class InventoryWallToWallReadinessContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = MIGRATION.read_text(encoding="utf-8")
        self.production = PRODUCTION.read_text(encoding="utf-8")
        self.schemas = SCHEMAS.read_text(encoding="utf-8")

    def test_v14_keeps_inventory_document_as_canonical_aggregate(self) -> None:
        self.assertIn("ALTER TABLE inventory_documents", self.sql)
        self.assertIn("count_mode", self.sql)
        self.assertIn("'GOLDEN_COUNT','WALL_TO_WALL'", self.sql)
        self.assertNotIn("CREATE TABLE inventory_campaign", self.sql)
        self.assertNotIn("CREATE TABLE IF NOT EXISTS inventory_campaign", self.sql)
        self.assertNotIn("CREATE TABLE inventory_wall_to_wall_document", self.sql)

    def test_v14_exposes_machine_readiness_with_unknown_fail_closed(self) -> None:
        self.assertIn("inventory_wall_to_wall_readiness_v14", self.sql)
        self.assertIn("'status','UNKNOWN'", self.sql)
        self.assertIn("'status','READY'", self.sql)
        self.assertIn("'LOCATION_SCOPE_UNKNOWN'", self.sql)
        self.assertIn("'SKU_SCOPE_UNKNOWN'", self.sql)
        self.assertIn("'LOST_FOUND_REQUIRED'", self.sql)
        self.assertIn("'STANDARD_LOCATION_REQUIRED'", self.sql)
        self.assertIn("'OPERATIONAL_MISSIONS_ACTIVE'", self.sql)
        self.assertIn("'ANOTHER_W2W_ACTIVE'", self.sql)
        self.assertIn("readiness_snapshot->>'status'<>'READY'", self.sql)

    def test_v14_serializes_start_against_operational_work(self) -> None:
        self.assertIn("inventory:w2w:warehouse:", self.sql)
        self.assertIn("pg_advisory_xact_lock", self.sql)
        self.assertIn("inventory_guard_w2w_readiness_v14_trigger", self.sql)
        self.assertIn("inventory_guard_operational_during_w2w_v14_trigger", self.sql)
        self.assertIn("state IN ('OPEN','CLAIMED')", self.sql)
        self.assertIn("Wall-to-Wall count is in progress", self.sql)

    def test_v14_persists_immutable_start_evidence(self) -> None:
        self.assertIn("inventory_w2w_start_evidence", self.sql)
        self.assertIn("readiness_snapshot jsonb NOT NULL", self.sql)
        self.assertIn("readiness_snapshot->>'status'='READY'", self.sql)
        self.assertIn("DEFERRABLE INITIALLY DEFERRED", self.sql)
        self.assertIn("inventory_w2w_start_evidence_immutable", self.sql)
        self.assertIn("inventory_immutable_row()", self.sql)
        self.assertIn("ON CONFLICT (tenant_id,document_id) DO NOTHING", self.sql)

    def test_v14_allows_only_one_active_w2w_per_warehouse(self) -> None:
        self.assertIn("inventory_one_active_w2w_per_warehouse_v14", self.sql)
        self.assertIn("count_mode='WALL_TO_WALL'", self.sql)
        self.assertIn("state IN ('COUNTING','SUBMITTED','RECONCILING')", self.sql)
        self.assertIn("Inventory count mode is immutable after document creation", self.sql)

    def test_v14_production_api_admits_canonical_count_modes(self) -> None:
        self.assertIn(
            'count_mode: str = Field(default="GOLDEN_COUNT", pattern="^(GOLDEN_COUNT|WALL_TO_WALL)$")',
            self.schemas,
        )
        create_slice = self.production.split("def create_document", 1)[1].split(
            "def _terminal_mission_id", 1
        )[0]
        self.assertIn('payload.get("count_mode", "GOLDEN_COUNT")', create_slice)
        self.assertIn('count_mode == "WALL_TO_WALL" and "LOST_FOUND" not in locations', create_slice)
        self.assertIn("inventory:w2w:warehouse:", create_slice)
        self.assertIn("inventory_wall_to_wall_readiness_v14", create_slice)
        self.assertIn("Bu depoda zaten aktif bir Wall-to-Wall sayımı var", create_slice)

    def test_v14_terminal_fails_closed_and_keeps_blind_count_boundary(self) -> None:
        task_slice = self.production.split("def list_terminal_tasks", 1)[1].split(
            "def reconciliation", 1
        )[0]
        self.assertIn("d.count_mode", task_slice)
        self.assertIn("inventory_wall_to_wall_readiness_v14", task_slice)
        self.assertIn("->>'status'='READY'", task_slice)
        self.assertIn("l.location_id='LOST_FOUND'", task_slice)
        self.assertIn("standard_l.location_kind='STANDARD'", task_slice)
        self.assertIn("standard_l.completed_event_id IS NULL", task_slice)
        self.assertNotIn("expected_quantity", task_slice)
        self.assertNotIn("unit_cost", task_slice)
        self.assertNotIn("variance", task_slice)

    def test_v14_registers_schema_version(self) -> None:
        self.assertIn(
            "VALUES (14,'inventory wall-to-wall readiness and warehouse quiescence authority')",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
