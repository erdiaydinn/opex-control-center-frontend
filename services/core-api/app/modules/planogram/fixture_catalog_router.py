from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.planogram.fixture_catalog import (
    FixtureCatalogStateError,
    canonical_fixture_record,
    fixture_record_fingerprint,
)
from app.modules.planogram.fixture_catalog_schemas import (
    PlanogramFixtureCatalogDecisionRequest,
    PlanogramFixtureCatalogDraftRequest,
    PlanogramFixtureCatalogRejectRequest,
    PlanogramFixtureCatalogRevisionRequest,
)
from app.modules.planogram.repository_fixture_catalog import (
    approve_fixture_catalog,
    create_fixture_catalog_draft,
    list_fixture_catalog_versions,
    reject_fixture_catalog,
    revise_fixture_catalog,
    submit_fixture_catalog,
    update_fixture_catalog_draft,
)

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]

Viewer = Annotated[Principal, Depends(require_permission("module:planogram:view"))]
Creator = Annotated[Principal, Depends(require_permission("action:planogram:create"))]
Editor = Annotated[Principal, Depends(require_permission("action:planogram:edit"))]
Approver = Annotated[Principal, Depends(require_permission("action:planogram:approve"))]


def _conflict(exc: FixtureCatalogStateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)


@router.get("/fixture-catalog/workspace")
async def get_fixture_catalog_workspace(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    permissions = set(principal.permissions)
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "authority": "server_authoritative_fixture_catalog_v1",
        "capabilities": {
            "create": "action:planogram:create" in permissions,
            "edit": "action:planogram:edit" in permissions,
            "submit": "action:planogram:edit" in permissions,
            "approve": "action:planogram:approve" in permissions,
        },
        "approval_policy": {
            "tenant_scoped": True,
            "maker_checker_required": True,
            "approved_versions_immutable": True,
            "approved_record_fingerprint_bound": True,
            "fixture_approval_grants_store_dna_authority": False,
            "fixture_approval_grants_production_release": False,
        },
        "versions": await list_fixture_catalog_versions(session, principal),
    }


@router.post("/fixture-catalog", status_code=status.HTTP_201_CREATED)
async def post_fixture_catalog_draft(
    payload: PlanogramFixtureCatalogDraftRequest,
    session: TenantSession,
    principal: Creator,
) -> dict[str, object]:
    try:
        record = canonical_fixture_record(payload.model_dump(mode="python"))
        return await create_fixture_catalog_draft(
            session,
            principal,
            fixture_code=record["fixture_code"],
            fixture_name=record["fixture_name"],
            record=record,
            record_sha256=fixture_record_fingerprint(record),
        )
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.put("/fixture-catalog/{version_id}")
async def put_fixture_catalog_draft(
    version_id: UUID,
    payload: PlanogramFixtureCatalogDraftRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        record = canonical_fixture_record(payload.model_dump(mode="python"))
        return await update_fixture_catalog_draft(
            session,
            principal,
            version_id,
            fixture_code=record["fixture_code"],
            fixture_name=record["fixture_name"],
            record=record,
            record_sha256=fixture_record_fingerprint(record),
        )
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/fixture-catalog/{version_id}/submit")
async def post_fixture_catalog_submit(
    version_id: UUID,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        return await submit_fixture_catalog(session, principal, version_id)
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc


@router.post("/fixture-catalog/{version_id}/approve")
async def post_fixture_catalog_approve(
    version_id: UUID,
    payload: PlanogramFixtureCatalogDecisionRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, object]:
    try:
        return await approve_fixture_catalog(session, principal, version_id, note=payload.note)
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc


@router.post("/fixture-catalog/{version_id}/reject")
async def post_fixture_catalog_reject(
    version_id: UUID,
    payload: PlanogramFixtureCatalogRejectRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, object]:
    try:
        return await reject_fixture_catalog(session, principal, version_id, reason=payload.reason)
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc


@router.post("/fixture-catalog/{version_id}/revise", status_code=status.HTTP_201_CREATED)
async def post_fixture_catalog_revise(
    version_id: UUID,
    payload: PlanogramFixtureCatalogRevisionRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        return await revise_fixture_catalog(session, principal, version_id, reason=payload.reason)
    except FixtureCatalogStateError as exc:
        raise _conflict(exc) from exc
