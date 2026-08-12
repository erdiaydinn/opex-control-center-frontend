from __future__ import annotations

import ast
from pathlib import Path

from pydantic import ValidationError
import pytest

from app.core.ai_tool_grants import AiToolGrantBinding


APP_ROOT = Path(__file__).resolve().parents[1] / "app"


def _route_path(node: ast.Call) -> str | None:
    if not node.args:
        return None

    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value

    return None


def test_mutating_internal_ai_routes_require_fresh_jarvis_identity() -> None:
    violations: list[str] = []

    for path in APP_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))

        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue

            internal_ai_route = False
            mutating = False

            for decorator in node.decorator_list:
                if not isinstance(decorator, ast.Call):
                    continue
                if not isinstance(decorator.func, ast.Attribute):
                    continue

                method = decorator.func.attr.lower()
                route_path = _route_path(decorator)

                if route_path and route_path.startswith("/internal/ai/"):
                    internal_ai_route = True
                    mutating = method in {"post", "put", "patch", "delete"}

            if not (internal_ai_route and mutating):
                continue

            referenced_names = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
            }

            if "require_fresh_jarvis_service" not in referenced_names:
                violations.append(
                    f"{path.relative_to(APP_ROOT)}:{node.lineno}:{node.name}"
                )

            if (
                "require_jarvis_service" in referenced_names
                and "require_fresh_jarvis_service" not in referenced_names
            ):
                violations.append(
                    f"{path.relative_to(APP_ROOT)}:{node.lineno}:{node.name}:basic-only"
                )

    assert not violations, (
        "Mutating /internal/ai routes must require fresh single-use "
        "Jarvis machine identity: " + ", ".join(violations)
    )


def test_grant_binding_schema_rejects_unknown_version() -> None:
    with pytest.raises(ValidationError):
        AiToolGrantBinding(
            version=2,  # type: ignore[arg-type]
            tenant_id="11111111-1111-4111-8111-111111111111",
            actor_subject="user-1",
            tool="ops_kpi_query",
            arguments_sha256="a" * 64,
            reason_sha256="b" * 64,
            authorization_fingerprint="c" * 64,
        )


def test_grant_binding_schema_rejects_unreviewed_tool() -> None:
    with pytest.raises(ValidationError):
        AiToolGrantBinding(
            version=1,
            tenant_id="11111111-1111-4111-8111-111111111111",
            actor_subject="user-1",
            tool="arbitrary_shell",  # type: ignore[arg-type]
            arguments_sha256="a" * 64,
            reason_sha256="b" * 64,
            authorization_fingerprint="c" * 64,
        )
