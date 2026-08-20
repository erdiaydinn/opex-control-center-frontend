from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.access import ensure_planogram_store_scope
from app.modules.planogram.temporal_realogram import evaluate_temporal_realogram

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
Creator = Annotated[Principal, Depends(require_permission("action:planogram:create"))]


class TemporalRealogramEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_type: Literal[
        "shelf_scan",
        "inventory_oos",
        "replenishment",
        "pick_sequence_step",
        "barcode_pick",
        "substitution",
        "cold_chain_transition",
    ]
    observed_at: str = Field(min_length=10, max_length=64)
    sku: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=500)
    flow_id: str | None = Field(default=None, max_length=160)
    aisle_id: str | None = Field(default=None, max_length=80)
    module_id: str | int | None = None
    shelf_no: str | int | None = None
    facing_count: int | None = Field(default=None, ge=1, le=500)
    confidence: float | None = Field(default=None, ge=0, le=1)
    image_quality_score: float | None = Field(default=None, ge=0, le=1)
    occlusion_pct: float | None = Field(default=None, ge=0, le=100)
    sequence_no: int | None = Field(default=None, ge=1, le=10_000)
    barcode: str | None = Field(default=None, max_length=160)
    quantity: float | None = Field(default=None, ge=0)
    substitute_sku: str | None = Field(default=None, max_length=160)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    allowed_seconds: float | None = Field(default=None, ge=0)
    temperature_c: float | None = Field(default=None, ge=-100, le=100)
    min_temperature_c: float | None = Field(default=None, ge=-100, le=100)
    max_temperature_c: float | None = Field(default=None, ge=-100, le=100)


class PlanogramTemporalRealogramRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    planogram: dict
    events: list[TemporalRealogramEvent] = Field(min_length=1, max_length=100_000)
    as_of: str | None = Field(default=None, min_length=10, max_length=64)
    stale_after_minutes: int = Field(default=240, ge=15, le=43_200)


@router.post("/temporal-realogram-preview")
async def post_temporal_realogram_preview(
    payload: PlanogramTemporalRealogramRequest,
    principal: Creator,
) -> dict[str, object]:
    store_code = ensure_planogram_store_scope(
        principal,
        "action:planogram:create",
        payload.store_code,
    )
    result = evaluate_temporal_realogram(
        plan_payload=payload.planogram,
        events=[event.model_dump(mode="python") for event in payload.events],
        as_of=payload.as_of,
        stale_after_minutes=payload.stale_after_minutes,
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": store_code,
        "preview_only": True,
        "production_release_allowed": False,
        "auto_correction_allowed": False,
        "realogram": result,
    }
