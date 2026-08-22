from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "014_inventory_wall_to_wall_readiness_authority.sql"


class InventoryWallToWallReadinessContractTest(unittest.TestCase):
    def setUp(self) -> None:
        self.sql = MIGRATION.read_text(encoding="utf-8")

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

    def test_v14_registers_schema_version(self) -> None:
        self.assertIn(
            "VALUES (14,'inventory wall-to-wall readiness and warehouse quiescence authority')",
            self.sql,
        )


if __name__ == "__main__":
    unittest.main()
