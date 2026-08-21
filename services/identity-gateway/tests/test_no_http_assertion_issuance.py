from __future__ import annotations

import ast
from pathlib import Path

MAIN_PATH = Path(__file__).resolve().parents[1] / "app" / "main.py"
EXPECTED_HTTP_ROUTES = {
    ("get", "/health/live"),
    ("get", "/health/ready"),
    ("get", "/.well-known/jwks.json"),
}
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}
FORBIDDEN_ISSUANCE_SYMBOLS = {
    "issue_authorized_session_assertions",
    "issue_ai_tenant_context_assertion",
    "issue_internal_assertion",
}


def _http_routes(source: str) -> set[tuple[str, str]]:
    tree = ast.parse(source)
    routes: set[tuple[str, str]] = set()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            func = decorator.func
            if not isinstance(func, ast.Attribute) or func.attr not in HTTP_METHODS:
                continue
            if not decorator.args:
                raise AssertionError("Identity Gateway HTTP route must declare a literal path")
            path_node = decorator.args[0]
            if not isinstance(path_node, ast.Constant) or not isinstance(path_node.value, str):
                raise AssertionError("Identity Gateway HTTP route path must remain a literal string")
            routes.add((func.attr, path_node.value))

    return routes


def test_identity_gateway_exposes_no_assertion_issuance_route() -> None:
    source = MAIN_PATH.read_text(encoding="utf-8")

    assert _http_routes(source) == EXPECTED_HTTP_ROUTES
    for symbol in FORBIDDEN_ISSUANCE_SYMBOLS:
        assert symbol not in source, (
            "Identity assertion issuance must remain trusted server-side code; "
            f"do not expose {symbol} from the HTTP application"
        )


def test_identity_gateway_has_no_mutating_http_method() -> None:
    routes = _http_routes(MAIN_PATH.read_text(encoding="utf-8"))
    assert all(method == "get" for method, _ in routes)
