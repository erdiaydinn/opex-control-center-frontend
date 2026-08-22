"""Proactive executive risk radar for EAY Jarvis.

This layer turns already-governed signals into attention priorities. It is not
an autonomous actuator: it may surface, escalate or suppress an insight, but
external side effects and irreversible actions remain behind explicit human
approval and the existing EAY policy/authorization stack.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum

from pydantic import BaseModel, Field, model_validator

PROACTIVE_INTELLIGENCE_CONTRACT = "eay-proactive-intelligence-v1"


class RadarDisposition(str, Enum):
    SUPPRESS = "suppress"
    WATCH = "watch"
    SURFACE = "surface"
    ESCALATE = "escalate"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ExecutiveSignal(BaseModel):
    signal_id: str = Field(min_length=1, max_length=180)
    domain: str = Field(min_length=1, max_length=120)
    metric_name: str = Field(min_length=1, max_length=200)
    location: str = Field(min_length=1, max_length=300)
    deviation_pct: float
    evidence_confidence: float = Field(ge=0.0, le=1.0)
    freshness_confidence: float = Field(ge=0.0, le=1.0)
    financial_materiality: float = Field(default=0.0, ge=0.0, le=1.0)
    legal_severity: float = Field(default=0.0, ge=0.0, le=1.0)
    safety_severity: float = Field(default=0.0, ge=0.0, le=1.0)
    time_to_impact_hours: float = Field(default=24.0, ge=0.0)
    provenance_refs: tuple[str, ...] = Field(min_length=1)

    @property
    def fingerprint(self) -> str:
        return "|".join(
            (
                self.domain.casefold().strip(),
                self.metric_name.casefold().strip(),
                self.location.casefold().strip(),
            )
        )


class GovernedActionProposal(BaseModel):
    action_id: str = Field(min_length=1, max_length=180)
    description: str = Field(min_length=1, max_length=1000)
    reversible: bool = True
    external_side_effect: bool = False
    irreversible: bool = False
    required_permission: str | None = Field(default=None, max_length=200)
    requires_human_approval: bool = False

    @model_validator(mode="after")
    def enforce_approval_boundary(self) -> "GovernedActionProposal":
        if (self.external_side_effect or self.irreversible) and not self.requires_human_approval:
            raise ValueError("side_effect_or_irreversible_action_requires_human_approval")
        if self.external_side_effect and not self.required_permission:
            raise ValueError("external_action_permission_required")
        return self


class RiskRadarItem(BaseModel):
    contract: str = PROACTIVE_INTELLIGENCE_CONTRACT
    signal_id: str
    fingerprint: str
    priority_score: float = Field(ge=0.0, le=1.0)
    risk_level: RiskLevel
    disposition: RadarDisposition
    requires_human_review: bool
    cascade_cluster: bool = False
    provenance_refs: tuple[str, ...]
    warnings: tuple[str, ...] = ()


class RiskRadar(BaseModel):
    contract: str = PROACTIVE_INTELLIGENCE_CONTRACT
    items: tuple[RiskRadarItem, ...]
    suppressed_duplicate_signal_ids: tuple[str, ...] = ()
    attention_count: int = 0
    escalation_count: int = 0


def _urgency(hours: float) -> float:
    return 1.0 / (1.0 + (hours / 24.0))


def _risk_level(score: float, severe_risk: float) -> RiskLevel:
    if severe_risk >= 0.90 or score >= 0.80:
        return RiskLevel.CRITICAL
    if severe_risk >= 0.70 or score >= 0.65:
        return RiskLevel.HIGH
    if score >= 0.45:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _disposition(score: float, risk: RiskLevel) -> RadarDisposition:
    if risk in {RiskLevel.CRITICAL, RiskLevel.HIGH} and score >= 0.60:
        return RadarDisposition.ESCALATE
    if score >= 0.45:
        return RadarDisposition.SURFACE
    if score >= 0.25:
        return RadarDisposition.WATCH
    return RadarDisposition.SUPPRESS


def score_executive_signal(signal: ExecutiveSignal) -> RiskRadarItem:
    materiality = min(abs(signal.deviation_pct) / 50.0, 1.0)
    urgency = _urgency(signal.time_to_impact_hours)
    severe_risk = max(signal.legal_severity, signal.safety_severity)
    evidence_quality = min(signal.evidence_confidence, signal.freshness_confidence)

    raw = (
        (0.30 * materiality)
        + (0.25 * signal.financial_materiality)
        + (0.25 * urgency)
        + (0.20 * severe_risk)
    )
    score = round(min(max(raw * evidence_quality, 0.0), 1.0), 6)
    risk = _risk_level(score, severe_risk)
    disposition = _disposition(score, risk)
    warnings: list[str] = []
    if signal.freshness_confidence < 0.50:
        warnings.append("stale_or_low_freshness_signal")
    if signal.evidence_confidence < 0.50:
        warnings.append("low_evidence_confidence")

    return RiskRadarItem(
        signal_id=signal.signal_id,
        fingerprint=signal.fingerprint,
        priority_score=score,
        risk_level=risk,
        disposition=disposition,
        requires_human_review=(risk in {RiskLevel.HIGH, RiskLevel.CRITICAL} or severe_risk >= 0.70),
        provenance_refs=signal.provenance_refs,
        warnings=tuple(warnings),
    )


def build_risk_radar(
    signals: list[ExecutiveSignal] | tuple[ExecutiveSignal, ...],
) -> RiskRadar:
    raw_items = [(signal, score_executive_signal(signal)) for signal in signals]

    best_by_fingerprint: dict[str, tuple[ExecutiveSignal, RiskRadarItem]] = {}
    suppressed_duplicates: list[str] = []
    for signal, item in raw_items:
        current = best_by_fingerprint.get(item.fingerprint)
        if current is None or item.priority_score > current[1].priority_score:
            if current is not None:
                suppressed_duplicates.append(current[0].signal_id)
            best_by_fingerprint[item.fingerprint] = (signal, item)
        else:
            suppressed_duplicates.append(signal.signal_id)

    location_domains: dict[str, set[str]] = defaultdict(set)
    for signal, item in best_by_fingerprint.values():
        if item.disposition is not RadarDisposition.SUPPRESS:
            location_domains[signal.location.casefold().strip()].add(signal.domain.casefold().strip())

    selected: list[RiskRadarItem] = []
    for signal, item in best_by_fingerprint.values():
        is_cluster = len(location_domains[signal.location.casefold().strip()]) >= 3
        if is_cluster:
            boosted_score = round(min(item.priority_score + 0.10, 1.0), 6)
            severe_risk = max(signal.legal_severity, signal.safety_severity)
            boosted_risk = _risk_level(boosted_score, severe_risk)
            item = item.model_copy(
                update={
                    "priority_score": boosted_score,
                    "risk_level": boosted_risk,
                    "disposition": _disposition(boosted_score, boosted_risk),
                    "requires_human_review": (
                        item.requires_human_review
                        or boosted_risk in {RiskLevel.HIGH, RiskLevel.CRITICAL}
                    ),
                    "cascade_cluster": True,
                    "warnings": tuple(dict.fromkeys((*item.warnings, "cross_domain_cascade_cluster"))),
                }
            )
        selected.append(item)

    selected.sort(key=lambda item: (-item.priority_score, item.signal_id))
    attention_count = sum(
        item.disposition in {RadarDisposition.SURFACE, RadarDisposition.ESCALATE}
        for item in selected
    )
    escalation_count = sum(item.disposition is RadarDisposition.ESCALATE for item in selected)

    return RiskRadar(
        items=tuple(selected),
        suppressed_duplicate_signal_ids=tuple(sorted(suppressed_duplicates)),
        attention_count=attention_count,
        escalation_count=escalation_count,
    )
