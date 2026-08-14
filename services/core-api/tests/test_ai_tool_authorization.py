from __future__ import annotations

import inspect
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

import pytest

from app.core.ai_tool_authorization import (
    SCOPE_PERMISSION_KEYS,
    TOOL_REQUIRED_SCOPES,
    AiToolAccessDenied,
    AiToolPermissionScopeUnsupported,
    derive_ai_tool_capability,
)
from app.core.permission_catalog import (
    ALL_PERMISSION_KEYS,
    SYSTEM_ROLE_PERMISSIONS,
)

TENANT_A = UUID(
    "11111111-1111-4111-8111-111111111111"
)
TENANT_B = UUID(
    "22222222-2222-4222-8222-222222222222"
)


@dataclass(frozen=True)
class Assignment:
    key: str
    role_key: str
    scope: dict[str, object]


@dataclass(frozen=True)
class PrincipalStub:
    subject: str
    tenant_id: UUID
    permissions: tuple[str, ...]
    permission_assignments: tuple[Assignment, ...]


def ai_scope(*stores: str) -> dict[str, object]:
    return {
        "ai_data_scope": {
            "version": 1,
            "store_names": list(stores),
        }
    }


def principal_with(
    *permission_keys: str,
    tenant_id: UUID = TENANT_A,
    subject: str = "user-1",
    scope_by_permission: dict[
        str,
        dict[str, object],
    ]
    | None = None,
) -> PrincipalStub:
    scope_by_permission = (
        scope_by_permission or {}
    )

    return PrincipalStub(
        subject=subject,
        tenant_id=tenant_id,
        permissions=tuple(permission_keys),
        permission_assignments=tuple(
            Assignment(
                key=permission,
                role_key="super_admin",
                scope=scope_by_permission.get(
                    permission,
                    ai_scope("Fulya"),
                ),
            )
            for permission in permission_keys
        ),
    )


def test_tool_scope_contract_matches_reviewed_ai_core_tools() -> None:
    assert TOOL_REQUIRED_SCOPES == {
        "ops_kpi_query": (
            "ops:read",
        ),
        "catalog_query": (
            "catalog:read",
        ),
        "regulatory_impact_query": (
            "catalog:read",
            "legal:read",
        ),
    }


def test_ops_tool_scope_is_derived_from_permission_and_data_scope() -> None:
    ops_permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]

    capability = derive_ai_tool_capability(
        principal_with(ops_permission),
        tool="ops_kpi_query",
    )

    assert capability.granted_scopes == (
        "ops:read",
    )
    assert capability.permission_keys == (
        ops_permission,
    )
    assert capability.authorizing_roles == (
        "super_admin",
    )
    assert capability.data_scope.store_names == (
        "Fulya",
    )
    assert len(capability.data_scope_fingerprint) == 64


def test_regulatory_tool_requires_both_legal_and_catalog() -> None:
    catalog_permission = SCOPE_PERMISSION_KEYS[
        "catalog:read"
    ]
    legal_permission = SCOPE_PERMISSION_KEYS[
        "legal:read"
    ]

    with pytest.raises(
        AiToolAccessDenied
    ) as exc_info:
        derive_ai_tool_capability(
            principal_with(
                catalog_permission
            ),
            tool="regulatory_impact_query",
        )

    assert exc_info.value.missing_permissions == (
        legal_permission,
    )

    capability = derive_ai_tool_capability(
        principal_with(
            catalog_permission,
            legal_permission,
            scope_by_permission={
                catalog_permission: ai_scope(
                    "Fulya",
                    "Anka",
                ),
                legal_permission: ai_scope(
                    "Fulya",
                    "Dicle",
                ),
            },
        ),
        tool="regulatory_impact_query",
    )

    assert capability.granted_scopes == (
        "catalog:read",
        "legal:read",
    )
    assert capability.data_scope.store_names == (
        "Fulya",
    )


def test_permission_projection_without_assignment_fails_closed() -> None:
    permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]

    principal = PrincipalStub(
        subject="user-1",
        tenant_id=TENANT_A,
        permissions=(permission,),
        permission_assignments=(),
    )

    with pytest.raises(
        AiToolAccessDenied
    ):
        derive_ai_tool_capability(
            principal,
            tool="ops_kpi_query",
        )


