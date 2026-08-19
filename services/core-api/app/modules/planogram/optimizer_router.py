from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
    generate_market_leadership_benchmark_preview,
    generate_optimized_preview,
)
from app.modules.planogram.schemas import PlanogramPreviewRequest

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

Optimizer = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
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
