from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.scanned_optimizer_adapter import (
    generate_scanned_store_optimizer_preview,
)
from app.modules.planogram.store_dna import normalize_store_code
from app.modules.planogram.store_scan_binding_schemas import (
    PlanogramStoreScanFixtureLayoutPreviewRequest,
    PlanogramStoreScanOptimizePreviewRequest,
)
from app.modules.planogram.store_scan_fixture_layout import (
    build_scanned_fixture_layout_preview,
)

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
Creator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]


@router.post("/store-scan/fixture-layout-preview")
async def post_store_scan_fixture_layout_preview(
    payload: PlanogramStoreScanFixtureLayoutPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    """Bind reviewed scan fixtures to catalog truth without production authority."""
    result = build_scanned_fixture_layout_preview(
        scan_payload=payload.scan.model_dump(mode="python"),
        expected_scan_fingerprint=payload.expected_scan_fingerprint,
        classifications=[row.model_dump(mode="python") for row in payload.classifications],
        operational_elements=[
            row.model_dump(mode="python") for row in payload.operational_elements
        ],
        fixture_bindings=[
            row.model_dump(mode="python") for row in payload.fixture_bindings
        ],
        review_note=payload.review_note,
        uncertainty_resolutions=[
            row.model_dump(mode="python") for row in payload.uncertainty_resolutions
        ],
    )
    for key in (
        "physical_layout_authority",
        "store_dna_authority",
        "v4_v5_production_eligible",
        "relocation_execution_allowed",
        "installation_approval_allowed",
        "capex_approval_allowed",
    ):
        if result.get(key) is not False:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Planogram scanned fixture preview violated authority boundary",
            )

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": normalize_store_code(payload.scan.store_code),
        "preview_only": True,
        "input_authority": "fingerprint_bound_human_fixture_binding_unattested",
        "store_dna_approval_allowed": False,
        "physical_layout_release_allowed": False,
        "production_release_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "result": result,
    }


@router.post("/store-scan/optimize-preview")
async def post_store_scan_optimize_preview(
    payload: PlanogramStoreScanOptimizePreviewRequest,
    principal: Creator,
    max_candidates: Annotated[int, Query(ge=1, le=24)] = 24,
) -> dict[str, object]:
    """Run V6 only after server-side scan review and fixture truth reconstruction."""
    try:
        result = generate_scanned_store_optimizer_preview(
            scan_payload=payload.scan.model_dump(mode="python"),
            expected_scan_fingerprint=payload.expected_scan_fingerprint,
            classifications=[
                row.model_dump(mode="python") for row in payload.classifications
            ],
            operational_elements=[
                row.model_dump(mode="python") for row in payload.operational_elements
            ],
            fixture_bindings=[
                row.model_dump(mode="python") for row in payload.fixture_bindings
            ],
            products=[dict(row) for row in payload.products],
            orders=[row.model_dump(mode="python") for row in payload.order_baskets],
            review_note=payload.review_note,
            max_candidates=max_candidates,
            uncertainty_resolutions=[
                row.model_dump(mode="python") for row in payload.uncertainty_resolutions
            ],
        )
    except Exception as exc:
        from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable

        if isinstance(exc, PlanogramEngineUnavailable):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Planogram scanned-store optimizer is unavailable",
            ) from exc
        raise

    for key in (
        "production_authority",
        "store_dna_authority",
        "physical_layout_authority",
        "installation_approved",
        "relocation_execution_allowed",
        "capex_approved",
        "global_optimum_claim",
        "field_evidence",
    ):
        if result.get(key) is not False:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Planogram scanned optimizer violated {key} boundary",
            )

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": normalize_store_code(payload.scan.store_code),
        "preview_only": True,
        "input_authority": "fingerprint_bound_scanned_v2_optimizer_unattested",
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