def test_empty_or_legacy_permission_scope_is_not_silently_widened() -> None:
    permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]

    for scope in (
        {},
        {"stores": ["Fulya"]},
        {
            "ai_data_scope": {
                "version": 1,
                "store_names": ["*"],
            }
        },
    ):
        principal = principal_with(
            permission,
            scope_by_permission={
                permission: scope,
            },
        )

        with pytest.raises(
            AiToolPermissionScopeUnsupported
        ):
            derive_ai_tool_capability(
                principal,
                tool="ops_kpi_query",
            )


def test_same_permission_roles_union_their_explicit_data_scope() -> None:
    permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]
    principal = PrincipalStub(
        subject="user-1",
        tenant_id=TENANT_A,
        permissions=(permission,),
        permission_assignments=(
            Assignment(
                key=permission,
                role_key="ops_west",
                scope=ai_scope("Fulya", "Anka"),
            ),
            Assignment(
                key=permission,
                role_key="ops_east",
                scope=ai_scope("Dicle"),
            ),
        ),
    )

    capability = derive_ai_tool_capability(
        principal,
        tool="ops_kpi_query",
    )

    assert capability.authorizing_roles == (
        "ops_east",
        "ops_west",
    )
    assert capability.data_scope.store_names == (
        "Anka",
        "Dicle",
        "Fulya",
    )


def test_caller_cannot_supply_or_widen_granted_or_data_scope() -> None:
    signature = inspect.signature(
        derive_ai_tool_capability
    )

    assert "granted_scopes" not in (
        signature.parameters
    )
    assert "requested_scopes" not in (
        signature.parameters
    )
    assert "data_scope" not in signature.parameters
    assert "store_names" not in signature.parameters


def test_authorization_fingerprint_binds_actor_tenant_tool_and_data_scope() -> None:
    ops_permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]
    catalog_permission = SCOPE_PERMISSION_KEYS[
        "catalog:read"
    ]

    first = derive_ai_tool_capability(
        principal_with(
            ops_permission,
            subject="user-1",
        ),
        tool="ops_kpi_query",
    )

    changed_actor = derive_ai_tool_capability(
        principal_with(
            ops_permission,
            subject="user-2",
        ),
        tool="ops_kpi_query",
    )

    changed_tenant = derive_ai_tool_capability(
        principal_with(
            ops_permission,
            tenant_id=TENANT_B,
        ),
        tool="ops_kpi_query",
    )

    changed_tool = derive_ai_tool_capability(
        principal_with(
            catalog_permission,
        ),
        tool="catalog_query",
    )

    changed_scope = derive_ai_tool_capability(
        principal_with(
            ops_permission,
            scope_by_permission={
                ops_permission: ai_scope("Anka"),
            },
        ),
        tool="ops_kpi_query",
    )

    fingerprints = {
        first.authorization_fingerprint,
        changed_actor.authorization_fingerprint,
        changed_tenant.authorization_fingerprint,
        changed_tool.authorization_fingerprint,
        changed_scope.authorization_fingerprint,
    }

    assert len(fingerprints) == 5

    for fingerprint in fingerprints:
        assert len(fingerprint) == 64
        int(fingerprint, 16)


def test_ai_permissions_are_known_and_default_fail_closed() -> None:
    ai_permissions = set(
        SCOPE_PERMISSION_KEYS.values()
    )

    assert ai_permissions <= ALL_PERMISSION_KEYS
    assert ai_permissions <= (
        SYSTEM_ROLE_PERMISSIONS[
            "super_admin"
        ]
    )

    assert ai_permissions.isdisjoint(
        SYSTEM_ROLE_PERMISSIONS[
            "platform_admin"
        ]
    )
    assert ai_permissions.isdisjoint(
        SYSTEM_ROLE_PERMISSIONS[
            "operator"
        ]
    )
    assert ai_permissions.isdisjoint(
        SYSTEM_ROLE_PERMISSIONS[
            "viewer"
        ]
    )


def test_0009_migration_grants_permission_but_not_global_data_scope() -> None:
    migration = (
        Path(__file__).resolve().parents[1]
        / "alembic"
        / "versions"
        / "0009_ai_tool_permissions.py"
    ).read_text(
        encoding="utf-8-sig"
    )

    for permission in (
        SCOPE_PERMISSION_KEYS.values()
    ):
        assert permission in migration

    assert "r.key = 'super_admin'" in migration
    assert "r.key = 'platform_admin'" not in migration
    assert "r.key = 'operator'" not in migration
    assert "r.key = 'viewer'" not in migration

    # 0009 deliberately does not invent store scope. Until an explicit
    # ai_data_scope is configured, capability derivation fails closed.
    assert "ai_data_scope" not in migration
