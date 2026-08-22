from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.authorization import require_permission
from app.core.security import Principal
from app.db.session import get_tenant_session
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.fixture_catalog import FixtureCatalogStateError
from app.modules.planogram.scanned_optimizer_adapter import (
    generate_scanned_store_optimizer_preview,
)
from app.modules.planogram.store_dna import normalize_store_code
from app.modules.planogram.store_scan_fixture_layout import (
    build_scanned_fixture_layout_preview,
)
from app.modules.planogram.store_scan_trusted_fixture import (
    resolve_trusted_fixture_bindings,
)
from app.modules.planogram.store_scan_trusted_schemas import (
    PlanogramStoreScanTrustedFixtureLayoutPreviewRequest,
    PlanogramStoreScanTrustedOptimizePreviewRequest,
)

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
TenantSession = Annotated[AsyncSession, Depends(get_tenant_session)]
Creator = Annotated[Principal, Depends(require_permission("action:planogram:create"))]


def _catalog_conflict(exc: FixtureCatalogStateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.code)


def _assert_preview_boundary(result: dict[str, object], keys: tuple[str, ...]) -> None:
    for key in keys:
        if result.get(key) is not False:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Planogram trusted preview violated {key} boundary",
            )


@router.post("/store-scan/fixture-layout-trusted-preview")
async def post_store_scan_fixture_layout_trusted_preview(
    payload: PlanogramStoreScanTrustedFixtureLayoutPreviewRequest,
    session: TenantSession,
    principal: Creator,
) -> dict[str, object]:
    """Resolve approved server catalog truth, then reconstruct the scan layout."""
    try:
        fixture_bindings = await resolve_trusted_fixture_bindings(
            session, principal, payload.fixture_bindings
        )
    except FixtureCatalogStateError as exc:
        raise _catalog_conflict(exc) from exc

    result = build_scanned_fixture_layout_preview(
        scan_payload=payload.scan.model_dump(mode="python"),
        expected_scan_fingerprint=payload.expected_scan_fingerprint,
        classifications=[row.model_dump(mode="python") for row in payload.classifications],
        operational_elements=[
            row.model_dump(mode="python") for row in payload.operational_elements
        ],
        fixture_bindings=fixture_bindings,
        review_note=payload.review_note,
    )
    _assert_preview_boundary(
        result,
        (
            "physical_layout_authority",
            "store_dna_authority",
            "v4_v5_production_eligible",
            "relocation_execution_allowed",
            "installation_approval_allowed",
            "capex_approval_allowed",
        ),
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": normalize_store_code(payload.scan.store_code),
        "preview_only": True,
        "input_authority": "server_approved_fixture_catalog_scan_binding_v1",
        "fixture_catalog_authoritative": True,
        "store_dna_approval_allowed": False,
        "physical_layout_release_allowed": False,
        "production_release_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "result": result,
    }


@router.post("/store-scan/optimize-trusted-preview")
async def post_store_scan_optimize_trusted_preview(
    payload: PlanogramStoreScanTrustedOptimizePreviewRequest,
    session: TenantSession,
    principal: Creator,
    max_candidates: Annotated[int, Query(ge=1, le=24)] = 24,
) -> dict[str, object]:
    """Run V6 with server-approved fixture truth without granting release authority."""
    try:
        fixture_bindings = await resolve_trusted_fixture_bindings(
            session, principal, payload.fixture_bindings
        )
        result = generate_scanned_store_optimizer_preview(
            scan_payload=payload.scan.model_dump(mode="python"),
            expected_scan_fingerprint=payload.expected_scan_fingerprint,
            classifications=[
                row.model_dump(mode="python") for row in payload.classifications
            ],
            operational_elements=[
                row.model_dump(mode="python") for row in payload.operational_elements
            ],
            fixture_bindings=fixture_bindings,
            products=[dict(row) for row in payload.products],
            orders=[row.model_dump(mode="python") for row in payload.order_baskets],
            review_note=payload.review_note,
            max_candidates=max_candidates,
        )
    except FixtureCatalogStateError as exc:
        raise _catalog_conflict(exc) from exc
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram scanned-store optimizer is unavailable",
        ) from exc

    _assert_preview_boundary(
        result,
        (
            "production_authority",
            "store_dna_authority",
            "physical_layout_authority",
            "installation_approved",
            "relocation_execution_allowed",
            "capex_approved",
            "global_optimum_claim",
            "field_evidence",
        ),
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": normalize_store_code(payload.scan.store_code),
        "preview_only": True,
        "input_authority": "server_approved_fixture_catalog_scanned_v2_optimizer_v1",
        "fixture_catalog_authoritative": True,
        "store_dna_approval_allowed": False,
        "physical_layout_release_allowed": False,
        "production_release_allowed": False,
        "installation_approval_allowed": False,
        "relocation_execution_allowed": False,
        "capex_approval_allowed": False,
        "global_optimum_claim": False,
        "field_evidence": False,
        "result": result,
    }
