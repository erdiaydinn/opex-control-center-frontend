from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "011_inventory_wall_to_wall_closeout_authority.sql"
RECONCILIATION = ROOT / "backend" / "app" / "modules" / "inventory" / "reconciliation.py"


def test_v11_keeps_inventory_document_as_canonical_wall_to_wall_aggregate() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "inventory_document_closeouts" in sql
    assert "inventory_wall_to_wall_submit_guard_v11" in sql
    assert "inventory_wall_to_wall_closeout_v11" in sql
    assert "inventory_wall_to_wall_location_scope_v11" in sql
    assert "inventory_wall_to_wall_sku_scope_v11" in sql
    assert "inventory_location_completion_anchor_v11" in sql
    assert "inventory_mission_attempts" in sql
    assert "inventory_mission_lease_closures" in sql
    assert "state='COMPLETED'" in sql
    assert "state='ACTIVE'" in sql
    assert "valid_until>now()" in sql
    assert "inventory_schema_migrations(version,name)" in sql
    assert "VALUES (11,'inventory wall-to-wall scope freeze and closeout authority')" in sql
    assert "CREATE TABLE IF NOT EXISTS inventory_campaign" not in sql


def test_closeout_evidence_is_immutable_server_generated_and_location_bound() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "inventory_document_closeouts_immutable" in sql
    assert "inventory_immutable_row()" in sql
    assert "completion_event_id" in sql
    assert "e.event_type='LOCATION_COMPLETE'" in sql
    assert "e.location_id=l.location_id" in sql
    assert "e.event_id=l.completed_event_id" in sql
    assert "completion_evidence jsonb NOT NULL" in sql
    assert "payload_hash" in sql
    assert "attempt_id" in sql
    assert "lease_id" in sql
    assert "active_shift_id" in sql


def test_reconciliation_exposes_explainable_wall_to_wall_blockers() -> None:
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
        assert token in rendered


def test_reconciliation_returns_wall_to_wall_status_with_variance_truth() -> None:
    tree = ast.parse(RECONCILIATION.read_text(encoding="utf-8"))
    function = next(
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "reconciliation"
    )
    rendered = ast.unparse(function)
    assert "_wall_to_wall_status" in rendered
    assert "'wall_to_wall': wall_to_wall" in rendered
    assert "inventory_expected_stock" in rendered
    assert "inventory_mission_attempts" in rendered
