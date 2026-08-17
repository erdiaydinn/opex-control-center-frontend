"""Unknown-unknown / blind-spot detection for EAY Jarvis.

Material anomalies that are not explained by any sufficiently supported
hypothesis are themselves decision-relevant. This module turns that state into
an explicit investigation signal instead of letting Jarvis fill the gap with a
story. It recommends evidence domains to inspect; it never invents a cause.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .hypothesis_intelligence import HypothesisRanking

BLIND_SPOT_INTELLIGENCE_CONTRACT = "eay-blind-spot-intelligence-v1"


class BlindSpotStatus(str, Enum):
    EXPLAINED_ENOUGH = "explained_enough"
    PARTIALLY_EXPLAINED = "partially_explained"
    UNEXPLAINED_MATERIAL_ANOMALY = "unexplained_material_anomaly"


class BlindSpotInput(BaseModel):
    anomaly_id: str = Field(min_length=1, max_length=180)
    metric_name: str = Field(min_length=1, max_length=200)
    deviation_pct: float
    evidence_domains_available: tuple[str, ...] = ()
    hypothesis_ranking: HypothesisRanking | None = None
    material_threshold_pct: float = Field(default=10.0, ge=0.0, le=1000.0)


class BlindSpotAssessment(BaseModel):
    contract: str = BLIND_SPOT_INTELLIGENCE_CONTRACT
    anomaly_id: str
    status: BlindSpotStatus
    material: bool
    best_hypothesis_id: str | None = None
    best_hypothesis_confidence: float = Field(ge=0.0, le=1.0)
    investigation_required: bool
    missing_evidence_domains: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


DEFAULT_INVESTIGATION_DOMAINS = (
    "demand_calendar",
    "weather",
    "city_events_transport",
    "pricing_promotions",
    "availability_inventory",
    "workforce_capacity",
    "delivery_rider_capacity",
    "platform_incident",
    "competitor_market",
    "macro_economy",
)


def assess_blind_spot(payload: BlindSpotInput) -> BlindSpotAssessment:
    material = abs(payload.deviation_pct) >= payload.material_threshold_pct
    available = {item.casefold().strip() for item in payload.evidence_domains_available}
    missing = tuple(domain for domain in DEFAULT_INVESTIGATION_DOMAINS if domain not in available)

    best_id = None
    best_confidence = 0.0
    ranking = payload.hypothesis_ranking
    if ranking is not None and ranking.assessments:
        best = ranking.assessments[0]
        best_id = best.hypothesis_id
        best_confidence = best.confidence

    warnings: list[str] = []
    if not material:
        status = BlindSpotStatus.EXPLAINED_ENOUGH
        investigation = False
    elif ranking is None or not ranking.assessments or best_confidence < 0.45:
        status = BlindSpotStatus.UNEXPLAINED_MATERIAL_ANOMALY
        investigation = True
        warnings.append("do_not_invent_root_cause")
    elif ranking.requires_more_evidence or best_confidence < 0.70:
        status = BlindSpotStatus.PARTIALLY_EXPLAINED
        investigation = True
        warnings.append("leading_explanation_not_decision_grade")
    else:
        status = BlindSpotStatus.EXPLAINED_ENOUGH
        investigation = False

    return BlindSpotAssessment(
        anomaly_id=payload.anomaly_id,
        status=status,
        material=material,
        best_hypothesis_id=best_id,
        best_hypothesis_confidence=round(best_confidence, 6),
        investigation_required=investigation,
        missing_evidence_domains=missing if investigation else (),
        warnings=tuple(warnings),
    )
