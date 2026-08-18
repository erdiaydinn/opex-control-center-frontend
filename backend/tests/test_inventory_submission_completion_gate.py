from __future__ import annotations

import ast
from pathlib import Path

PRODUCTION = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "production.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(PRODUCTION.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_submission_gate_uses_only_server_ledger_location_truth() -> None:
    rendered = ast.unparse(_function("_assert_all_locations_completed"))
    assert "inventory_document_locations" in rendered
    assert "inventory_events" in rendered
    assert "LOCATION_COMPLETE" in rendered
    assert "count(DISTINCT location_id)" in rendered
    assert "required_location_count" in rendered
    assert "completed_location_count" in rendered
    assert "InventoryRuleError" in rendered
    assert "expected_quantity" not in rendered
    assert "inventory_expected_stock" not in rendered


def test_counting_to_submitted_requires_all_location_completion_inside_transition() -> None:
    rendered = ast.unparse(_function("transition"))
    assert "row['state'] == 'COUNTING'" in rendered
    assert "target_state == 'SUBMITTED'" in rendered
    assert "_assert_all_locations_completed" in rendered


def test_approval_cannot_bypass_explicit_reconciliation_state() -> None:
    rendered = ast.unparse(_function("transition"))
    assert "('COUNTING', 'SUBMITTED')" in rendered
    assert "('SUBMITTED', 'RECONCILING')" in rendered
    assert "('RECONCILING', 'APPROVED')" in rendered
    assert "('APPROVED', 'LOCKED')" in rendered
    assert "('SUBMITTED', 'APPROVED')" not in rendered


def test_rejection_remains_a_supervisor_escape_path_from_submitted() -> None:
    rendered = ast.unparse(_function("transition"))
    assert "('SUBMITTED', 'REJECTED')" in rendered
