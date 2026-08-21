from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal

from .authorization import AuditScope, require_audit_scope, scope_allows_location
from .repository import AuditConflictError, AuditRepositoryError, get_location
from .visit_planning import AuditVisitCreate, AuditVisitNoteCreate, AuditVisitRunStart
from .visit_repository import (
    append_visit_note,
    complete_visit_manifest,
    create_visit_manifest,
    get_visit_location,
    get_visit_manifest,
    list_visit_manifests,
    list_visit_notes,
    start_visit_run,
)

router = APIRouter(prefix="/v1/audit/visits", tags=["audit-visits"])
AuditViewer = Annotated[Principal, Depends(require_permission("module:audit:view"))]


def _raise_repository_error(exc: AuditRepositoryError) -> None:
    if isinstance(exc, AuditConflictError):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


def _assert_location_scope(
    scope: AuditScope,
    location: dict[str, object] | None,
    *,
    not_found_detail: str,
) -> dict[str, object]:
    if not location:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=not_found_detail)
    location_id = str(location.get("location_id") or "")
    region = str(location.get("region") or "") or None
    if not location_id or not scope_allows_location(
        scope,
        location_id=location_id,
        region=region,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Audit visit is outside authorized scope",
        )
    return location


async def _require_location_scope(
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
    return _assert_location_scope(scope, location, not_found_detail="Audit location not found")


async def _require_visit_scope(
    principal: Principal,
    scope: AuditScope,
    visit_manifest_id: UUID,
) -> dict[str, object]:
    location = await get_visit_location(str(principal.tenant_id), visit_manifest_id)
    return _assert_location_scope(scope, location, not_found_detail="Audit visit not found")


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_audit_visit(
    payload: AuditVisitCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:startAudit")
    await _require_location_scope(principal, scope, payload.location_id)
    try:
        return await create_visit_manifest(
            str(principal.tenant_id),
            principal.subject,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("")
async def get_audit_visits(
    principal: AuditViewer,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:audits")
    return await list_visit_manifests(
        str(principal.tenant_id),
        location_ids=scope.location_ids,
        regions=scope.regions,
        unrestricted=scope.unrestricted,
        limit=limit,
    )


@router.get("/{visit_manifest_id}")
async def get_audit_visit(
    visit_manifest_id: UUID,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "feature:audit:audits")
    await _require_visit_scope(principal, scope, visit_manifest_id)
    visit = await get_visit_manifest(str(principal.tenant_id), visit_manifest_id)
    if not visit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Audit visit not found")
    return visit


@router.post("/{visit_manifest_id}/run", status_code=status.HTTP_201_CREATED)
async def post_audit_visit_run(
    visit_manifest_id: UUID,
    payload: AuditVisitRunStart,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:startAudit")
    await _require_visit_scope(principal, scope, visit_manifest_id)
    try:
        return await start_visit_run(
            str(principal.tenant_id),
            principal.subject,
            visit_manifest_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.post("/{visit_manifest_id}/notes", status_code=status.HTTP_201_CREATED)
async def post_audit_visit_note(
    visit_manifest_id: UUID,
    payload: AuditVisitNoteCreate,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:updateAction")
    await _require_visit_scope(principal, scope, visit_manifest_id)
    try:
        return await append_visit_note(
            str(principal.tenant_id),
            principal.subject,
            visit_manifest_id,
            payload,
        )
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)


@router.get("/{visit_manifest_id}/notes")
async def get_audit_visit_notes(
    visit_manifest_id: UUID,
    principal: AuditViewer,
) -> list[dict[str, object]]:
    scope = require_audit_scope(principal, "feature:audit:audits")
    await _require_visit_scope(principal, scope, visit_manifest_id)
    return await list_visit_notes(str(principal.tenant_id), visit_manifest_id)


@router.post("/{visit_manifest_id}/complete")
async def post_complete_audit_visit(
    visit_manifest_id: UUID,
    principal: AuditViewer,
) -> dict[str, object]:
    scope = require_audit_scope(principal, "action:audit:updateAction")
    await _require_visit_scope(principal, scope, visit_manifest_id)
    try:
        return await complete_visit_manifest(str(principal.tenant_id), visit_manifest_id)
    except AuditRepositoryError as exc:
        _raise_repository_error(exc)
