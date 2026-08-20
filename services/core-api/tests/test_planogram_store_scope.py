from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.security import PermissionAssignment, Principal
from app.modules.planogram.access import ensure_planogram_store_scope

VIEW = "module:planogram:view"


def principal(scope: dict, *, permission: str = VIEW) -> Principal:
    return Principal(
        subject="scope-test",
        tenant_id=uuid4(),
        permissions=(permission,),
        permission_assignments=(
            PermissionAssignment(
                key=permission,
                role_key="planogram-test",
                scope=scope,
            ),
        ),
        auth_mode="oidc",
    )


@pytest.mark.parametrize(
    ("scope", "requested", "expected"),
    [
        ({"warehouses": ["fulya"]}, "FULYA", "FULYA"),
        ({"locations": ["Fulya"]}, "fulya", "FULYA"),
        ({"type": "all"}, "Any-Store", "ANY-STORE"),
    ],
)
def test_planogram_store_scope_allows_authorized_store(
    scope: dict,
    requested: str,
    expected: str,
) -> None:
    assert ensure_planogram_store_scope(
        principal(scope),
        VIEW,
        requested,
    ) == expected


@pytest.mark.parametrize(
    "scope",
    [
        {"warehouses": ["OTHER"]},
        {"cost_centers": ["FULYA"]},
        {"warehouses": []},
    ],
)
def test_planogram_store_scope_denies_unassigned_store(scope: dict) -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_planogram_store_scope(principal(scope), VIEW, "FULYA")
    assert exc.value.status_code == 403


def test_planogram_store_scope_conceals_resource_identity() -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_planogram_store_scope(
            principal({"warehouses": ["OTHER"]}),
            VIEW,
            "FULYA",
            conceal=True,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail == "Planogram resource is unavailable"


def test_planogram_store_scope_preserves_fail_closed_empty_scope() -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_planogram_store_scope(principal({}), VIEW, "FULYA")
    assert exc.value.status_code == 403


@pytest.mark.parametrize(
    "scope",
    [
        {"type": "ALL"},
        {"warehouses": "FULYA"},
        {"warehouses": [7]},
    ],
)
def test_planogram_store_scope_rejects_malformed_authority(scope: dict) -> None:
    with pytest.raises(HTTPException) as exc:
        ensure_planogram_store_scope(principal(scope), VIEW, "FULYA")
    assert exc.value.status_code == 503


def test_planogram_store_scope_requires_matching_assignment() -> None:
    actor = Principal(
        subject="scope-test",
        tenant_id=uuid4(),
        permissions=(VIEW,),
        permission_assignments=(),
        auth_mode="oidc",
    )
    with pytest.raises(HTTPException) as exc:
        ensure_planogram_store_scope(actor, VIEW, "FULYA")
    assert exc.value.status_code == 503
