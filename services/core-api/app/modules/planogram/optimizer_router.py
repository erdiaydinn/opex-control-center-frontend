from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.benchmark_schemas import PlanogramBlindBenchmarkRequest
from app.modules.planogram.blind_benchmark_adapter import (
    generate_blind_benchmark_preview,
)
from app.modules.planogram.cad_adapter import generate_cad_preview_document
from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    generate_market_leadership_benchmark_preview,
    generate_optimized_preview,
)
from app.modules.planogram.physical_layout_adapter import (
    generate_physical_layout_search_preview,
)
from app.modules.planogram.schemas import PlanogramPreviewRequest

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

Optimizer = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]
Exporter = Annotated[
    Principal,
    Depends(require_permission("action:planogram:export")),
]


@router.post("/optimize-preview")
async def post_planogram_optimize_preview(
    payload: PlanogramPreviewRequest,
    principal: Optimizer,
) -> dict[str, object]:
    """Optimize request-supplied data without promoting it to production truth."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    try:
        result = generate_optimized_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
            orders=baskets or None,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Canonical Planogram optimizer is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "basket_authority": (
            "request_supplied_observed_or_test_unattested" if baskets else "not_supplied"
        ),
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "optimizer_result": result,
    }


@router.post("/market-benchmark-preview")
async def post_planogram_market_benchmark_preview(
    payload: PlanogramPreviewRequest,
    principal: Optimizer,
    max_candidates: Annotated[int, Query(ge=8, le=32)] = 24,
) -> dict[str, object]:
    """Compare canonical V3 and experimental V4 on exactly the same preview input."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    if not baskets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Market benchmark requires anonymized observed or test SKU baskets",
        )

    try:
        benchmark = generate_market_leadership_benchmark_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
            orders=baskets,
            max_candidates=max_candidates,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram market benchmark is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "basket_authority": "request_supplied_observed_or_test_unattested",
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "experimental_optimizer_production_authority": False,
        "benchmark": benchmark,
    }


@router.post("/physical-layout-search-preview")
async def post_planogram_physical_layout_search_preview(
    payload: PlanogramPreviewRequest,
    principal: Optimizer,
    max_layout_candidates: Annotated[int, Query(ge=1, le=32)] = 16,
    max_allocation_candidates: Annotated[int, Query(ge=8, le=24)] = 12,
) -> dict[str, object]:
    """Search bounded fixture relocations as proposals, never executable moves."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    if not baskets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Physical layout search requires anonymized SKU baskets",
        )

    try:
        result = generate_physical_layout_search_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            orders=baskets,
            mode=payload.mode,
            max_layout_candidates=max_layout_candidates,
            max_allocation_candidates=max_allocation_candidates,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram physical layout search is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "relocation_policy_authority": "request_supplied_unattested",
        "basket_authority": "request_supplied_observed_or_test_unattested",
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "physical_relocation_execution_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "result": result,
    }


@router.post("/blind-benchmark-preview")
async def post_planogram_blind_benchmark_preview(
    payload: PlanogramBlindBenchmarkRequest,
    principal: Optimizer,
) -> dict[str, object]:
    """Score anonymous A/B plans without receiving expert-versus-AI identity."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    try:
        benchmark = generate_blind_benchmark_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            orders=baskets,
            candidate_a=payload.candidate_a.model_dump(mode="python"),
            candidate_b=payload.candidate_b.model_dump(mode="python"),
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram blind benchmark is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "blind": True,
        "candidate_identity_fields_accepted": False,
        "input_authority": "request_supplied_unattested",
        "basket_authority": "request_supplied_observed_or_test_unattested",
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "market_leadership_claim_allowed": False,
        "benchmark": benchmark,
    }


@router.post("/cad-preview")
async def post_planogram_cad_preview(
    payload: PlanogramPreviewRequest,
    principal: Optimizer,
    _exporter: Exporter,
    include_dxf: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    """Render the selected preview plan as a measured SVG/DXF engineering drawing."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    try:
        optimized = generate_optimized_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
            orders=baskets or None,
        )
        drawing = generate_cad_preview_document(
            optimizer_result=optimized,
            layout=payload.layout,
            store_dna=payload.store_dna,
            include_dxf=include_dxf,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Measured Planogram CAD preview is unavailable",
        ) from exc

    optimizer_meta = (
        optimized.get("picker_tour_optimizer")
        or optimized.get("optimizer")
        or {}
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "basket_authority": (
            "request_supplied_observed_or_test_unattested" if baskets else "not_supplied"
        ),
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "installation_approval_allowed": False,
        "optimizer_summary": {
            "optimizer_version": optimizer_meta.get("optimizer_version"),
            "selected_strategy": optimizer_meta.get("selected_strategy"),
        },
        "drawing": drawing,
    }
