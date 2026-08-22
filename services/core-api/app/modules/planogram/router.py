from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.planogram.access import ensure_planogram_store_scope
from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    engine_status,
    generate_preview,
)
from app.modules.planogram.repository_store_dna import (
    approve_store_dna,
    create_store_dna_draft,
    get_approved_store_dna,
    list_store_dna_versions,
    reject_store_dna,
    revise_store_dna,
    submit_store_dna,
    update_store_dna_draft,
)
from app.modules.planogram.schemas import (
    PlanogramPreviewRequest,
    PlanogramStoreDnaApproveRequest,
    PlanogramStoreDnaDraftRequest,
    PlanogramStoreDnaRejectRequest,
    PlanogramStoreDnaRevisionRequest,
    PlanogramStoreScanPreviewRequest,
)
from app.modules.planogram.store_dna import (
    DEFAULT_AISLE_COUNT,
    DEFAULT_MODULES_PER_SIDE,
    DEFAULT_PALLET_COUNT,
    DEFAULT_SHELVES_PER_MODULE,
    StoreDnaStateError,
    build_store_dna_configuration,
    configuration_fingerprint,
    geometry_attested,
    summarize_store_dna,
)
from app.modules.planogram.store_scan import normalize_store_scan

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]

Viewer = Annotated[
    Principal,
    Depends(require_permission("module:planogram:view")),
]
Creator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]
Editor = Annotated[
    Principal,
    Depends(require_permission("action:planogram:edit")),
]
Approver = Annotated[
    Principal,
    Depends(require_permission("action:planogram:approve")),
]

REQUIRED_EVIDENCE = (
    "approved_sku_dimensions",
    "product_image_linkage",
    "store_dna",
    "fixture_geometry_capacity",
    "physical_layout_aisle",
    "pallet_fixture_authority",
)


def _engine_or_503() -> dict[str, object]:
    try:
        return engine_status()
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical Planogram engine is unavailable",
        ) from exc


def _store_dna_conflict(exc: StoreDnaStateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)


@router.get("/readiness")
async def get_planogram_readiness(principal: Viewer) -> dict[str, object]:
    """Expose software readiness without inventing physical production truth."""
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "engine": _engine_or_503(),
        "authority_state": "server_store_dna_lifecycle_available_physical_truth_incomplete",
        "production_ready": False,
        "publishable": False,
        "solver_optimizer_allowed": False,
        "physical_truth": {
            "server_attested": False,
            "required_evidence": list(REQUIRED_EVIDENCE),
        },
    }


@router.post("/preview")
async def post_planogram_preview(
    payload: PlanogramPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    """Run the canonical physical gate against request-supplied candidate data."""
    _engine_or_503()
    try:
        result = generate_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical Planogram engine is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "production_release_allowed": False,
        "engine_result": result,
    }


@router.post("/store-scan/normalize-preview")
async def post_store_scan_normalize_preview(
    payload: PlanogramStoreScanPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    """Normalize measured camera/LiDAR/AR geometry without granting Store DNA truth."""
    store_code = ensure_planogram_store_scope(
        principal,
        "action:planogram:create",
        payload.store_code,
    )
    result = normalize_store_scan(payload.model_dump(mode="python"))
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": store_code,
        "preview_only": True,
        "input_authority": "request_supplied_measured_scan_unattested",
        "production_release_allowed": False,
        "store_scan": result,
    }


@router.get("/store-dna/workspace")
async def get_store_dna_workspace(
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    permissions = set(principal.permissions)
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "template": {
            "aisle_count": DEFAULT_AISLE_COUNT,
            "modules_per_side": DEFAULT_MODULES_PER_SIDE,
            "shelves_per_module": DEFAULT_SHELVES_PER_MODULE,
            "pallet_count": DEFAULT_PALLET_COUNT,
            "module_total": DEFAULT_AISLE_COUNT * DEFAULT_MODULES_PER_SIDE * 2,
            "shelf_total": (
                DEFAULT_AISLE_COUNT
                * DEFAULT_MODULES_PER_SIDE
                * 2
                * DEFAULT_SHELVES_PER_MODULE
            ),
        },
        "capabilities": {
            "create": "action:planogram:create" in permissions,
            "edit": "action:planogram:edit" in permissions,
            "submit": "action:planogram:edit" in permissions,
            "approve": "action:planogram:approve" in permissions,
        },
        "approval_policy": {
            "maker_checker_required": True,
            "approved_versions_immutable": True,
            "approval_attests_topology_not_missing_geometry": True,
        },
        "versions": await list_store_dna_versions(session, principal),
    }


