"""Source-quality governance for EAY Jarvis external context.

Jarvis must not treat every fresh-looking webpage as equivalent evidence. This
module evaluates source freshness, independence, authority and contradictions
before external context is allowed to influence executive reasoning. It does
not fetch the network and it never promotes context into binding legal truth.
"""

from __future__ import annotations

import unicodedata
from datetime import datetime, timedelta
from enum import Enum
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .context_intelligence import ContextKind, ContextSourceClass

SOURCE_GOVERNANCE_CONTRACT = "eay-context-source-governance-v1"


class SourceGovernanceStatus(str, Enum):
    TRUSTED = "trusted"
    DEGRADED = "degraded"
    BLOCKED = "blocked"


class FreshnessPolicy(BaseModel):
    max_age_minutes: int = Field(gt=0)
    min_independent_sources: int = Field(ge=1)
    require_official_source: bool = False


DEFAULT_FRESHNESS_POLICIES: dict[ContextKind, FreshnessPolicy] = {
    ContextKind.WEATHER: FreshnessPolicy(max_age_minutes=120, min_independent_sources=1),
    ContextKind.CITY_EVENT: FreshnessPolicy(max_age_minutes=1440, min_independent_sources=1),
    ContextKind.ROAD_CLOSURE: FreshnessPolicy(max_age_minutes=120, min_independent_sources=1),
    ContextKind.TRANSIT_DISRUPTION: FreshnessPolicy(max_age_minutes=60, min_independent_sources=1),
    ContextKind.NEWS_AGENDA: FreshnessPolicy(max_age_minutes=360, min_independent_sources=2),
    ContextKind.MACRO_ECONOMIC: FreshnessPolicy(
        max_age_minutes=43_200,
        min_independent_sources=1,
        require_official_source=True,
    ),
    ContextKind.REGULATORY_SIGNAL: FreshnessPolicy(
        max_age_minutes=1440,
        min_independent_sources=1,
        require_official_source=True,
    ),
    ContextKind.LOCAL_INCIDENT: FreshnessPolicy(max_age_minutes=120, min_independent_sources=2),
}


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _domain(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("source_evidence_https_required")
    return parsed.hostname.casefold()


def _normalize_claim(value: str) -> str:
    folded = value.casefold().replace("ı", "i")
    decomposed = unicodedata.normalize("NFKD", folded)
    without_marks = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(without_marks.split())


class SourceEvidence(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=180)
    kind: ContextKind
    claim_key: str = Field(min_length=1, max_length=240)
    claim_value: str = Field(min_length=1, max_length=2000)
    observed_at: datetime
    fetched_at: datetime
    source_name: str = Field(min_length=1, max_length=300)
    source_url: str = Field(min_length=1, max_length=2048)
    source_class: ContextSourceClass
    source_confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_evidence(self) -> "SourceEvidence":
        if not _aware(self.observed_at) or not _aware(self.fetched_at):
            raise ValueError("source_evidence_timezone_required")
        if self.fetched_at < self.observed_at:
            raise ValueError("source_evidence_fetch_before_observation")
        _domain(self.source_url)
        return self

    @property
    def source_domain(self) -> str:
        return _domain(self.source_url)


class SourceGovernanceReport(BaseModel):
    contract: str = SOURCE_GOVERNANCE_CONTRACT
    kind: ContextKind
    status: SourceGovernanceStatus
    usable_evidence_ids: tuple[str, ...] = ()
    stale_evidence_ids: tuple[str, ...] = ()
    contradiction_keys: tuple[str, ...] = ()
    source_domains: tuple[str, ...] = ()
    independent_source_count: int = 0
    official_source_present: bool = False
    confidence_cap: float = Field(ge=0.0, le=1.0)
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()


def evaluate_source_evidence(
    evidence: list[SourceEvidence] | tuple[SourceEvidence, ...],
    *,
    now: datetime,
    kind: ContextKind,
    policy: FreshnessPolicy | None = None,
) -> SourceGovernanceReport:
    if not _aware(now):
        raise ValueError("source_governance_now_timezone_required")

    selected_policy = policy or DEFAULT_FRESHNESS_POLICIES[kind]
    kind_evidence = [item for item in evidence if item.kind is kind]
    if not kind_evidence:
        return SourceGovernanceReport(
            kind=kind,
            status=SourceGovernanceStatus.BLOCKED,
            confidence_cap=0.0,
            blockers=("source_evidence_missing",),
        )

    max_age = timedelta(minutes=selected_policy.max_age_minutes)
    usable: list[SourceEvidence] = []
    stale: list[SourceEvidence] = []
    warnings: list[str] = []
    blockers: list[str] = []

    for item in kind_evidence:
        if item.fetched_at > now + timedelta(minutes=5):
            blockers.append("source_evidence_future_fetch_timestamp")
            continue
        age = now - item.fetched_at
        if age > max_age:
            stale.append(item)
        else:
            usable.append(item)

    if not usable:
        blockers.append("fresh_source_evidence_missing")

    domains = tuple(sorted({item.source_domain for item in usable}))
    official_present = any(item.source_class is ContextSourceClass.OFFICIAL for item in usable)
    if len(domains) < selected_policy.min_independent_sources:
        blockers.append("independent_source_quorum_missing")
    if selected_policy.require_official_source and not official_present:
        blockers.append("official_source_required")

    values_by_key: dict[str, set[str]] = {}
    for item in usable:
        values_by_key.setdefault(item.claim_key, set()).add(_normalize_claim(item.claim_value))
    contradiction_keys = tuple(
        sorted(key for key, values in values_by_key.items() if len(values) > 1)
    )
    if contradiction_keys:
        warnings.append("source_claim_contradiction_detected")

    base_confidence = (
        sum(item.source_confidence for item in usable) / len(usable)
        if usable
        else 0.0
    )
    confidence_cap = min(base_confidence, 0.95)
    if stale:
        warnings.append("stale_source_evidence_present")
        confidence_cap = min(confidence_cap, 0.85)
    if contradiction_keys:
        confidence_cap = min(confidence_cap, 0.55 if official_present else 0.40)
    if blockers:
        confidence_cap = min(confidence_cap, 0.40)

    if blockers:
        status = SourceGovernanceStatus.BLOCKED
    elif contradiction_keys or stale:
        status = SourceGovernanceStatus.DEGRADED
    else:
        status = SourceGovernanceStatus.TRUSTED

    return SourceGovernanceReport(
        kind=kind,
        status=status,
        usable_evidence_ids=tuple(item.evidence_id for item in usable),
        stale_evidence_ids=tuple(item.evidence_id for item in stale),
        contradiction_keys=contradiction_keys,
        source_domains=domains,
        independent_source_count=len(domains),
        official_source_present=official_present,
        confidence_cap=round(max(0.0, confidence_cap), 6),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
    )
