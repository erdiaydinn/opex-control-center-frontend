"""Static regression gate for Inventory production identity authority.

The legacy pilot routes may retain compatibility headers while production v1
must never accept role/permission authority as route parameters.
"""

import ast
from pathlib import Path

ROUTER = Path(__file__).parents[1] / "app" / "modules" / "inventory" / "router.py"
PRODUCTION_AUTHORIZED_ROUTES = {
    "create_production_document",
    "production_terminal_tasks",
    "production_reconciliation",
    "production_explanation_context",
    "transition_document",
}
FORBIDDEN_AUTHORITY_PARAMETERS = {"x_opex_role", "x_opex_permissions"}


def production_functions():
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in PRODUCTION_AUTHORIZED_ROUTES
    }


def test_all_production_authorized_routes_are_guarded() -> None:
    functions = production_functions()
    assert set(functions) == PRODUCTION_AUTHORIZED_ROUTES

    for name, node in functions.items():
        parameter_names = {argument.arg for argument in node.args.args}
        assert not parameter_names.intersection(FORBIDDEN_AUTHORITY_PARAMETERS), name

        calls = {
            call.func.id
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
        }
        assert "require_verified_identity" in calls, name


def test_verified_identity_guard_reads_request_state_not_request_headers() -> None:
    tree = ast.parse(ROUTER.read_text(encoding="utf-8"))
    guard = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "require_verified_identity"
    )
    rendered = ast.unparse(guard)
    assert "request.state" in rendered
    assert "request.headers" not in rendered
    assert "x_opex_role" not in rendered
    assert "x_opex_permissions" not in rendered