@router.post("/store-dna/bootstrap", status_code=status.HTTP_201_CREATED)
async def post_store_dna_bootstrap(
    payload: PlanogramStoreDnaDraftRequest,
    session: TenantSession,
    principal: Creator,
) -> dict[str, object]:
    try:
        store_code = ensure_planogram_store_scope(
            principal,
            "action:planogram:create",
            payload.store_code,
        )
        configuration = build_store_dna_configuration(payload)
        result = await create_store_dna_draft(
            session,
            principal,
            store_code=store_code,
            store_name=payload.store_name,
            source=payload.source,
            configuration=configuration,
            summary=summarize_store_dna(configuration),
            configuration_sha256=configuration_fingerprint(configuration),
            geometry_attested=geometry_attested(configuration),
        )
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.put("/store-dna/{version_id}")
async def put_store_dna_draft(
    version_id: UUID,
    payload: PlanogramStoreDnaDraftRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        store_code = ensure_planogram_store_scope(
            principal,
            "action:planogram:edit",
            payload.store_code,
        )
        configuration = build_store_dna_configuration(payload)
        result = await update_store_dna_draft(
            session,
            principal,
            version_id,
            store_code=store_code,
            store_name=payload.store_name,
            source=payload.source,
            configuration=configuration,
            summary=summarize_store_dna(configuration),
            configuration_sha256=configuration_fingerprint(configuration),
            geometry_attested=geometry_attested(configuration),
        )
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return result


@router.post("/store-dna/{version_id}/submit")
async def post_store_dna_submit(
    version_id: UUID,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        return await submit_store_dna(session, principal, version_id)
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc


@router.post("/store-dna/{version_id}/approve")
async def post_store_dna_approve(
    version_id: UUID,
    payload: PlanogramStoreDnaApproveRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, object]:
    try:
        return await approve_store_dna(
            session,
            principal,
            version_id,
            note=payload.note,
        )
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc


@router.post("/store-dna/{version_id}/reject")
async def post_store_dna_reject(
    version_id: UUID,
    payload: PlanogramStoreDnaRejectRequest,
    session: TenantSession,
    principal: Approver,
) -> dict[str, object]:
    try:
        return await reject_store_dna(
            session,
            principal,
            version_id,
            reason=payload.reason,
        )
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc


@router.post("/store-dna/{version_id}/revise", status_code=status.HTTP_201_CREATED)
async def post_store_dna_revise(
    version_id: UUID,
    payload: PlanogramStoreDnaRevisionRequest,
    session: TenantSession,
    principal: Editor,
) -> dict[str, object]:
    try:
        return await revise_store_dna(
            session,
            principal,
            version_id,
            reason=payload.reason,
        )
    except StoreDnaStateError as exc:
        raise _store_dna_conflict(exc) from exc


@router.get("/store-dna/{store_code}/readiness")
async def get_store_dna_readiness(
    store_code: str,
    session: TenantSession,
    principal: Viewer,
) -> dict[str, object]:
    canonical_store_code = ensure_planogram_store_scope(
        principal,
        "module:planogram:view",
        store_code,
        conceal=True,
    )
    approved = await get_approved_store_dna(
        session,
        principal,
        canonical_store_code,
    )
    store_dna_attested = approved is not None
    fixture_geometry_attested = bool(approved and approved["geometry_attested"])
    evidence = {
        "approved_sku_dimensions": False,
        "product_image_linkage": False,
        "store_dna": store_dna_attested,
        "fixture_geometry_capacity": fixture_geometry_attested,
        "physical_layout_aisle": fixture_geometry_attested,
        "pallet_fixture_authority": store_dna_attested,
    }
    return {
        "tenant_id": str(principal.tenant_id),
        "store_code": canonical_store_code,
        "approved_store_dna": approved,
        "evidence": evidence,
        "production_ready": all(evidence.values()),
        "solver_optimizer_allowed": all(evidence.values()),
        "blockers": [key for key, verified in evidence.items() if not verified],
    }
