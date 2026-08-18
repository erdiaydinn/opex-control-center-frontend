from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from app.core.ai_tool_authorization import (
    SCOPE_PERMISSION_KEYS,
    AiToolAccessDenied,
    AiToolPermissionScopeUnsupported,
)
from app.core.operational_tool_authority import (
    OPERATIONAL_TOOL_REGISTRY,
    derive_operational_tool_capability,
)
from app.core.permission_catalog import module_permission

TENANT = UUID("11111111-1111-4111-8111-111111111111")


@dataclass(frozen=True)
class Assignment:
    key: str
    role_key: str
    scope: dict[str, object]


@dataclass(frozen=True)
class Principal:
    subject: str
    tenant_id: UUID
    permissions: tuple[str, ...]
    permission_assignments: tuple[Assignment, ...]


def scope(*stores: str) -> dict[str, object]:
    return {"ai_data_scope": {"version": 1, "store_names": list(stores)}}


def principal(
    module: str,
    *,
    assignment: bool = True,
    ai_stores: tuple[str, ...] = ("Fulya", "Besiktas"),
    module_scope: dict[str, object] | None = None,
) -> Principal:
    ops = SCOPE_PERMISSION_KEYS["ops:read"]
    module_key = module_permission(module)
    assignments = [Assignment(ops, "ops_reader", scope(*ai_stores))]
    if assignment:
        assignments.append(
            Assignment(module_key, "module_reader", module_scope or {})
        )
    return Principal(
        subject="user",
        tenant_id=TENANT,
        permissions=(ops, module_key),
        permission_assignments=tuple(assignments),
    )


def test_registry_covers_master34_modules() -> None:
    assert set(OPERATIONAL_TOOL_REGISTRY) == {
        "glossary_lookup",
        "field_read",
        "workforce_read",
        "inventory_read",
        "planogram_read",
        "dockos_read",
        "budget_read",
        "academy_read",
        "insight_read",
    }
    assert all(spec.risk == "read_only" for spec in OPERATIONAL_TOOL_REGISTRY.values())


def test_budget_tool_requires_both_ai_scope_and_budget_entitlement() -> None:
    capability = derive_operational_tool_capability(
        principal("budget"),
        tool="budget_read",
    )
    assert capability.module == "budget"
    assert capability.data_scope.store_names == ("Besiktas", "Fulya")
    assert len(capability.authorization_fingerprint) == 64
    assert len(capability.data_scope_fingerprint) == 64

    with pytest.raises(AiToolAccessDenied):
        derive_operational_tool_capability(
            principal("budget", assignment=False),
            tool="budget_read",
        )


def test_cross_module_permission_cannot_be_reused() -> None:
    with pytest.raises(AiToolAccessDenied):
        derive_operational_tool_capability(
            principal("academy"),
            tool="budget_read",
        )


def test_module_scope_can_only_narrow_base_ai_data_scope() -> None:
    capability = derive_operational_tool_capability(
        principal("budget", module_scope=scope("Fulya")),
        tool="budget_read",
    )
    assert capability.data_scope.store_names == ("Fulya",)


def test_non_overlapping_or_unknown_module_scope_fails_closed() -> None:
    with pytest.raises(AiToolPermissionScopeUnsupported):
        derive_operational_tool_capability(
            principal("budget", module_scope=scope("Kadikoy")),
            tool="budget_read",
        )

    with pytest.raises(AiToolPermissionScopeUnsupported):
        derive_operational_tool_capability(
            principal("budget", module_scope={"stores": ["Fulya"]}),
            tool="budget_read",
        )
