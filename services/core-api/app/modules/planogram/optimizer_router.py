from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.engine_adapter import (
    PlanogramEngineUnavailable,
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
    try:
        result = generate_optimized_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            mode=payload.mode,
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
        "production_release_allowed": False,
        "optimizer_result": result,
    }
