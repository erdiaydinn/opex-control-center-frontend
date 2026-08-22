"""Governed external-context correlation for EAY Jarvis.

The engine connects time-bounded external signals (weather, city events, road
closures, macro/news context) to governed operational observations without
turning correlation into a causal claim. It does not fetch the web, execute
queries, mutate KPI truth, or promote legal/news signals into binding law.

Provider adapters are expected to normalize their evidence into ContextSignal;
internal metrics must arrive as governed OperationalObservation objects from the
existing tenant-safe data/tool path.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

CONTEXT_INTELLIGENCE_CONTRACT = "eay-context-intelligence-v1"
MATERIAL_DEVIATION_PCT = 5.0


class ContextKind(str, Enum):
    WEATHER = "weather"
    CITY_EVENT = "city_event"
    ROAD_CLOSURE = "road_closure"
    TRANSIT_DISRUPTION = "transit_disruption"
    NEWS_AGENDA = "news_agenda"
    MACRO_ECONOMIC = "macro_economic"
    REGULATORY_SIGNAL = "regulatory_signal"
    LOCAL_INCIDENT = "local_incident"


class ContextSourceClass(str, Enum):
    OFFICIAL = "official"
    VERIFIED_PROVIDER = "verified_provider"
    REPUTABLE_NEWS = "reputable_news"
    INTERNAL_ANALYST = "internal_analyst"


class ImpactDimension(str, Enum):
    DEMAND = "demand"
    ORDER_VOLUME = "order_volume"
    STORE_ACCESS = "store_access"
    DELIVERY_SPEED = "delivery_speed"
    RIDER_CAPACITY = "rider_capacity"
    PICKER_CAPACITY = "picker_capacity"
    CLOSURE_TIME = "closure_time"
    PREP_TIME = "prep_time"
    AVAILABILITY = "availability"
    CUSTOMER_EXPERIENCE = "customer_experience"
    COST = "cost"
    REVENUE = "revenue"
    MARGIN = "margin"
    LABOR = "labor"
    COMPLIANCE = "compliance"


class RelationStatus(str, Enum):
    PLAUSIBLE_CONTRIBUTOR = "plausible_contributor"
    CONTEXT_CANDIDATE = "context_candidate"
    INSUFFICIENT = "insufficient"


_SOURCE_WEIGHT = {
    ContextSourceClass.OFFICIAL: 1.00,
    ContextSourceClass.VERIFIED_PROVIDER: 0.90,
    ContextSourceClass.REPUTABLE_NEWS: 0.75,
    ContextSourceClass.INTERNAL_ANALYST: 0.70,
}


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _norm_location(value: str) -> str:
    folded = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.split())


def _https_source(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("context_source_https_required")


class ContextSignal(BaseModel):
    signal_id: str = Field(min_length=1, max_length=160)
    kind: ContextKind
    title: str = Field(min_length=1, max_length=500)
    starts_at: datetime
    ends_at: datetime
    observed_at: datetime
    locations: tuple[str, ...] = Field(min_length=1)
    expected_impacts: tuple[ImpactDimension, ...] = Field(min_length=1)
    source_name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    source_class: ContextSourceClass
    source_confidence: float = Field(ge=0.0, le=1.0)
    context_only: bool = True
    binding_legal_evidence: bool = False

    @model_validator(mode="after")
    def validate_boundary(self) -> "ContextSignal":
        if not all(_aware(item) for item in (self.starts_at, self.ends_at, self.observed_at)):
            raise ValueError("context_signal_timezone_required")
        if self.ends_at < self.starts_at:
            raise ValueError("context_signal_invalid_interval")
        if not self.context_only or self.binding_legal_evidence:
            raise ValueError("context_signal_cannot_be_binding_authority")
        if not any(item.strip() for item in self.locations):
            raise ValueError("context_signal_location_required")
        _https_source(self.source_url)
        return self


class OperationalObservation(BaseModel):
    observation_id: str = Field(min_length=1, max_length=160)
    metric_name: str = Field(min_length=1, max_length=200)
    impact_dimension: ImpactDimension
    value: float
    baseline_value: float | None = None
    unit: str = Field(min_length=1, max_length=80)
    starts_at: datetime
    ends_at: datetime
    locations: tuple[str, ...] = Field(min_length=1)
    provenance_ref: str = Field(min_length=1, max_length=500)
    governed_operational_truth: bool = True

    @model_validator(mode="after")
    def validate_governance(self) -> "OperationalObservation":
        if not all(_aware(item) for item in (self.starts_at, self.ends_at)):
            raise ValueError("operational_observation_timezone_required")
        if self.ends_at < self.starts_at:
            raise ValueError("operational_observation_invalid_interval")
        if not self.governed_operational_truth:
            raise ValueError("governed_operational_truth_required")
        if not any(item.strip() for item in self.locations):
            raise ValueError("operational_observation_location_required")
        return self

    @property
    def deviation_pct(self) -> float | None:
        if self.baseline_value in (None, 0):
            return None
        return round((self.value - self.baseline_value) * 100.0 / self.baseline_value, 4)


class ContextRelation(BaseModel):
    signal_id: str
    observation_id: str
    status: RelationStatus
    score: float = Field(ge=0.0, le=1.0)
    temporal_overlap: float = Field(ge=0.0, le=1.0)
    geographic_overlap: float = Field(ge=0.0, le=1.0)
    semantic_overlap: float = Field(ge=0.0, le=1.0)
    anomaly_strength: float = Field(ge=0.0, le=1.0)
    deviation_pct: float | None = None
    causality_proven: bool = False
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ("correlation_is_not_causation",)

    @model_validator(mode="after")
    def prohibit_causal_claim(self) -> "ContextRelation":
        if self.causality_proven:
            raise ValueError("context_engine_cannot_assert_causality")
        return self


class ContextInsight(BaseModel):
    contract: str = CONTEXT_INTELLIGENCE_CONTRACT
    signal_id: str
    status: RelationStatus
    confidence: float = Field(ge=0.0, le=1.0)
    relations: tuple[ContextRelation, ...]
    evidence_refs: tuple[str, ...]
    summary: str
    causality_proven: bool = False
    warnings: tuple[str, ...] = (
        "correlation_is_not_causation",
        "external_context_never_overrides_governed_operational_truth",
    )


def _temporal_overlap(signal: ContextSignal, observation: OperationalObservation) -> float:
    start = max(signal.starts_at, observation.starts_at)
    end = min(signal.ends_at, observation.ends_at)
    if end < start:
        return 0.0
    observation_seconds = max((observation.ends_at - observation.starts_at).total_seconds(), 1.0)
    overlap_seconds = max((end - start).total_seconds(), 1.0)
    return round(min(overlap_seconds / observation_seconds, 1.0), 6)


def _geographic_overlap(signal: ContextSignal, observation: OperationalObservation) -> float:
    signal_locations = {_norm_location(item) for item in signal.locations if item.strip()}
    observation_locations = {_norm_location(item) for item in observation.locations if item.strip()}
    if "global" in signal_locations:
        return 1.0
    if signal_locations & observation_locations:
        return 1.0
    return 0.0


def _semantic_overlap(signal: ContextSignal, observation: OperationalObservation) -> float:
    return 1.0 if observation.impact_dimension in set(signal.expected_impacts) else 0.0


def _anomaly_strength(observation: OperationalObservation) -> float:
    deviation = observation.deviation_pct
    if deviation is None:
        return 0.0
    return round(min(abs(deviation) / 20.0, 1.0), 6)


def assess_relation(signal: ContextSignal, observation: OperationalObservation) -> ContextRelation:
    temporal = _temporal_overlap(signal, observation)
    geographic = _geographic_overlap(signal, observation)
    semantic = _semantic_overlap(signal, observation)
    deviation = observation.deviation_pct
    anomaly = _anomaly_strength(observation)
    blockers: list[str] = []
    warnings = ["correlation_is_not_causation"]

    if temporal == 0.0:
        blockers.append("no_temporal_overlap")
    if geographic == 0.0:
        blockers.append("no_geographic_overlap")
    if semantic == 0.0:
        blockers.append("impact_dimension_mismatch")
    if deviation is None:
        warnings.append("baseline_evidence_missing")
    elif abs(deviation) < MATERIAL_DEVIATION_PCT:
        blockers.append("operational_anomaly_not_material")

    weighted_overlap = (
        (0.35 * temporal)
        + (0.25 * geographic)
        + (0.20 * semantic)
        + (0.20 * anomaly)
    )
    score = round(
        weighted_overlap * signal.source_confidence * _SOURCE_WEIGHT[signal.source_class],
        6,
    )
    if blockers:
        status = RelationStatus.INSUFFICIENT
    elif deviation is None:
        status = (
            RelationStatus.CONTEXT_CANDIDATE
            if score >= 0.45
            else RelationStatus.INSUFFICIENT
        )
    elif score >= 0.65:
        status = RelationStatus.PLAUSIBLE_CONTRIBUTOR
    elif score >= 0.45:
        status = RelationStatus.CONTEXT_CANDIDATE
    else:
        status = RelationStatus.INSUFFICIENT

    return ContextRelation(
        signal_id=signal.signal_id,
        observation_id=observation.observation_id,
        status=status,
        score=score,
        temporal_overlap=temporal,
        geographic_overlap=geographic,
        semantic_overlap=semantic,
        anomaly_strength=anomaly,
        deviation_pct=deviation,
        evidence_refs=(signal.source_url, observation.provenance_ref),
        blockers=tuple(blockers),
        warnings=tuple(warnings),
    )


def build_context_insight(
    signal: ContextSignal,
    observations: list[OperationalObservation] | tuple[OperationalObservation, ...],
) -> ContextInsight:
    relations = tuple(assess_relation(signal, item) for item in observations)
    supporting = [item for item in relations if item.status is RelationStatus.PLAUSIBLE_CONTRIBUTOR]
    candidates = [item for item in relations if item.status is RelationStatus.CONTEXT_CANDIDATE]

    if supporting:
        status = RelationStatus.PLAUSIBLE_CONTRIBUTOR
        confidence = round(sum(item.score for item in supporting) / len(supporting), 6)
        summary = (
            f"{signal.title} zaman, coğrafya, ilgili etki boyutu ve anlamlı operasyon sapmasıyla "
            "örtüşüyor; olası katkı faktörü olarak değerlendirilmelidir, nedensellik kanıtı değildir."
        )
    elif candidates:
        status = RelationStatus.CONTEXT_CANDIDATE
        confidence = round(sum(item.score for item in candidates) / len(candidates), 6)
        summary = (
            f"{signal.title} operasyonel değişimle kısmi bağlam örtüşmesi gösteriyor; ek baseline veya "
            "karşılaştırma kanıtı olmadan etki ya da nedensellik sonucu çıkarılmamalıdır."
        )
    else:
        status = RelationStatus.INSUFFICIENT
        confidence = 0.0
        summary = (
            f"{signal.title} ile verilen operasyon gözlemleri arasında güvenilir bağ kurmak için kanıt yetersiz."
        )

    evidence_refs = tuple(
        dict.fromkeys(ref for relation in relations for ref in relation.evidence_refs)
    )
    return ContextInsight(
        signal_id=signal.signal_id,
        status=status,
        confidence=confidence,
        relations=relations,
        evidence_refs=evidence_refs,
        summary=summary,
    )
