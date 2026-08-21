from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.authorization import resolve_permission_scope
from app.core.localization import (
    SUPPORTED_LOCALES,
    canonicalize_locale,
    resolve_accept_language,
)
from app.core.security import PermissionAssignment, Principal


def _principal(
    *assignments: PermissionAssignment, permissions: tuple[str, ...] | None = None
) -> Principal:
    permission_keys = permissions or tuple(sorted({assignment.key for assignment in assignments}))
    return Principal(
        subject="subject-a",
        tenant_id=UUID("11111111-1111-1111-1111-111111111111"),
        roles=("field_manager",),
        permissions=permission_keys,
        permission_assignments=assignments,
        auth_mode="oidc",
    )


def test_core_scope_unions_db_authoritative_dimensions():
    permission = "module:field_intelligence:view"
    principal = _principal(
        PermissionAssignment(
            key=permission,
            role_key="region-role",
            scope={"regions": ["Marmara", "Ege"]},
        ),
        PermissionAssignment(
            key=permission,
            role_key="warehouse-role",
            scope={"warehouses": ["FULYA", "ICERENKOY"]},
        ),
    )

    scope = resolve_permission_scope(principal, permission)

    assert scope.unrestricted is False
    assert scope.values("regions") == frozenset({"Marmara", "Ege"})
    assert scope.values("warehouses") == frozenset({"FULYA", "ICERENKOY"})
    assert scope.role_keys == frozenset({"region-role", "warehouse-role"})


def test_core_scope_centrally_normalizes_legacy_budget_scope():
    permission = "module:budget:view"
    center_a = "11111111-1111-1111-1111-111111111112"
    center_b = "11111111-1111-1111-1111-111111111113"
    principal = _principal(
        PermissionAssignment(
            key=permission,
            role_key="budget-viewer",
            scope={
                "all_cost_centers": False,
                "cost_center_ids": [center_a, center_b],
            },
        )
    )

    scope = resolve_permission_scope(principal, permission)

    assert scope.unrestricted is False
    assert scope.values("cost_center_ids") == frozenset({center_a, center_b})


def test_core_scope_centrally_normalizes_legacy_budget_all_scope():
    permission = "module:budget:view"
    principal = _principal(
        PermissionAssignment(
            key=permission,
            role_key="budget-admin",
            scope={"all_cost_centers": True, "cost_center_ids": []},
        )
    )

    scope = resolve_permission_scope(principal, permission)

    assert scope.unrestricted is True


def test_core_scope_accepts_only_exact_all_grant():
    permission = "module:field_intelligence:view"
    principal = _principal(
        PermissionAssignment(
            key=permission,
            role_key="bad-role",
            scope={"type": "all", "warehouses": ["SHOULD_NOT_BE_MERGED"]},
        )
    )

    with pytest.raises(HTTPException) as captured:
        resolve_permission_scope(principal, permission)

    assert captured.value.status_code == 503


def test_core_scope_fails_closed_when_flat_permission_has_no_assignment():
    permission = "module:field_intelligence:view"
    principal = _principal(permissions=(permission,))

    with pytest.raises(HTTPException) as captured:
        resolve_permission_scope(principal, permission)

    assert captured.value.status_code == 503


def test_core_scope_denies_missing_permission():
    principal = _principal()

    with pytest.raises(HTTPException) as captured:
        resolve_permission_scope(principal, "module:field_intelligence:view")

    assert captured.value.status_code == 403


def test_locale_contract_is_single_ten_language_matrix():
    assert SUPPORTED_LOCALES == (
        "tr",
        "en",
        "de",
        "ar",
        "fr",
        "es",
        "it",
        "nl",
        "pl",
        "pt-BR",
    )
    assert canonicalize_locale("pt-br") == "pt-BR"
    assert canonicalize_locale("de-DE") == "de"


def test_accept_language_uses_quality_and_rtl_from_core_contract():
    context = resolve_accept_language("de-DE;q=0.7, ar;q=0.9, en;q=0.8")
    assert context.locale == "ar"
    assert context.rtl is True
    assert context.source == "accept-language"


def test_unsupported_accept_language_fails_to_safe_default():
    context = resolve_accept_language("ja-JP, zh-CN;q=0.9")
    assert context.locale == "en"
    assert context.rtl is False
    assert context.source == "default"
