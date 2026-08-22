"""Adaptive research planning and evidence sufficiency for Jarvis.

The research engine does not browse the web itself. It creates a bounded,
auditable search mission and evaluates collected evidence. High-stakes or
executive conclusions require primary-source coverage, independent
corroboration, contradiction search, freshness, and explicit unresolved gaps.
Evidence published after the requested as-of boundary cannot leak backward
into a historical conclusion. A large result count is never proof by itself.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

RESEARCH_ENGINE_CONTRACT = "eay-adaptive-research-engine-v1"


class ResearchRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SourceTier(str, Enum):
    PRIMARY = "primary"
    AUTHORITATIVE_SECONDARY = "authoritative_secondary"
    REPUTABLE_SECONDARY = "reputable_secondary"
    DISCOVERY_ONLY = "discovery_only"


class ResearchRole(str, Enum):
    PRIMARY_SOURCE = "primary_source"
    CORROBORATION = "corroboration"
    CONTRADICTION = "contradiction"
    TEMPORAL_UPDATE = "temporal_update"
    DOMAIN_SPECIALIST = "domain_specialist"
    QUANTITATIVE_CHECK = "quantitative_check"


class ResearchQuestion(BaseModel):
    question_id: str = Field(min_length=1)
    question: str = Field(min_length=3)
    risk: ResearchRisk
    domains: tuple[str, ...] = ()
    as_of: datetime
    decision_deadline: datetime | None = None
    requires_current_information: bool = True
    enforce_as_of_information_boundary: bool = True
    minimum_independent_sources: int = Field(default=2, ge=1, le=10)

    @model_validator(mode="after")
    def temporal_contract(self) -> "ResearchQuestion":
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("research_as_of_requires_timezone")
        if self.decision_deadline is not None:
            if self.decision_deadline.tzinfo is None or self.decision_deadline.utcoffset() is None:
                raise ValueError("research_deadline_requires_timezone")
            if self.decision_deadline < self.as_of:
                raise ValueError("research_deadline_precedes_as_of")
        return self


class ResearchTask(BaseModel):
    task_id: str = Field(min_length=1)
    role: ResearchRole
    query_intent: str = Field(min_length=3)
    preferred_source_tiers: tuple[SourceTier, ...]
    required: bool = True
    max_results: int = Field(default=8, ge=1, le=25)


class ResearchMission(BaseModel):
    contract: str = RESEARCH_ENGINE_CONTRACT
    question_id: str
    tasks: tuple[ResearchTask, ...]
    maximum_total_results: int = Field(ge=1, le=200)
    contradiction_search_required: bool
    primary_source_required: bool
    quantitative_check_required: bool


class ResearchEvidence(BaseModel):
    evidence_id: str = Field(min_length=1)
    claim_key: str = Field(min_length=1)
    claim_value: str = Field(min_length=1)
    source_url: str = Field(min_length=8)
    source_domain: str = Field(min_length=1)
    source_tier: SourceTier
    publisher_key: str = Field(min_length=1)
    published_at: datetime | None = None
    fetched_at: datetime
    supports_claim: bool
    contradicts_claim: bool = False
    evidence_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def evidence_contract(self) -> "ResearchEvidence":
        if self.fetched_at.tzinfo is None or self.fetched_at.utcoffset() is None:
            raise ValueError("research_evidence_fetch_requires_timezone")
        if self.published_at is not None and (
            self.published_at.tzinfo is None or self.published_at.utcoffset() is None
        ):
            raise ValueError("research_evidence_publish_requires_timezone")
        if not self.source_url.startswith("https://"):
            raise ValueError("research_evidence_https_required")
        if self.supports_claim and self.contradicts_claim:
            raise ValueError("research_evidence_direction_ambiguous")
        return self


class ResearchVerdict(str, Enum):
    INSUFFICIENT = "insufficient"
    CONTESTED = "contested"
    SUPPORTED = "supported"


class ResearchAssessment(BaseModel):
    contract: str = RESEARCH_ENGINE_CONTRACT
    question_id: str
    claim_key: str
    verdict: ResearchVerdict
    independent_support_count: int
    independent_contradiction_count: int
    primary_source_present: bool
    stale_evidence_count: int
    temporally_unavailable_evidence_count: int = Field(ge=0)
    evidence_refs: tuple[str, ...]
    excluded_evidence_refs: tuple[str, ...] = ()
    confidence_cap: float = Field(ge=0.0, le=1.0)
    blockers: tuple[str, ...] = ()
    unresolved_gaps: tuple[str, ...] = ()


def plan_research(question: ResearchQuestion) -> ResearchMission:
    high_stakes = question.risk in {ResearchRisk.HIGH, ResearchRisk.CRITICAL}
    tasks: list[ResearchTask] = [
        ResearchTask(
            task_id=f"{question.question_id}:primary",
            role=ResearchRole.PRIMARY_SOURCE,
            query_intent=f"Find primary/official evidence for: {question.question}",
            preferred_source_tiers=(SourceTier.PRIMARY,),
            required=high_stakes,
        ),
        ResearchTask(
            task_id=f"{question.question_id}:corroborate",
            role=ResearchRole.CORROBORATION,
            query_intent=f"Find independent corroboration for: {question.question}",
            preferred_source_tiers=(
                SourceTier.PRIMARY,
                SourceTier.AUTHORITATIVE_SECONDARY,
                SourceTier.REPUTABLE_SECONDARY,
            ),
        ),
        ResearchTask(
            task_id=f"{question.question_id}:contradict",
            role=ResearchRole.CONTRADICTION,
            query_intent=f"Actively search for evidence that contradicts or weakens: {question.question}",
            preferred_source_tiers=(
                SourceTier.PRIMARY,
                SourceTier.AUTHORITATIVE_SECONDARY,
                SourceTier.REPUTABLE_SECONDARY,
            ),
            required=question.risk is not ResearchRisk.LOW,
        ),
    ]
    if question.requires_current_information:
        tasks.append(
            ResearchTask(
                task_id=f"{question.question_id}:current",
                role=ResearchRole.TEMPORAL_UPDATE,
                query_intent=f"Find the most recent authoritative update available as of {question.as_of.isoformat()}: {question.question}",
                preferred_source_tiers=(SourceTier.PRIMARY, SourceTier.AUTHORITATIVE_SECONDARY),
            )
        )
    if question.domains:
        tasks.append(
            ResearchTask(
                task_id=f"{question.question_id}:specialist",
                role=ResearchRole.DOMAIN_SPECIALIST,
                query_intent=f"Find domain-specialist evidence across {', '.join(question.domains)} for: {question.question}",
                preferred_source_tiers=(SourceTier.PRIMARY, SourceTier.AUTHORITATIVE_SECONDARY),
                required=high_stakes,
            )
        )
    quantitative = any(
        token in question.question.casefold()
        for token in ("%", "rate", "impact", "cost", "revenue", "margin", "kpi", "forecast", "kaç", "oran", "maliyet")
    )
    if quantitative:
        tasks.append(
            ResearchTask(
                task_id=f"{question.question_id}:quant",
                role=ResearchRole.QUANTITATIVE_CHECK,
                query_intent=f"Verify quantitative claims and denominators for: {question.question}",
                preferred_source_tiers=(SourceTier.PRIMARY, SourceTier.AUTHORITATIVE_SECONDARY),
            )
        )

    maximum = min(120 if high_stakes else 60, sum(task.max_results for task in tasks))
    return ResearchMission(
        question_id=question.question_id,
        tasks=tuple(tasks),
        maximum_total_results=maximum,
        contradiction_search_required=question.risk is not ResearchRisk.LOW,
        primary_source_required=high_stakes,
        quantitative_check_required=quantitative,
    )


def assess_research(
    question: ResearchQuestion,
    *,
    claim_key: str,
    evidence: list[ResearchEvidence],
    freshness_window: timedelta = timedelta(days=30),
) -> ResearchAssessment:
    claim_evidence = [item for item in evidence if item.claim_key == claim_key]
    temporally_unavailable = [
        item
        for item in claim_evidence
        if question.enforce_as_of_information_boundary
        and item.published_at is not None
        and item.published_at > question.as_of
    ]
    unavailable_ids = {item.evidence_id for item in temporally_unavailable}
    current = [item for item in claim_evidence if item.evidence_id not in unavailable_ids]

    evidence_refs = tuple(sorted({item.evidence_ref for item in current}))
    excluded_refs = tuple(sorted({item.evidence_ref for item in temporally_unavailable}))
    support = [item for item in current if item.supports_claim]
    contradict = [item for item in current if item.contradicts_claim]

    support_publishers = {item.publisher_key for item in support}
    contradict_publishers = {item.publisher_key for item in contradict}
    primary_present = any(item.source_tier is SourceTier.PRIMARY for item in support)
    stale = [
        item
        for item in current
        if question.requires_current_information and question.as_of - item.fetched_at > freshness_window
    ]

    blockers: list[str] = []
    gaps: list[str] = []
    high_stakes = question.risk in {ResearchRisk.HIGH, ResearchRisk.CRITICAL}
    if temporally_unavailable:
        blockers.append("research_evidence_not_available_as_of")
        gaps.append("replace_future_published_evidence")
    if high_stakes and not primary_present:
        blockers.append("research_primary_source_missing")
        gaps.append("obtain_primary_source")
    if len(support_publishers) < question.minimum_independent_sources:
        blockers.append("research_independent_support_quorum_missing")
        gaps.append("find_independent_corroboration")
    if question.risk is not ResearchRisk.LOW and not current:
        blockers.append("research_no_eligible_evidence")
    if stale and len(stale) == len(current):
        blockers.append("research_evidence_stale_only")
        gaps.append("refresh_evidence")

    if support and contradict:
        verdict = ResearchVerdict.CONTESTED
        blockers.append("research_material_contradiction_unresolved")
        gaps.append("resolve_contradictory_evidence")
        confidence_cap = 0.60
    elif blockers:
        verdict = ResearchVerdict.INSUFFICIENT
        confidence_cap = 0.55 if current else 0.20
    elif support:
        verdict = ResearchVerdict.SUPPORTED
        confidence_cap = 0.95 if primary_present else 0.80
    else:
        verdict = ResearchVerdict.INSUFFICIENT
        blockers.append("research_claim_not_supported")
        confidence_cap = 0.20

    return ResearchAssessment(
        question_id=question.question_id,
        claim_key=claim_key,
        verdict=verdict,
        independent_support_count=len(support_publishers),
        independent_contradiction_count=len(contradict_publishers),
        primary_source_present=primary_present,
        stale_evidence_count=len(stale),
        temporally_unavailable_evidence_count=len(temporally_unavailable),
        evidence_refs=evidence_refs,
        excluded_evidence_refs=excluded_refs,
        confidence_cap=confidence_cap,
        blockers=tuple(dict.fromkeys(blockers)),
        unresolved_gaps=tuple(dict.fromkeys(gaps)),
    )
