from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission, resolve_permission_scope
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.execution_schemas import (
    PlanogramComplianceConsumeRequest,
    PlanogramExecutionAssignmentRequest,
    PlanogramPlanDraftRequest,
    PlanogramPlanEditRequest,
    PlanogramPlanRejectRequest,
)
from app.modules.planogram.execution_service import consume_compliance_promotion
from app.modules.planogram.repository_assignment_lifecycle import close_assignment
from app.modules.planogram.repository_execution import (
    acknowledge_assignment,
    approve_plan,
    create_assignment,
    create_plan_draft,
    list_assignments,
    list_plan_versions,
    reject_plan,
    submit_plan,
)
from app.modules.planogram.repository_plan_edit import update_plan_draft

router = APIRouter(prefix="/v1/planogram/execution", tags=["planogram-execution"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Viewer = Annotated[Principal, Depends(require_permission("module:planogram:view"))]
Editor = Annotated[Principal, Depends(require_permission("action:planogram:edit"))]
Approver = Annotated[Principal, Depends(require_permission("action:planogram:approve"))]
EvidenceConsumer = Annotated[
    Principal,
    Depends(require_permission("action:planogram:acceptFieldEvidence")),
]


def _conflict(exc: PlanogramExecutionError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)


def _ensure_store_scope(
    principal: Principal,
    permission_key: str,
    store_code: str,
) -> None:
    scope = resolve_permission_scope(principal, permission_key)
    if scope.unrestricted:
        return
    allowed = scope.values("warehouses") | scope.values("locations")
    if store_code in allowed:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Planogram permission scope does not cover this store",
    )


async def _plan_by_id(
    session: AsyncSession,
    principal: Principal,
    plan_version_id: UUID,
) -> dict[str, Any]:
    plans = await list_plan_versions(session, principal)
    match = next((row for row in plans if str(row["id"]) == str(plan_version_id)), None)
    if match is None:
        raise PlanogramExecutionError("plan_version_not_found")
    return match


async def _assignment_by_id(
    session: AsyncSession,
    principal: Principal,
    assignment_id: UUID,
) -> dict[str, Any]:
    assignments = await list_assignments(session, principal)
    match = next((row for row in assignments if str(row["id"]) == str(assignment_id)), None)
    if match is None:
        raise PlanogramExecutionError("execution_assignment_not_found")
    return match


@router.get("/plans")
async def get_execution_plans(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    items = await list_plan_versions(session, principal)
    visible: list[dict[str, Any]] = []
    for item in items:
        try:
            _ensure_store_scope(principal, "module:planogram:view", str(item["store_code"]))
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                continue
            raise
        visible.append(item)
    return {
        "count": len(visible),
        "items": visible,
        "truth_boundary": {
            "runtime_can_assert_physical_truth": False,
            "unattested_plan_can_be_approved": False,
        },
    }


@router.post("/plans", status_code=status.HTTP_201_CREATED)
async def post_execution_plan_draft(
    payload: PlanogramPlanDraftRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, Any]:
    store_code = payload.store_code.strip().upper()
    _ensure_store_scope(principal, "action:planogram:edit", store_code)
    try:
        return await create_plan_draft(
            session,
            principal,
            store_dna_version_id=payload.store_dna_version_id,
            store_code=store_code,
            source=payload.source,
            plan_payload=payload.plan_payload,
            optimizer_fingerprint=payload.optimizer_fingerprint,
        )
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.put("/plans/{plan_version_id}")
async def put_execution_plan_draft(
    plan_version_id: UUID,
    payload: PlanogramPlanEditRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, Any]:
    try:
        plan = await _plan_by_id(session, principal, plan_version_id)
        _ensure_store_scope(principal, "action:planogram:edit", str(plan["store_code"]))
        return await update_plan_draft(
            session,
            principal,
            plan_version_id,
            plan_payload=payload.plan_payload,
            optimizer_fingerprint=payload.optimizer_fingerprint,
        )
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/plans/{plan_version_id}/submit")
async def post_execution_plan_submit(
    plan_version_id: UUID,
    session: TenantSession,
    principal: Editor,
) -> dict[str, Any]:
    try:
        plan = await _plan_by_id(session, principal, plan_version_id)
        _ensure_store_scope(principal, "action:planogram:edit", str(plan["store_code"]))
        return await submit_plan(session, principal, plan_version_id)
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/plans/{plan_version_id}/approve")
async def post_execution_plan_approve(
    plan_version_id: UUID,
    session: TenantSession,
    principal: Approver,
) -> dict[str, Any]:
    try:
        plan = await _plan_by_id(session, principal, plan_version_id)
        _ensure_store_scope(principal, "action:planogram:approve", str(plan["store_code"]))
        return await approve_plan(session, principal, plan_version_id)
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/plans/{plan_version_id}/reject")
async def post_execution_plan_reject(
    plan_version_id: UUID,
    payload: PlanogramPlanRejectRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, Any]:
    try:
        plan = await _plan_by_id(session, principal, plan_version_id)
        _ensure_store_scope(principal, "action:planogram:approve", str(plan["store_code"]))
        return await reject_plan(
            session,
            principal,
            plan_version_id,
            reason=payload.reason,
        )
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.get("/assignments")
async def get_execution_assignments(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    items = await list_assignments(session, principal)
    visible: list[dict[str, Any]] = []
    for item in items:
        try:
            _ensure_store_scope(principal, "module:planogram:view", str(item["store_code"]))
        except HTTPException as exc:
            if exc.status_code == status.HTTP_403_FORBIDDEN:
                continue
            raise
        visible.append(item)
    return {"count": len(visible), "items": visible}


@router.post("/assignments", status_code=status.HTTP_201_CREATED)
async def post_execution_assignment(
    payload: PlanogramExecutionAssignmentRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, Any]:
    try:
        plan = await _plan_by_id(session, principal, payload.plan_version_id)
        _ensure_store_scope(principal, "action:planogram:approve", str(plan["store_code"]))
        return await create_assignment(
            session,
            principal,
            plan_version_id=payload.plan_version_id,
            effective_from=payload.effective_from,
            due_at=payload.due_at,
        )
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/assignments/{assignment_id}/acknowledge")
async def post_execution_assignment_acknowledge(
    assignment_id: UUID,
    session: TenantSession,
    principal: Editor,
) -> dict[str, Any]:
    try:
        assignment = await _assignment_by_id(session, principal, assignment_id)
        _ensure_store_scope(principal, "action:planogram:edit", str(assignment["store_code"]))
        return await acknowledge_assignment(session, principal, assignment_id)
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/assignments/{assignment_id}/close")
async def post_execution_assignment_close(
    assignment_id: UUID,
    session: TenantSession,
    principal: Approver,
) -> dict[str, Any]:
    try:
        assignment = await _assignment_by_id(session, principal, assignment_id)
        _ensure_store_scope(principal, "action:planogram:approve", str(assignment["store_code"]))
        return await close_assignment(session, principal, assignment_id)
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc


@router.post("/assignments/{assignment_id}/compliance")
async def post_execution_compliance(
    assignment_id: UUID,
    payload: PlanogramComplianceConsumeRequest,
    session: TenantSession,
    principal: EvidenceConsumer,
) -> dict[str, Any]:
    try:
        assignment = await _assignment_by_id(session, principal, assignment_id)
        _ensure_store_scope(
            principal,
            "action:planogram:acceptFieldEvidence",
            str(assignment["store_code"]),
        )
        return await consume_compliance_promotion(
            session,
            principal,
            assignment_id=assignment_id,
            field_promotion_id=payload.field_promotion_id,
        )
    except PlanogramExecutionError as exc:
        raise _conflict(exc) from exc
