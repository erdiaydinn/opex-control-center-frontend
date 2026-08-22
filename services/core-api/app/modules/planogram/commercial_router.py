from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.access import ensure_planogram_store_scope
from app.modules.planogram.commercial_adapter import generate_commercial_merchandising_preview
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
Creator = Annotated[Principal, Depends(require_permission("action:planogram:create"))]


class CommercialSubstitutionEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku_a: str = Field(min_length=1, max_length=160)
    sku_b: str = Field(min_length=1, max_length=160)
    cross_elasticity: float = Field(ge=0, le=1.5)
    source_ref: str | None = Field(default=None, max_length=500)


class PlanogramCommercialPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    products: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)
    category_capacity_cm: dict[str, float] = Field(default_factory=dict)
    total_shelf_width_cm: float | None = Field(default=None, gt=0, le=10_000_000)
    substitution_edges: list[CommercialSubstitutionEdge] = Field(
        default_factory=list,
        max_length=50_000,
    )
    objective_weights: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def require_capacity(self) -> PlanogramCommercialPreviewRequest:
        if not self.category_capacity_cm and self.total_shelf_width_cm is None:
            raise ValueError("category_capacity_cm or total_shelf_width_cm is required")
        return self


@router.post("/commercial-merchandising-preview")
async def post_commercial_merchandising_preview(
    payload: PlanogramCommercialPreviewRequest,
    principal: Creator,
) -> dict[str, object]:
    store_code = ensure_planogram_store_scope(
        principal,
        "action:planogram:create",
        payload.store_code,
    )
    try:
        result = generate_commercial_merchandising_preview(
            products=payload.products,
            category_capacity_cm=payload.category_capacity_cm,
            total_shelf_width_cm=payload.total_shelf_width_cm,
            substitution_edges=[
                row.model_dump(mode="python") for row in payload.substitution_edges
            ],
            objective_weights=payload.objective_weights,
        )
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Commercial merchandising optimizer is unavailable",
        ) from exc

    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": store_code,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "production_release_allowed": False,
        "assortment_execution_allowed": False,
        "finance_decision_allowed": False,
        "result": result,
    }
