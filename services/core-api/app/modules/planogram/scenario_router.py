from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.scenario_adapter import (
    generate_physical_layout_candidate_preview,
)
from app.modules.planogram.scenario_schemas import (
    PlanogramPhysicalLayoutCandidatePreviewRequest,
)

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])

ScenarioCreator = Annotated[
    Principal,
    Depends(require_permission("action:planogram:create")),
]


@router.post("/physical-layout-candidate-preview")
async def post_planogram_physical_layout_candidate_preview(
    payload: PlanogramPhysicalLayoutCandidatePreviewRequest,
    principal: ScenarioCreator,
    max_layout_candidates: Annotated[int, Query(ge=1, le=32)] = 16,
    max_allocation_candidates: Annotated[int, Query(ge=8, le=24)] = 12,
) -> dict[str, object]:
    """Replay one V5 candidate by server-generated fingerprint, preview only."""
    baskets = [basket.model_dump(mode="python") for basket in payload.order_baskets]
    if not baskets:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Physical-layout candidate preview requires anonymized SKU baskets",
        )

    try:
        result = generate_physical_layout_candidate_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            orders=baskets,
            layout_fingerprint=payload.layout_fingerprint.lower(),
            mode=payload.mode,
            max_layout_candidates=max_layout_candidates,
            max_allocation_candidates=max_allocation_candidates,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram physical-layout candidate preview is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "candidate_selection_authority": "server_recomputed_fingerprint_match_only",
        "basket_authority": "request_supplied_observed_or_test_unattested",
        "observed_basket_input_count": len(baskets),
        "production_release_allowed": False,
        "physical_relocation_execution_allowed": False,
        "installation_approval_allowed": False,
        "capex_approval_allowed": False,
        "result": result,
    }
