from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal

from .accountability import (
    assign_location_manager,
    get_location_manager_assignment,
    list_location_manager_assignments,
)
from .assurance import (
    append_auditor_decision_and_route,
    auditor_assurance_summary,
    get_assurance_case,
    list_assurance_cases,
    manager_decide_assurance_case,
    standards_decide_assurance_case,
)
from .authorization import AuditScope, require_audit_scope, scope_allows_location
from .evidence_binding import bind_server_evidence_to_redaction_receipt
from .evidence_binding_schemas import AuditEvidenceBindingCreate
from .repository import (
    AuditConflictError,
    AuditRepositoryError,
    activate_program,
    append_assurance_review,
    create_action,
    create_program,
    get_action,
    get_location,
    list_actions,
    list_programs,
    list_runs,
    update_action,
)
from .resource_scope import get_action_location, get_run_location
from .run_authority import start_authoritative_run
from .schemas import (
    AuditActionCreate,
    AuditActionUpdate,
    AuditAssuranceReviewCreate,
    AuditDecisionEventCreate,
    AuditLocationManagerAssignmentCreate,
    AuditManagerAssuranceDecision,
    AuditProgramActivate,
    AuditProgramCreate,
    AuditRunStart,
    AuditStandardsAssuranceDecision,
)

router = APIRouter(prefix="/v1/audit", tags=["audit"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


def _raise_repository_error(exc: AuditRepositoryError) -> None:
    if isinstance(exc, AuditConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=str(exc),
    ) from exc


def _require_resolved_resource_scope(
    scope: AuditScope,
    location: dict[str, object] | None,
    *,
    not_found_detail: str,
) -> dict[str, object]:
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=not_found_detail,
        )
    location_id = str(location.get("location_id") or "")
    region = str(location.get("region") or "") or None
    if not location_id or not scope_allows_location(
        scope,
        location_id=location_id,
        region=region,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit resource is outside authorized scope",
        )
    return location


async def _require_location(
    principal: Principal,
    scope: AuditScope,
    location_id: str,
) -> dict[str, object]:
    location = await get_location(str(principal.tenant_id), location_id)
    if not location or not bool(location.get("active")):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audit location not found",
        )
    return _require_resolved_resource_scope(
        scope,
        location,
        not_found_detail="Audit location not found",
    )


async def _require_run_scope(
    principal: Principal,
    scope: AuditScope,
    audit_run_id: UUID,
) -> dict[str, object]:
    location = await get_run_location(str(principal.tenant_id), audit_run_id)
    return _require_resolved_resource_scope(
        scope,
        location,
        not_found_detail="Audit run not found",
    )


async def _require_action_scope(
    principal: Principal,
    scope: AuditScope,
    action_id: UUID,
) -> dict[str, object]:
    location = await get_action_location(str(principal.tenant_id), action_id)
    return _require_resolved_resource_scope(
        scope,
        location,
        not_found_detail="Audit action not found",
    )


