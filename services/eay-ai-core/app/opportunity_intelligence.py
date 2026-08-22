"""Proactive upside/opportunity scoring for EAY Jarvis.

Jarvis should surface not only risks but also evidence-backed opportunities such
as weather-driven demand, event peaks, temporary capacity headroom or margin
improvement. The output is decision support; external actions remain governed.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

OPPORTUNITY_INTELLIGENCE_CONTRACT = "eay-opportunity-intelligence-v1"


class OpportunityDisposition(str, Enum):
    IGNORE = "ignore"
    WATCH = "watch"
    PREPARE = "prepare"
    PRIORITIZE = "prioritize"


class OpportunitySignal(BaseModel):
    opportunity_id: str = Field(min_length=1, max_length=180)
    domain: str = Field(min_length=1, max_length=120)
    location: str = Field(min_length=1, max_length=300)
    expected_uplift_pct: float = Field(ge=0.0, le=1000.0)
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    freshness_confidence: float = Field(ge=0.0, le=1.0)
    capacity_headroom_pct: float = Field(ge=0.0, le=1000.0)
    inventory_readiness: float = Field(ge=0.0, le=1.0)
    margin_quality: float = Field(ge=0.0, le=1.0)
    time_to_impact_hours: float = Field(ge=0.0)
    provenance_refs: tuple[str, ...] = Field(min_length=1)


class OpportunityAssessment(BaseModel):
    contract: str = OPPORTUNITY_INTELLIGENCE_CONTRACT
    opportunity_id: str
    score: float = Field(ge=0.0, le=1.0)
    disposition: OpportunityDisposition
    capture_readiness: float = Field(ge=0.0, le=1.0)
    upside_strength: float = Field(ge=0.0, le=1.0)
    evidence_quality: float = Field(ge=0.0, le=1.0)
    blockers: tuple[str, ...] = ()
    suggested_preparations: tuple[str, ...] = ()


def assess_opportunity(signal: OpportunitySignal) -> OpportunityAssessment:
    upside = min(signal.expected_uplift_pct / 30.0, 1.0)
    capacity = min(signal.capacity_headroom_pct / max(signal.expected_uplift_pct, 1.0), 1.0)
    readiness = (
        (0.40 * capacity)
        + (0.35 * signal.inventory_readiness)
        + (0.25 * signal.margin_quality)
    )
    evidence = min(signal.evidence_confidence, signal.freshness_confidence)
    urgency = 1.0 / (1.0 + signal.time_to_impact_hours / 24.0)
    score = min(
        ((0.35 * upside) + (0.35 * readiness) + (0.30 * urgency)) * evidence,
        1.0,
    )

    blockers: list[str] = []
    preparations: list[str] = []
    if signal.inventory_readiness < 0.60:
        blockers.append("inventory_readiness_low")
        preparations.append("review_inventory_and_availability")
    if capacity < 0.70:
        blockers.append("capacity_headroom_insufficient_for_expected_uplift")
        preparations.append("simulate_workforce_and_delivery_capacity")
    if signal.margin_quality < 0.45:
        blockers.append("margin_quality_low")
        preparations.append("validate_incremental_contribution_margin")
    if evidence < 0.60:
        blockers.append("opportunity_evidence_quality_low")

    if score >= 0.72 and not blockers:
        disposition = OpportunityDisposition.PRIORITIZE
    elif score >= 0.52:
        disposition = OpportunityDisposition.PREPARE
    elif score >= 0.30:
        disposition = OpportunityDisposition.WATCH
    else:
        disposition = OpportunityDisposition.IGNORE

    if disposition in {OpportunityDisposition.PREPARE, OpportunityDisposition.PRIORITIZE}:
        if "simulate_workforce_and_delivery_capacity" not in preparations:
            preparations.append("simulate_workforce_and_delivery_capacity")
        if "review_inventory_and_availability" not in preparations:
            preparations.append("review_inventory_and_availability")

    return OpportunityAssessment(
        opportunity_id=signal.opportunity_id,
        score=round(score, 6),
        disposition=disposition,
        capture_readiness=round(readiness, 6),
        upside_strength=round(upside, 6),
        evidence_quality=round(evidence, 6),
        blockers=tuple(dict.fromkeys(blockers)),
        suggested_preparations=tuple(dict.fromkeys(preparations)),
    )
