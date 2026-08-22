from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).parents[2]
MIGRATION = ROOT / "backend" / "migrations" / "005_inventory_mission_attempt_lease.sql"
LEASE_MODULE = ROOT / "backend" / "app" / "modules" / "inventory" / "mission_lease.py"
EVENT_MODULE = ROOT / "backend" / "app" / "modules" / "inventory" / "mission_event.py"
ROUTER = ROOT / "backend" / "app" / "modules" / "inventory" / "router.py"
RECONCILIATION = ROOT / "backend" / "app" / "modules" / "inventory" / "reconciliation.py"


def _function(path: Path, name: str) -> ast.FunctionDef:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_v5_database_enforces_attempt_lease_history_and_rls() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    assert "inventory_mission_attempts" in sql
    assert "inventory_mission_leases" in sql
    assert "inventory_mission_lease_closures" in sql
    assert "WHERE state='ACTIVE'" in sql
    assert "inventory_mission_attempt_one_active_idx" in sql
    assert "inventory_mission_leases_immutable" in sql
    assert "inventory_mission_lease_closures_immutable" in sql
    assert "inventory_guard_mission_event_v5_trigger" in sql
    assert "NEW.occurred_at<lease_row.valid_from" in sql
    assert "NEW.occurred_at>lease_row.valid_until" in sql
    assert "NEW.occurred_at>lease_closed_at" in sql
    assert "NEW.occurred_at>attempt_row.closed_at" in sql
    assert "attempt_id IS NOT NULL" in sql
    assert "lease_id IS NOT NULL" in sql
    assert "active_shift_id IS NOT NULL" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "VALUES (5,'inventory mission attempt and historical lease authority')" in sql


def test_claim_is_transactional_idempotent_and_never_retroactively_extends_a_lease() -> None:
    rendered = ast.unparse(_function(LEASE_MODULE, "claim_terminal_mission"))
    assert "READ COMMITTED" in rendered
    assert "pg_advisory_xact_lock" in rendered
    assert "FOR UPDATE" in rendered
    assert "_verify_device_proof" in rendered
    assert "valid_until>%s" in rendered
    assert "idempotent=True" in rendered
    assert "valid_from" in rendered
    assert "INSERT INTO inventory_mission_leases" in rendered
    assert "UPDATE inventory_mission_leases" not in rendered
    assert "supervisor reassignment" in rendered


def test_historical_attestation_binds_event_to_exact_owner_interval() -> None:
    rendered = ast.unparse(_function(LEASE_MODULE, "attest_event_lease"))
    for token in (
        "document_id",
        "warehouse_id",
        "location_id",
        "employee_id",
        "device_id",
        "shift_id",
        "valid_from",
        "valid_until",
        "lease_closed_at",
        "attempt_closed_at",
    ):
        assert token in rendered
    assert "event_time < row['valid_from']" in rendered
    assert "event_time > row['valid_until']" in rendered
    assert "location_completion and row['attempt_state'] != 'ACTIVE'" in rendered


def test_completion_and_reassignment_close_truth_without_deleting_history() -> None:
    completed = ast.unparse(_function(LEASE_MODULE, "complete_attempt"))
    reassigned = ast.unparse(_function(LEASE_MODULE, "supersede_attempt"))
    assert "valid_from>%s" in completed
    assert "state='COMPLETED'" in completed
    assert "inventory_mission_lease_closures" in completed
    assert "DELETE" not in completed
    assert "state='SUPERSEDED'" in reassigned
    assert "INSERT INTO inventory_mission_attempts" in reassigned
    assert "inventory_mission_lease_closures" in reassigned
    assert "DELETE" not in reassigned


def test_terminal_event_and_router_require_claimed_mission_authority() -> None:
    event = EVENT_MODULE.read_text(encoding="utf-8")
    router = ROUTER.read_text(encoding="utf-8")
    assert '"attempt_id"' in event
    assert '"lease_id"' in event
    assert "attest_event_lease" in event
    assert "attempt_id,lease_id,active_shift_id" in event.replace(" ", "")
    assert '"/v1/terminal/missions/claim"' in router
    assert "filter_and_annotate_terminal_tasks" in router
    assert "active_shift_principal" in router
    assert '"/v1/documents/{document_id}/locations/{location_id}/reassign"' in router
    assert 'require_verified_identity(request, "approveInventory")' in router


def test_reconciliation_counts_only_completed_v5_attempts_with_explicit_legacy_boundary() -> None:
    source = RECONCILIATION.read_text(encoding="utf-8")
    compact = source.replace(" ", "")
    assert "LEFTJOINinventory_mission_attemptsa" in compact
    assert "a.state='COMPLETED'" in source
    assert "e.attempt_id IS NULL" in source
    assert "NOT EXISTS" in source
    assert "any_attempt.document_id=e.document_id" in compact
