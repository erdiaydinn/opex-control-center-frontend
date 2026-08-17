from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException

from app.core.security import PermissionAssignment, Principal
from app.modules.planogram import view_router

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ASSIGNMENT_ID = UUID("22222222-2222-2222-2222-222222222222")


def _principal(scope: dict[str, object]) -> Principal:
    return Principal(
        subject="viewer@example.test",
        tenant_id=TENANT_ID,
        permissions=("module:planogram:view",),
        permission_assignments=(
            PermissionAssignment(
                key="module:planogram:view",
                role_key="planogram_viewer",
                scope=scope,
            ),
        ),
        auth_mode="development",
    )


@pytest.mark.asyncio
async def test_assignment_view_returns_exact_persisted_payload(monkeypatch) -> None:
    async def fake_get_assignment_plan(session, principal, assignment_id):
        assert session is not None
        assert principal.tenant_id == TENANT_ID
        assert assignment_id == ASSIGNMENT_ID
        return {
            "assignment_id": ASSIGNMENT_ID,
            "plan_version_id": UUID("33333333-3333-3333-3333-333333333333"),
            "store_code": "STORE-A",
            "assignment_status": "assigned",
            "plan_status": "approved",
            "physical_truth_attested": True,
            "plan_payload": {"planogram": {"store_code": "STORE-A", "aisles": []}},
            "plan_fingerprint": "a" * 64,
        }

    monkeypatch.setattr(view_router, "get_assignment_plan", fake_get_assignment_plan)
    result = await view_router.get_assignment_plan_view(
        ASSIGNMENT_ID,
        object(),
        _principal({"warehouses": ["STORE-A"]}),
    )

    assert result["plan_payload"]["planogram"]["store_code"] == "STORE-A"
    assert result["physical_truth_attested"] is True
    assert result["truth_boundary"] == {
        "visualization_read_only": True,
        "plan_payload_is_exact_assignment_version": True,
        "runtime_can_assert_physical_truth": False,
    }


@pytest.mark.asyncio
async def test_assignment_view_fails_closed_outside_store_scope(monkeypatch) -> None:
    async def fake_get_assignment_plan(session, principal, assignment_id):
        return {
            "assignment_id": assignment_id,
            "store_code": "STORE-B",
            "plan_payload": {"planogram": {"store_code": "STORE-B", "aisles": []}},
        }

    monkeypatch.setattr(view_router, "get_assignment_plan", fake_get_assignment_plan)
    with pytest.raises(HTTPException) as exc_info:
        await view_router.get_assignment_plan_view(
            ASSIGNMENT_ID,
            object(),
            _principal({"warehouses": ["STORE-A"]}),
        )
    assert exc_info.value.status_code == 403


def test_assignment_view_route_is_read_only_get() -> None:
    route = next(
        item
        for item in view_router.router.routes
        if item.path.endswith("/assignments/{assignment_id}/view")
    )
    assert route.methods == {"GET"}
