"""Unified Planogram retail-intelligence preview orchestration."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.access import ensure_planogram_store_scope
from app.modules.planogram.commercial_physical_adapter import (
    generate_commercial_physical_convergence_preview,
)
from app.modules.planogram.commercial_router import CommercialSubstitutionEdge
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.market_evidence_gate import evaluate_market_evidence_gate
from app.modules.planogram.realogram_router import TemporalRealogramEvent
from app.modules.planogram.realogram_v2 import evaluate_temporal_realogram_v2
from app.modules.planogram.retail_intelligence_guard import assert_retail_payload_safe
from app.modules.planogram.shadow_backtest_adapter import generate_shadow_backtest_preview

router = APIRouter(prefix="/v1/planogram", tags=["planogram"])
Creator = Annotated[Principal, Depends(require_permission("action:planogram:create"))]


class PlanogramShadowPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pair_id: str = Field(min_length=1, max_length=160)
    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    window_id: str = Field(min_length=1, max_length=160)
    source_ref: str = Field(min_length=1, max_length=500)
    attested: bool = False
    baseline: dict[str, float]
    candidate: dict[str, float]


class RetailRealogramEvent(TemporalRealogramEvent):
    provider: Literal[
        "shelf_cv",
        "iot_shelf",
        "wms",
        "scanner",
        "picker_app",
        "cold_chain_sensor",
        "manual_verified",
    ]
    provider_event_id: str = Field(min_length=1, max_length=200)


class PlanogramRetailIntelligenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    products: list[dict[str, Any]] = Field(min_length=1, max_length=10_000)
    layout: dict[str, Any]
    store_dna: dict[str, Any]
    mode: Literal["HYBRID", "CATEGORY", "ABC", "BRAND"] = "HYBRID"
    category_capacity_cm: dict[str, float] = Field(default_factory=dict)
    total_shelf_width_cm: float | None = Field(default=None, gt=0, le=10_000_000)
    substitution_edges: list[CommercialSubstitutionEdge] = Field(
        default_factory=list,
        max_length=50_000,
    )
    objective_weights: dict[str, float] = Field(default_factory=dict)
    historical_pairs: list[PlanogramShadowPair] = Field(default_factory=list, max_length=5_000)
    metric_directions: dict[str, Literal["lower", "higher"]] = Field(default_factory=dict)
    minimum_backtest_pairs: int = Field(default=3, ge=1, le=5_000)
    realogram_events: list[RetailRealogramEvent] = Field(default_factory=list, max_length=100_000)
    as_of: str | None = Field(default=None, min_length=10, max_length=64)
    stale_after_minutes: int = Field(default=240, ge=15, le=43_200)
    require_images: bool = True

    @model_validator(mode="after")
    def require_commercial_capacity(self) -> "PlanogramRetailIntelligenceRequest":
        if not self.category_capacity_cm and self.total_shelf_width_cm is None:
            raise ValueError("category_capacity_cm or total_shelf_width_cm is required")
        return self


def _normalized_store_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _assert_embedded_store_matches(payload: PlanogramRetailIntelligenceRequest) -> None:
    requested = _normalized_store_code(payload.store_code)
    for container_name, container in (("layout", payload.layout), ("store_dna", payload.store_dna)):
        embedded = _normalized_store_code(container.get("store_code"))
        if embedded and embedded not in {"AUTO", requested}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{container_name}_store_code_mismatch",
            )
    for row in payload.historical_pairs:
        if _normalized_store_code(row.store_code) != requested:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="shadow_pair_store_code_mismatch",
            )


@router.post("/retail-intelligence-preview")
async def post_retail_intelligence_preview(
    payload: PlanogramRetailIntelligenceRequest,
    principal: Creator,
) -> dict[str, object]:
    store_code = ensure_planogram_store_scope(
        principal,
        "action:planogram:create",
        payload.store_code,
    )
    _assert_embedded_store_matches(payload)
    try:
        assert_retail_payload_safe(payload.products)
        historical_payload = [
            row.model_dump(mode="python") for row in payload.historical_pairs
        ]
        assert_retail_payload_safe(historical_payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    try:
        convergence = generate_commercial_physical_convergence_preview(
            products=payload.products,
            layout=payload.layout,
            store_dna=payload.store_dna,
            category_capacity_cm=payload.category_capacity_cm,
            total_shelf_width_cm=payload.total_shelf_width_cm,
            substitution_edges=[
                row.model_dump(mode="python") for row in payload.substitution_edges
            ],
            objective_weights=payload.objective_weights,
            mode=payload.mode,
            require_images=payload.require_images,
        )
        backtest = generate_shadow_backtest_preview(
            pairs=[row.model_dump(mode="python") for row in payload.historical_pairs],
            metric_directions=dict(payload.metric_directions),
            minimum_pairs=payload.minimum_backtest_pairs,
        ) if payload.historical_pairs else {
            "available": False,
            "blockers": ["historical_pairs_missing"],
            "causal_claim_allowed": False,
            "market_leadership_claim_allowed": False,
        }
        realogram = evaluate_temporal_realogram_v2(
            plan_payload=(convergence.get("physical") or {}).get("planogram")
            or payload.layout,
            events=[row.model_dump(mode="python") for row in payload.realogram_events],
            as_of=payload.as_of,
            stale_after_minutes=payload.stale_after_minutes,
        ) if payload.realogram_events else {
            "available": False,
            "blockers": ["realogram_events_missing"],
            "field_truth": False,
            "auto_execute_allowed": False,
        }
    except PlanogramEngineUnavailable as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram retail-intelligence engine is unavailable",
        ) from exc

    evidence_gate = evaluate_market_evidence_gate(
        convergence=convergence,
        shadow_backtest=backtest,
        blind_benchmark=None,
        realogram=realogram,
        shelf_scan=None,
        external_authority=None,
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": store_code,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "convergence": convergence,
        "shadow_backtest": backtest,
        "realogram_v2": realogram,
        "market_evidence_gate": evidence_gate,
        "production_release_allowed": False,
        "assortment_execution_allowed": False,
        "auto_correction_allowed": False,
        "causal_claim_allowed": False,
        "market_leadership_claim_allowed": False,
    }
