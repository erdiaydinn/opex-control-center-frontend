"""Static integration contract for Workforce -> Inventory terminal shift admission."""

from __future__ import annotations

import ast
from pathlib import Path

ROUTER = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "router.py"


def _function(name: str) -> ast.FunctionDef:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    return next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name
    )


def test_active_shift_principal_uses_server_workforce_authority_and_narrows_warehouse() -> None:
    rendered = ast.unparse(_function("active_shift_principal"))
    assert "resolve_active_shift" in rendered
    assert "principal.tenant_id" in rendered
    assert "principal.employee_id" in rendered
    assert "principal.warehouse_scope" in rendered
    assert "canonical_warehouse" in rendered
    assert "str(warehouse).strip().lower() == str(attestation.warehouse_id).strip().lower()" in rendered
    assert "warehouse_scope=frozenset({canonical_warehouse})" in rendered
    assert "attestation.shift_id" in rendered
    assert "status_code=503" in rendered
    assert "status_code=403" in rendered


def test_terminal_tasks_require_count_permission_and_active_shift() -> None:
    rendered = ast.unparse(_function("production_terminal_tasks"))
    assert "require_verified_identity(request, 'countInventory')" in rendered
    assert "active_shift_principal(principal)" in rendered
    assert "if active is None" in rendered
    assert "{'rows': []}" in rendered
    assert "production_list_terminal_tasks" in rendered
    assert "active_shift_id" in rendered


def test_terminal_task_route_never_accepts_client_shift_or_role_truth() -> None:
    node = _function("production_terminal_tasks")
    parameters = {argument.arg for argument in node.args.args}
    assert "shift_id" not in parameters
    assert "active_shift_id" not in parameters
    assert "x_opex_role" not in parameters
    assert "x_opex_permissions" not in parameters


def test_shared_inventory_boundary_maps_only_workforce_authority_outage_to_503() -> None:
    rendered = ast.unparse(_function("run"))
    assert "except RuntimeError as error" in rendered
    assert "isinstance(error.__cause__, ActiveShiftAuthorityError)" in rendered
    assert "status_code=503" in rendered
    assert "raise" in rendered
