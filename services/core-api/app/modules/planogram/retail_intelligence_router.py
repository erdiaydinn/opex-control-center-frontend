"""Unified Planogram retail-intelligence preview orchestration."""
from __future__ import annotations

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.authorization import require_permission
from app.core.security import Principal
from app.modules.planogram.access import ensure_planogram_store_scope
from app.modules.planogram.benchmark_schemas import PlanogramBlindCandidate
from app.modules.planogram.blind_benchmark_adapter import generate_blind_benchmark_preview
from app.modules.planogram.commercial_physical_adapter import (
    generate_commercial_physical_convergence_preview,
)
from app.modules.planogram.commercial_router import CommercialSubstitutionEdge
from app.modules.planogram.engine_adapter import PlanogramEngineUnavailable
from app.modules.planogram.execution import PlanogramExecutionError
from app.modules.planogram.market_evidence_gate import evaluate_market_evidence_gate
from app.modules.planogram.realogram_router import TemporalRealogramEvent
from app.modules.planogram.realogram_v2 import evaluate_temporal_realogram_v2
from app.modules.planogram.retail_intelligence_guard import assert_retail_payload_safe
from app.modules.planogram.schemas import PlanogramOrderBasket
from app.modules.planogram.shadow_backtest_adapter import generate_shadow_backtest_preview
from app.modules.planogram.shelf_scan import evaluate_shelf_scan
from app.modules.planogram.shelf_scan_schemas import (
    PlanogramShelfScanObservation,
    PlanogramShelfScanShelfEvidence,
)

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

    historical_pairs: list[PlanogramShadowPair] = Field(
        default_factory=list,
        max_length=5_000,
    )
    metric_directions: dict[str, Literal["lower", "higher"]] = Field(
        default_factory=dict
    )
    minimum_backtest_pairs: int = Field(default=3, ge=1, le=5_000)

    order_baskets: list[PlanogramOrderBasket] = Field(
        default_factory=list,
        max_length=5_000,
    )
    blind_candidate_a: PlanogramBlindCandidate | None = None
    blind_candidate_b: PlanogramBlindCandidate | None = None

    shelf_scan_shelves: list[PlanogramShelfScanShelfEvidence] = Field(
        default_factory=list,
        max_length=2_000,
    )
    shelf_scan_observations: list[PlanogramShelfScanObservation] = Field(
        default_factory=list,
        max_length=20_000,
    )
    min_detection_confidence: float = Field(default=0.80, ge=0.50, le=1.0)
    min_image_quality: float = Field(default=0.70, ge=0.0, le=1.0)
    max_occlusion_pct: float = Field(default=35.0, ge=0.0, le=100.0)

    realogram_events: list[RetailRealogramEvent] = Field(
        default_factory=list,
        max_length=100_000,
    )
    as_of: str | None = Field(default=None, min_length=10, max_length=64)
    stale_after_minutes: int = Field(default=240, ge=15, le=43_200)
    require_images: bool = True

    @model_validator(mode="after")
    def validate_evidence_contract(self) -> PlanogramRetailIntelligenceRequest:
        if not self.category_capacity_cm and self.total_shelf_width_cm is None:
            raise ValueError("category_capacity_cm or total_shelf_width_cm is required")

        blind_pair = (self.blind_candidate_a is not None, self.blind_candidate_b is not None)
        if blind_pair[0] != blind_pair[1]:
            raise ValueError("blind_candidate_a and blind_candidate_b must be supplied together")
        if any(blind_pair) and not self.order_baskets:
            raise ValueError("blind benchmark candidates require order_baskets")
        if self.shelf_scan_observations and not self.shelf_scan_shelves:
            raise ValueError("shelf_scan_observations require shelf_scan_shelves")
        return self


def _normalized_store_code(value: Any) -> str:
    return str(value or "").strip().upper()


def _assert_embedded_store_matches(payload: PlanogramRetailIntelligenceRequest) -> None:
    requested = _normalized_store_code(payload.store_code)
    for container_name, container in (
        ("layout", payload.layout),
        ("store_dna", payload.store_dna),
    ):
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

    for label, candidate in (
        ("blind_candidate_a", payload.blind_candidate_a),
        ("blind_candidate_b", payload.blind_candidate_b),
    ):
        if candidate is None:
            continue
        embedded = _normalized_store_code(candidate.planogram.get("store_code"))
        if embedded and embedded not in {"AUTO", requested}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"{label}_store_code_mismatch",
            )


