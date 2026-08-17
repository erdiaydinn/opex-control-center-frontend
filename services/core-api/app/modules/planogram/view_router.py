from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission, resolve_permission_scope
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.repository_execution import get_assignment_plan

router = APIRouter(prefix="/v1/planogram/execution", tags=["planogram-experience"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Viewer = Annotated[Principal, Depends(require_permission("module:planogram:view"))]


def _ensure_view_store_scope(principal: Principal, store_code: str) -> None:
    scope = resolve_permission_scope(principal, "module:planogram:view")
    if scope.unrestricted:
        return
    allowed = scope.values("warehouses") | scope.values("locations")
    if store_code in allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Planogram permission scope does not cover this store",
    )


@router.get("/assignments/{assignment_id}/view")
async def get_assignment_plan_view(
    assignment_id: UUID,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    """Return the exact persisted plan behind one visible assignment.

    The endpoint is read-only and intentionally reuses the security-reviewed
    Master-26 assignment-plan query. Visualization never changes plan status,
    attestation or assignment authority.
    """
    try:
        plan = await get_assignment_plan(session, principal, assignment_id)
    except PlanogramExecutionError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.code,
        ) from exc

    _ensure_view_store_scope(principal, str(plan["store_code"]))
    return {
        **plan,
        "truth_boundary": {
            "visualization_read_only": True,
            "plan_payload_is_exact_assignment_version": True,
            "runtime_can_assert_physical_truth": False,
        },
    }