async def _require_assurance_case_scope(
    principal: Principal,
    scope: AuditScope,
    case_id: UUID,
) -> dict[str, object]:
    case = await get_assurance_case(str(principal.tenant_id), case_id)
    return _require_resolved_resource_scope(
        scope,
        case,
        not_found_detail="Audit assurance case not found",
    )


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
        return await activate_program(
            str(principal.tenant_id),
            program_key,
            version,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("/locations/manager-assignments")
async def get_location_manager_assignments(
    principal: AuditViewer,
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:locations")
    return await list_location_manager_assignments(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
    )


@router.get("/locations/{location_id}/manager-assignment")
async def get_location_manager(
    location_id: str,
    principal: AuditViewer,
) -> dict[str, object] | None:
    scope = require_audit_scope(principal, "feature:audit:locations")
    await _require_location(principal, scope, location_id)
    return await get_location_manager_assignment(str(principal.tenant_id), location_id)


@router.post("/locations/{location_id}/manager-assignment")
async def post_location_manager_assignment(
    location_id: str,
    payload: AuditLocationManagerAssignmentCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:manageLocations")
    await _require_location(principal, scope, location_id)
    try:
        return await assign_location_manager(
            str(principal.tenant_id),
            principal.subject,
            location_id,
            payload,
        )
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
        return await start_authoritative_run(
            str(principal.tenant_id),
            principal.subject,
            payload,
        )
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


@router.post(
    "/runs/{audit_run_id}/redaction-receipts",
    status_code=status.HTTP_201_CREATED,
)
async def post_redaction_receipt(
    audit_run_id: UUID,
    payload: AuditEvidenceBindingCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:submitEvidence")
    await _require_run_scope(principal, scope, audit_run_id)
    try:
        return await bind_server_evidence_to_redaction_receipt(
            str(principal.tenant_id),
            audit_run_id,
            field_evidence_receipt_id=payload.field_evidence_receipt_id,
            source_fingerprint=payload.source_fingerprint,
            privacy_policy_version=payload.privacy_policy_version,
            detector_model_ref=payload.detector_model_ref,
            device_id=payload.device_id,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post(
    "/runs/{audit_run_id}/auditor-decisions",
    status_code=status.HTTP_201_CREATED,
)
async def post_auditor_decision(
    audit_run_id: UUID,
    payload: AuditDecisionEventCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:decideItem")
    await _require_run_scope(principal, scope, audit_run_id)
    if payload.decision_source != "AUDITOR":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Public auditor endpoint cannot assert AI/manager/standards authority",
        )
    try:
        return await append_auditor_decision_and_route(
            str(principal.tenant_id),
            principal.subject,
            audit_run_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/runs/{audit_run_id}/actions", status_code=status.HTTP_201_CREATED)
async def post_audit_action(
    audit_run_id: UUID,
    payload: AuditActionCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:createAction")
    await _require_run_scope(principal, scope, audit_run_id)
    try:
        return await create_action(
            str(principal.tenant_id),
            principal.subject,
            audit_run_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("/actions")
async def get_audit_actions(
    principal: AuditViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:actions")
    return await list_actions(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
        limit=limit,
    )


@router.get("/actions/{action_id}")
async def get_audit_action(
    action_id: UUID,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "feature:audit:actions")
    await _require_action_scope(principal, scope, action_id)
    action = await get_action(str(principal.tenant_id), action_id)
    if not action:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit action not found")
    return action


@router.patch("/actions/{action_id}")
async def patch_audit_action(
    action_id: UUID,
    payload: AuditActionUpdate,
    principal: AuditViewer,
) -> dict[str, object]:
    if payload.status == "ai_verified":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Public action endpoint cannot assert AI verification authority",
        )
    permission = (
        "action:audit:verifyAction"
        if payload.status in {"human_verified", "closed"}
        else "action:audit:updateAction"
    )
    scope = require_audit_scope(principal, permission)
    await _require_action_scope(principal, scope, action_id)
    try:
        return await update_action(str(principal.tenant_id), action_id, payload)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("/assurance/cases")
async def get_assurance_cases(
    principal: AuditViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:assurance")
    return await list_assurance_cases(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
        limit=limit,
    )


@router.get("/assurance/auditors")
async def get_auditor_assurance_summary(
    principal: AuditViewer,
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:assurance")
    return await auditor_assurance_summary(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
    )


@router.post("/assurance/cases/{case_id}/manager-decision")
async def post_manager_assurance_decision(
    case_id: UUID,
    payload: AuditManagerAssuranceDecision,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:reviewDisagreement")
    await _require_assurance_case_scope(principal, scope, case_id)
    try:
        return await manager_decide_assurance_case(
            str(principal.tenant_id),
            principal.subject,
            case_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/assurance/cases/{case_id}/standards-decision")
async def post_standards_assurance_decision(
    case_id: UUID,
    payload: AuditStandardsAssuranceDecision,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:manageStandards")
    await _require_assurance_case_scope(principal, scope, case_id)
    try:
        return await standards_decide_assurance_case(
            str(principal.tenant_id),
            principal.subject,
            case_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post(
    "/runs/{audit_run_id}/assurance-reviews",
    status_code=status.HTTP_201_CREATED,
)
async def post_assurance_review(
    audit_run_id: UUID,
    payload: AuditAssuranceReviewCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    """Legacy append-only review endpoint; current-state routing uses assurance cases."""

    standards_review = payload.state == "OPERATIONS_STANDARDS_REVIEW"
    permission = (
        "action:audit:manageStandards"
        if standards_review
        else "action:audit:reviewDisagreement"
    )
    scope = require_audit_scope(principal, permission)
    await _require_run_scope(principal, scope, audit_run_id)
    try:
        return await append_assurance_review(
            str(principal.tenant_id),
            principal.subject,
            audit_run_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)
