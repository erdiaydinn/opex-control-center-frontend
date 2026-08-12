from __future__ import annotations

import ast
from pathlib import Path

from app.tool_execution import TemplateToolExecutionRequest


APP_ROOT = Path(__file__).resolve().parents[1] / "app"
LOW_LEVEL_EXECUTOR = "execute_with_adapter"
GOVERNED_EXECUTOR = "authorize_and_execute_with_adapter"


def _called_name(node: ast.Call) -> str | None:
    function = node.func
    if isinstance(function, ast.Name):
        return function.id
    if isinstance(function, ast.Attribute):
        return function.attr
    return None


def test_production_modules_cannot_bypass_platform_authorization_wrapper() -> None:
    violations: list[str] = []

    for path in sorted(APP_ROOT.rglob("*.py")):
        if path.name == "tool_execution.py":
            continue

        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _called_name(node) == LOW_LEVEL_EXECUTOR:
                violations.append(f"{path.relative_to(APP_ROOT)}:{node.lineno}")

    assert violations == [], (
        "Production code bypasses Platform tool authorization: "
        + ", ".join(violations)
    )


def test_voice_adapter_uses_governed_authorization_wrapper() -> None:
    path = APP_ROOT / "voice_governed_tool_adapter.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = {
        _called_name(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }

    assert GOVERNED_EXECUTOR in calls
    assert LOW_LEVEL_EXECUTOR not in calls


def test_public_execution_request_has_no_identity_or_permission_inputs() -> None:
    fields = set(TemplateToolExecutionRequest.model_fields)

    assert "grant_token" in fields
    assert {
        "granted_scopes",
        "requested_by",
        "tenant_id",
        "actor_subject",
        "permissions",
        "roles",
    }.isdisjoint(fields)


def test_low_level_executor_is_only_invoked_inside_governed_wrapper() -> None:
    path = APP_ROOT / "tool_execution.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    wrapper_calls = []
    other_calls = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if _called_name(child) != LOW_LEVEL_EXECUTOR:
                continue
            target = wrapper_calls if node.name == GOVERNED_EXECUTOR else other_calls
            target.append(node.lineno)

    assert wrapper_calls
    assert other_calls == []