def _unavailable(reason: str, **authority: bool) -> dict[str, object]:
    return {
        "available": False,
        "blockers": [reason],
        **authority,
    }


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

    historical_payload = [
        row.model_dump(mode="python") for row in payload.historical_pairs
    ]
    blind_payload = [
        candidate.planogram
        for candidate in (payload.blind_candidate_a, payload.blind_candidate_b)
        if candidate is not None
    ]
    shelf_payload = [
        row.model_dump(mode="python") for row in payload.shelf_scan_shelves
    ] + [
        row.model_dump(mode="python") for row in payload.shelf_scan_observations
    ]
    try:
        assert_retail_payload_safe(payload.products)
        assert_retail_payload_safe(historical_payload)
        assert_retail_payload_safe(blind_payload)
        assert_retail_payload_safe(shelf_payload)
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

        backtest = (
            generate_shadow_backtest_preview(
                pairs=historical_payload,
                metric_directions=dict(payload.metric_directions),
                minimum_pairs=payload.minimum_backtest_pairs,
            )
            if payload.historical_pairs
            else _unavailable(
                "historical_pairs_missing",
                causal_claim_allowed=False,
                market_leadership_claim_allowed=False,
            )
        )

        if payload.blind_candidate_a and payload.blind_candidate_b:
            blind_benchmark = generate_blind_benchmark_preview(
                products=payload.products,
                layout=payload.layout,
                store_dna=payload.store_dna,
                orders=[
                    row.model_dump(mode="python") for row in payload.order_baskets
                ],
                candidate_a=payload.blind_candidate_a.model_dump(mode="python"),
                candidate_b=payload.blind_candidate_b.model_dump(mode="python"),
            )
        else:
            blind_benchmark = _unavailable(
                "blind_candidates_missing",
                production_evidence=False,
                market_leadership_proven=False,
                promotion_allowed=False,
            )

        converged_planogram = (convergence.get("physical") or {}).get("planogram")
        if payload.shelf_scan_shelves and converged_planogram:
            shelf_scan = evaluate_shelf_scan(
                plan_payload=converged_planogram,
                shelves=shelf_payload[: len(payload.shelf_scan_shelves)],
                observations=shelf_payload[len(payload.shelf_scan_shelves) :],
                min_detection_confidence=payload.min_detection_confidence,
                min_image_quality=payload.min_image_quality,
                max_occlusion_pct=payload.max_occlusion_pct,
            )
        elif payload.shelf_scan_shelves:
            shelf_scan = _unavailable(
                "converged_planogram_missing_for_shelf_scan",
                production_evidence=False,
                field_truth=False,
                auto_correct_allowed=False,
            )
        else:
            shelf_scan = _unavailable(
                "shelf_scan_evidence_missing",
                production_evidence=False,
                field_truth=False,
                auto_correct_allowed=False,
            )

        if payload.realogram_events and converged_planogram:
            realogram = evaluate_temporal_realogram_v2(
                plan_payload=converged_planogram,
                events=[
                    row.model_dump(mode="python") for row in payload.realogram_events
                ],
                as_of=payload.as_of,
                stale_after_minutes=payload.stale_after_minutes,
            )
        elif payload.realogram_events:
            realogram = _unavailable(
                "converged_planogram_missing_for_realogram",
                field_truth=False,
                auto_execute_allowed=False,
            )
        else:
            realogram = _unavailable(
                "realogram_events_missing",
                field_truth=False,
                auto_execute_allowed=False,
            )
    except (PlanogramEngineUnavailable, PlanogramExecutionError) as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Planogram retail-intelligence engine is unavailable",
        ) from exc

    evidence_gate = evaluate_market_evidence_gate(
        convergence=convergence,
        shadow_backtest=backtest,
        blind_benchmark=blind_benchmark,
        realogram=realogram,
        shelf_scan=shelf_scan,
        external_authority=None,
        preview_context=True,
    )
    return {
        "tenant_id": str(principal.tenant_id),
        "subject": principal.subject,
        "store_code": store_code,
        "preview_only": True,
        "input_authority": "request_supplied_unattested",
        "convergence": convergence,
        "shadow_backtest": backtest,
        "blind_benchmark": blind_benchmark,
        "shelf_scan": shelf_scan,
        "realogram_v2": realogram,
        "market_evidence_gate": evidence_gate,
        "production_release_allowed": False,
        "assortment_execution_allowed": False,
        "auto_correction_allowed": False,
        "causal_claim_allowed": False,
        "market_leadership_claim_allowed": False,
    }
