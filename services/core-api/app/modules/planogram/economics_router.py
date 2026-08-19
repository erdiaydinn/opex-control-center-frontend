from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.economics_adapter import (
    generate_physical_layout_economics_preview,
)
from app.modules.planogram.economics_schemas import (
    PlanogramPhysicalEconomicsPreviewRequest,
)
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

Creator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]
Approver = Annotated[
    Principal,
    Depends(require_permission("action:planogram:approve")),
]


@router.post("/physical-layout-economics-preview")
async def post_planogram_physical_layout_economics_preview(
    payload: PlanogramPhysicalEconomicsPreviewRequest,
    principal: Creator,
    _approver: Approver,
    max_layout_candidates: Annotated[int, Query(ge=1, le=32)] = 16,
    max_allocation_candidates: Annotated[int, Query(ge=8, le=24)] = 12,
) -> dict[str, object]:
    """Recompute V5 and derive economics without granting investment authority."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    if not baskets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Physical-layout economics requires anonymized SKU baskets",
        )

    try:
        result = generate_physical_layout_economics_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            orders=baskets,
            mode=payload.mode,
            assumptions=payload.economics.model_dump(mode="python"),
            max_layout_candidates=max_layout_candidates,
            max_allocation_candidates=max_allocation_candidates,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram physical-layout economics is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "economic_assumption_authority": "request_supplied_attestation_claims_unverified",
        "basket_authority": "request_supplied_observed_or_test_unattested",
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "physical_relocation_execution_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "finance_approval_allowed": False,
        "investment_decision_allowed": False,
        "realized_savings_proven": False,
        "result": result,
    }
