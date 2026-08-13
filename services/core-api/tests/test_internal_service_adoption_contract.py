"""
Fail-closed service-to-service replay contract.

Human/admin RBAC routes remain separate from service identity.

Any future mutating internal-service endpoint must use
require_fresh_internal_service so one assertion cannot perform
the mutation more than once.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

import app.core.config as config_module
from app.core.internal_service_replay import (
    INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS,
    INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS,
)

APP_ROOT = (
    Path(__file__).parents[1]
    / "app"
)

MUTATING_METHODS = {
    "post",
    "put",
    "patch",
    "delete",
}


def _route_methods(
    node: ast.FunctionDef
    | ast.AsyncFunctionDef,
) -> set[str]:

    methods: set[str] = set()

    for decorator in node.decorator_list:

        if not isinstance(
            decorator,
            ast.Call,
        ):
            continue

        function = decorator.func

        if not isinstance(
            function,
            ast.Attribute,
        ):
            continue

        method = function.attr.lower()

        if method in {
            "get",
            "post",
            "put",
            "patch",
            "delete",
            "head",
            "options",
        }:
            methods.add(method)

    return methods


def _referenced_names(
    node: ast.AST,
) -> set[str]:

    return {
        child.id
        for child in ast.walk(node)
        if isinstance(
            child,
            ast.Name,
        )
    }


def test_replay_retention_covers_assertion_window():
    settings = (
        config_module.Settings()
    )

    required_retention = (
        settings.internal_assertion_max_lifetime_seconds
        + INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS
    )

    assert required_retention <= (
        INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS
    )


def test_config_fails_closed_if_replay_capacity_is_too_small(
    monkeypatch,
):
    monkeypatch.setattr(
        config_module,
        "INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS",
        69,
    )

    with pytest.raises(
        ValueError,
        match=(
            "Internal assertion lifetime exceeds "
            "replay retention capacity"
        ),
    ):
        config_module.Settings(
            internal_assertion_max_lifetime_seconds=60,
        )


def test_mutating_internal_routes_require_fresh_assertion():
    violations: list[str] = []

    for path in APP_ROOT.rglob(
        "*.py"
    ):

        source = path.read_text(
            encoding="utf-8-sig"
        )

        tree = ast.parse(
            source
        )

        for node in ast.walk(
            tree
        ):

            if not isinstance(
                node,
                (
                    ast.FunctionDef,
                    ast.AsyncFunctionDef,
                ),
            ):
                continue

            methods = _route_methods(
                node
            )

            if not (
                methods
                & MUTATING_METHODS
            ):
                continue

            names = _referenced_names(
                node
            )

            basic_internal = (
                "require_internal_service"
                in names
            )

            fresh_internal = (
                "require_fresh_internal_service"
                in names
            )

            if (
                basic_internal
                and not fresh_internal
            ):

                relative = (
                    path.relative_to(
                        APP_ROOT
                    )
                )

                violations.append(
                    f"{relative}:"
                    f"{node.lineno}:"
                    f"{node.name}"
                )

    assert not violations, (
        "Mutating internal-service routes "
        "must use "
        "require_fresh_internal_service: "
        + ", ".join(
            violations
        )
    )


def test_security_module_uses_canonical_replay_skew():
    security_path = (
        APP_ROOT
        / "core"
        / "security.py"
    )

    source = security_path.read_text(
        encoding="utf-8-sig"
    )

    assert (
        "_INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS"
        not in source
    )

    assert (
        "INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS"
        in source
    )
