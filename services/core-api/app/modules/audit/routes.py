from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal

from .authorization import AuditScope, require_audit_scope, scope_allows_location
from .repository import (
    AuditConflictError,
    AuditRepositoryError,
    activate_program,
    append_assurance_review,
    append_decision_event,
    append_redaction_receipt,
    create_action,
    create_program,
    get_location,
    list_programs,
    list_runs,
    start_run,
    update_action,
)
from .schemas import (
    AuditActionCreate,
    AuditActionUpdate,
    AuditAssuranceReviewCreate,
    AuditDecisionEventCreate,
    AuditProgramActivate,
    AuditProgramCreate,
    AuditRedactionReceiptCreate,
    AuditRunStart,
)

router = APIRouter(prefix="/v1/audit", tags=["audit"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


def _raise_repository_error(exc: AuditRepositoryError) -> None:
    if isinstance(exc, AuditConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


async def _require_location(
    principal: Principal,
    scope: AuditScope,
    location_id: str,
) -> dict[str, object]:
    location = await get_location(str(principal.tenant_id), location_id)
    if not location or not bool(location.get("active")):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit location not found")
    if not scope_allows_location(
        scope,
        location_id=location_id,
        region=str(location.get("region") or "") or None,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit location is outside authorized scope",
        )
    return location


@router.get("/programs")
async def get_audit_programs(principal: AuditViewer) -> list[dict[str, object]]:
    return await list_programs(str(principal.tenant_id))


@router.post("/programs", status_code=status.HTTP_201_CREATED)
async def post_audit_program(
    payload: AuditProgramCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    require_audit_scope(principal, "action:audit:manageStandards")
    try:
        return await create_program(str(principal.tenant_id), principal.subject, payload)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/programs/{program_key}/{version}/activate")
async def post_activate_audit_program(
    program_key: str,
    version: int,
    payload: AuditProgramActivate,
    principal: AuditViewer,
) -> dict[str, object]:
    require_audit_scope(principal, "action:audit:manageStandards")
    try:
        return await activate_program(str(principal.tenant_id), program_key, version, payload)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/runs", status_code=status.HTTP_201_CREATED)
async def post_audit_run(
    payload: AuditRunStart,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:startAudit")
    await _require_location(principal, scope, payload.location_id)
    try:
        return await start_run(str(principal.tenant_id), principal.subject, payload)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("/runs")
async def get_audit_runs(
    principal: AuditViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "module:audit:view")
    return await list_runs(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
        limit=limit,
    )


@router.post("/runs/{audit_run_id}/redaction-receipts", status_code=status.HTTP_201_CREATED)
async def post_redaction_receipt(
    audit_run_id: UUID,
    payload: AuditRedactionReceiptCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:submitEvidence")
    await _require_location(principal, scope, payload.location_id)
    try:
        receipt = await append_redaction_receipt(
            str(principal.tenant_id), audit_run_id, payload
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)
    return {
        **receipt,
        "client_redaction_received": True,
        "server_privacy_verified": False,
        "vision_inference_authorized": False,
    }


@router.post("/runs/{audit_run_id}/auditor-decisions", status_code=status.HTTP_201_CREATED)
async def post_auditor_decision(
    audit_run_id: UUID,
    payload: AuditDecisionEventCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    require_audit_scope(principal, "action:audit:decideItem")
    if payload.decision_source != "AUDITOR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Public auditor endpoint cannot assert AI/manager/standards authority",
        )
    try:
        return await append_decision_event(
            str(principal.tenant_id), principal.subject, audit_run_id, payload
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/runs/{audit_run_id}/actions", status_code=status.HTTP_201_CREATED)
async def post_audit_action(
    audit_run_id: UUID,
    payload: AuditActionCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    require_audit_scope(principal, "action:audit:createAction")
    try:
        return await create_action(
            str(principal.tenant_id), principal.subject, audit_run_id, payload
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.patch("/actions/{action_id}")
async def patch_audit_action(
    action_id: UUID,
    payload: AuditActionUpdate,
    principal: AuditViewer,
) -> dict[str, object]:
    permission = (
        "action:audit:verifyAction"
        if payload.status in {"ai_verified", "human_verified", "closed"}
        else "action:audit:updateAction"
    )
    require_audit_scope(principal, permission)
    try:
        return await update_action(str(principal.tenant_id), action_id, payload)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/runs/{audit_run_id}/assurance-reviews", status_code=status.HTTP_201_CREATED)
async def post_assurance_review(
    audit_run_id: UUID,
    payload: AuditAssuranceReviewCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    require_audit_scope(principal, "action:audit:reviewDisagreement")
    if payload.state == "OPERATIONS_STANDARDS_REVIEW" and "audit_standards" not in principal.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operations Standards review requires Audit Standards role",
        )
    try:
        return await append_assurance_review(
            str(principal.tenant_id), principal.subject, audit_run_id, payload
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)
