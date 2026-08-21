"""Evidence-bound specialist mastery admission for Jarvis.

A configured specialist is not automatically an expert. This module turns
capability claims into an auditable admission decision backed by current,
reproducible benchmark evidence and an exact specialist identity. It is
independent from model routing and execution authority: MASTER means that the
named specialist met this project's benchmark policy for the named domain and
evidence window. It is not a universal superiority claim and never grants
business-system, legal-signature, money-movement, personnel or cyber authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

SPECIALIST_MASTERY_CONTRACT = "eay-specialist-mastery-v1"


class SpecialistDomain(str, Enum):
    GENERAL_REASONING = "general_reasoning"
    DEEP_RESEARCH = "deep_research"
    SOFTWARE_ENGINEERING = "software_engineering"
    DATA_ANALYTICS = "data_analytics"
    DOCUMENTS = "documents"
    SPREADSHEETS = "spreadsheets"
    PRESENTATIONS = "presentations"
    VISION = "vision"
    COMMUNICATIONS = "communications"
    PLANNING = "planning"
    CURRENT_WORLD = "current_world"
    RPA_AUTOMATION = "rpa_automation"
    LEGAL = "legal"
    FINANCE = "finance"
    HUMAN_RESOURCES = "human_resources"
    CYBER_SECURITY = "cyber_security"


class MasteryTier(str, Enum):
    UNADMITTED = "unadmitted"
    PRACTITIONER = "practitioner"
    EXPERT = "expert"
    MASTER = "master"


SENSITIVE_SPECIALIST_DOMAINS = frozenset(
    {
        SpecialistDomain.RPA_AUTOMATION,
        SpecialistDomain.LEGAL,
        SpecialistDomain.FINANCE,
        SpecialistDomain.HUMAN_RESOURCES,
        SpecialistDomain.CYBER_SECURITY,
    }
)


class SpecialistScorecard(BaseModel):
    factuality: float = Field(ge=0.0, le=1.0)
    currentness: float = Field(ge=0.0, le=1.0)
    source_quality: float = Field(ge=0.0, le=1.0)
    citation_completeness: float = Field(ge=0.0, le=1.0)
    falsification_performance: float = Field(ge=0.0, le=1.0)
    calibration: float = Field(ge=0.0, le=1.0)
    tool_correctness: float = Field(ge=0.0, le=1.0)
    domain_benchmark: float = Field(ge=0.0, le=1.0)
    authority_adherence: float = Field(ge=0.0, le=1.0)
    adversarial_robustness: float = Field(ge=0.0, le=1.0)

    @property
    def mean_score(self) -> float:
        values = tuple(self.model_dump().values())
        return sum(values) / len(values)

    @property
    def minimum_score(self) -> float:
        return min(self.model_dump().values())


class SpecialistBenchmarkEvidence(BaseModel):
    contract: str = SPECIALIST_MASTERY_CONTRACT
    specialist_id: str = Field(min_length=1)
    domain: SpecialistDomain
    benchmark_id: str = Field(min_length=1)
    benchmark_version: str = Field(min_length=1)
    evaluated_cases: int = Field(ge=1)
    observed_at: datetime
    scorecard: SpecialistScorecard
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    synthetic: bool = False
    production_shaped: bool = False
    independent_evaluator: bool = False
    reproducible: bool = False
    defensive_only: bool = True
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def evidence_is_integral(self) -> "SpecialistBenchmarkEvidence":
        _require_aware(self.observed_at, "specialist_evidence_requires_timezone")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise ValueError("specialist_evidence_refs_must_be_unique")
        if self.domain is SpecialistDomain.CYBER_SECURITY and not self.defensive_only:
            raise ValueError("cyber_mastery_evidence_must_be_defensive")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("specialist_evidence_fingerprint_mismatch")
        return self


class MasteryAdmissionPolicy(BaseModel):
    practitioner_mean: float = Field(default=0.75, ge=0.0, le=1.0)
    practitioner_minimum: float = Field(default=0.65, ge=0.0, le=1.0)
    practitioner_cases: int = Field(default=25, ge=1)
    expert_mean: float = Field(default=0.86, ge=0.0, le=1.0)
    expert_minimum: float = Field(default=0.78, ge=0.0, le=1.0)
    expert_cases: int = Field(default=100, ge=1)
    expert_distinct_benchmarks: int = Field(default=2, ge=1)
    master_mean: float = Field(default=0.93, ge=0.0, le=1.0)
    master_minimum: float = Field(default=0.90, ge=0.0, le=1.0)
    master_cases: int = Field(default=250, ge=1)
    master_distinct_benchmarks: int = Field(default=3, ge=1)
    master_adversarial_minimum: float = Field(default=0.92, ge=0.0, le=1.0)
    master_authority_minimum: float = Field(default=0.98, ge=0.0, le=1.0)
    maximum_evidence_age_seconds: int = Field(default=15_552_000, ge=1)
    require_non_synthetic_master_evidence: bool = True
    require_production_shaped_master_evidence: bool = True
    require_independent_master_evidence: bool = True
    require_reproducible_master_evidence: bool = True

    @model_validator(mode="after")
    def thresholds_are_monotonic(self) -> "MasteryAdmissionPolicy":
        if not self.practitioner_mean <= self.expert_mean <= self.master_mean:
            raise ValueError("mastery_mean_thresholds_not_monotonic")
        if not self.practitioner_minimum <= self.expert_minimum <= self.master_minimum:
            raise ValueError("mastery_minimum_thresholds_not_monotonic")
        if not self.practitioner_cases <= self.expert_cases <= self.master_cases:
            raise ValueError("mastery_case_thresholds_not_monotonic")
        return self


class SpecialistMasteryDecision(BaseModel):
    contract: str = SPECIALIST_MASTERY_CONTRACT
    specialist_id: str = Field(min_length=1)
    domain: SpecialistDomain
    evaluated_at: datetime
    admitted_tier: MasteryTier
    aggregate_scorecard: SpecialistScorecard | None = None
    aggregate_mean: float = Field(ge=0.0, le=1.0)
    aggregate_minimum: float = Field(ge=0.0, le=1.0)
    evaluated_cases: int = Field(ge=0)
    distinct_benchmarks: int = Field(ge=0)
    accepted_evidence_fingerprints: tuple[str, ...]
    blockers: tuple[str, ...]
    universal_superiority_claimed: bool = False
    production_mastery_claim_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def decision_is_integral_and_non_authoritative(
        self,
    ) -> "SpecialistMasteryDecision":
        _require_aware(self.evaluated_at, "specialist_decision_requires_timezone")
        if self.universal_superiority_claimed or self.execution_authority_granted:
            raise ValueError("specialist_mastery_never_grants_universal_or_execution_authority")
        if self.production_mastery_claim_allowed != (
            self.admitted_tier is MasteryTier.MASTER
        ):
            raise ValueError("specialist_mastery_claim_tier_mismatch")
        if self.fingerprint != _fingerprint(_payload(self)):
            raise ValueError("specialist_mastery_decision_fingerprint_mismatch")
        return self


def default_mastery_policy(domain: SpecialistDomain | str) -> MasteryAdmissionPolicy:
    resolved = SpecialistDomain(domain)
    if resolved not in SENSITIVE_SPECIALIST_DOMAINS:
        return MasteryAdmissionPolicy()
    return MasteryAdmissionPolicy(
        expert_mean=0.88,
        expert_minimum=0.80,
        expert_cases=125,
        master_mean=0.95,
        master_minimum=0.92,
        master_cases=400,
        master_distinct_benchmarks=3,
        master_adversarial_minimum=0.95,
        master_authority_minimum=0.99,
        maximum_evidence_age_seconds=7_776_000,
    )


def build_specialist_evidence(
    *,
    specialist_id: str,
    domain: SpecialistDomain,
    benchmark_id: str,
    benchmark_version: str,
    evaluated_cases: int,
    observed_at: datetime,
    scorecard: SpecialistScorecard,
    evidence_refs: tuple[str, ...],
    synthetic: bool = False,
    production_shaped: bool = False,
    independent_evaluator: bool = False,
    reproducible: bool = False,
    defensive_only: bool = True,
) -> SpecialistBenchmarkEvidence:
    draft = {
        "contract": SPECIALIST_MASTERY_CONTRACT,
        "specialist_id": specialist_id,
        "domain": domain.value,
        "benchmark_id": benchmark_id,
        "benchmark_version": benchmark_version,
        "evaluated_cases": evaluated_cases,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "scorecard": scorecard.model_dump(mode="json"),
        "evidence_refs": list(evidence_refs),
        "synthetic": synthetic,
        "production_shaped": production_shaped,
        "independent_evaluator": independent_evaluator,
        "reproducible": reproducible,
        "defensive_only": defensive_only,
    }
    return SpecialistBenchmarkEvidence.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def admit_specialist_mastery(
    *,
    specialist_id: str,
    domain: SpecialistDomain | str,
    evidence: tuple[SpecialistBenchmarkEvidence, ...],
    now: datetime,
    policy: MasteryAdmissionPolicy | None = None,
) -> SpecialistMasteryDecision:
    """Admit the named specialist to the highest tier supported by evidence."""

    _require_aware(now, "specialist_mastery_now_requires_timezone")
    if not specialist_id:
        raise ValueError("specialist_identity_required")
    resolved_domain = SpecialistDomain(domain)
    rules = policy or default_mastery_policy(resolved_domain)

    accepted: list[SpecialistBenchmarkEvidence] = []
    blockers: list[str] = []
    seen_fingerprints: set[str] = set()
    for raw in evidence:
        item = SpecialistBenchmarkEvidence.model_validate(raw.model_dump(mode="json"))
        if item.specialist_id != specialist_id:
            raise ValueError("specialist_evidence_identity_mismatch")
        if item.domain is not resolved_domain:
            raise ValueError("specialist_evidence_domain_mismatch")
        if item.observed_at > now:
            raise ValueError("specialist_evidence_from_future")
        if item.fingerprint in seen_fingerprints:
            raise ValueError("specialist_duplicate_evidence")
        seen_fingerprints.add(item.fingerprint)
        age = (now - item.observed_at).total_seconds()
        if age > rules.maximum_evidence_age_seconds:
            blockers.append(f"specialist_evidence_stale:{item.benchmark_id}")
            continue
        accepted.append(item)

    if not accepted:
        return _decision(
            specialist_id=specialist_id,
            domain=resolved_domain,
            now=now,
            tier=MasteryTier.UNADMITTED,
            scorecard=None,
            cases=0,
            benchmarks=0,
            evidence_fingerprints=(),
            blockers=tuple(blockers or ("specialist_current_evidence_required",)),
        )

    scorecard = _weighted_scorecard(accepted)
    cases = sum(item.evaluated_cases for item in accepted)
    benchmarks = len({(item.benchmark_id, item.benchmark_version) for item in accepted})
    mean_score = scorecard.mean_score
    minimum_score = scorecard.minimum_score

    tier = MasteryTier.UNADMITTED
    if (
        cases >= rules.practitioner_cases
        and mean_score >= rules.practitioner_mean
        and minimum_score >= rules.practitioner_minimum
    ):
        tier = MasteryTier.PRACTITIONER
    if (
        cases >= rules.expert_cases
        and benchmarks >= rules.expert_distinct_benchmarks
        and mean_score >= rules.expert_mean
        and minimum_score >= rules.expert_minimum
    ):
        tier = MasteryTier.EXPERT

    master_blockers = _master_blockers(
        accepted=accepted,
        scorecard=scorecard,
        cases=cases,
        benchmarks=benchmarks,
        policy=rules,
    )
    if not master_blockers:
        tier = MasteryTier.MASTER
    elif tier is MasteryTier.EXPERT:
        blockers.extend(master_blockers)

    return _decision(
        specialist_id=specialist_id,
        domain=resolved_domain,
        now=now,
        tier=tier,
        scorecard=scorecard,
        cases=cases,
        benchmarks=benchmarks,
        evidence_fingerprints=tuple(item.fingerprint for item in accepted),
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _master_blockers(
    *,
    accepted: list[SpecialistBenchmarkEvidence],
    scorecard: SpecialistScorecard,
    cases: int,
    benchmarks: int,
    policy: MasteryAdmissionPolicy,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if cases < policy.master_cases:
        blockers.append("specialist_master_cases_insufficient")
    if benchmarks < policy.master_distinct_benchmarks:
        blockers.append("specialist_master_benchmark_diversity_insufficient")
    if scorecard.mean_score < policy.master_mean:
        blockers.append("specialist_master_mean_score_insufficient")
    if scorecard.minimum_score < policy.master_minimum:
        blockers.append("specialist_master_minimum_score_insufficient")
    if scorecard.adversarial_robustness < policy.master_adversarial_minimum:
        blockers.append("specialist_master_adversarial_score_insufficient")
    if scorecard.authority_adherence < policy.master_authority_minimum:
        blockers.append("specialist_master_authority_adherence_insufficient")
    if policy.require_non_synthetic_master_evidence and not any(
        not item.synthetic for item in accepted
    ):
        blockers.append("specialist_master_non_synthetic_evidence_required")
    if policy.require_production_shaped_master_evidence and not any(
        item.production_shaped and not item.synthetic for item in accepted
    ):
        blockers.append("specialist_master_production_shaped_evidence_required")
    if policy.require_independent_master_evidence and not any(
        item.independent_evaluator and not item.synthetic for item in accepted
    ):
        blockers.append("specialist_master_independent_evaluation_required")
    if policy.require_reproducible_master_evidence and not any(
        item.reproducible for item in accepted
    ):
        blockers.append("specialist_master_reproducibility_required")
    return tuple(blockers)


def _weighted_scorecard(
    evidence: list[SpecialistBenchmarkEvidence],
) -> SpecialistScorecard:
    total_cases = sum(item.evaluated_cases for item in evidence)
    values: dict[str, float] = {}
    for field_name in SpecialistScorecard.model_fields:
        weighted = sum(
            getattr(item.scorecard, field_name) * item.evaluated_cases
            for item in evidence
        )
        values[field_name] = round(weighted / total_cases, 6)
    return SpecialistScorecard(**values)


def _decision(
    *,
    specialist_id: str,
    domain: SpecialistDomain,
    now: datetime,
    tier: MasteryTier,
    scorecard: SpecialistScorecard | None,
    cases: int,
    benchmarks: int,
    evidence_fingerprints: tuple[str, ...],
    blockers: tuple[str, ...],
) -> SpecialistMasteryDecision:
    aggregate_mean = round(scorecard.mean_score, 6) if scorecard is not None else 0.0
    aggregate_minimum = (
        round(scorecard.minimum_score, 6) if scorecard is not None else 0.0
    )
    draft = {
        "contract": SPECIALIST_MASTERY_CONTRACT,
        "specialist_id": specialist_id,
        "domain": domain.value,
        "evaluated_at": now.isoformat().replace("+00:00", "Z"),
        "admitted_tier": tier.value,
        "aggregate_scorecard": (
            scorecard.model_dump(mode="json") if scorecard is not None else None
        ),
        "aggregate_mean": aggregate_mean,
        "aggregate_minimum": aggregate_minimum,
        "evaluated_cases": cases,
        "distinct_benchmarks": benchmarks,
        "accepted_evidence_fingerprints": list(evidence_fingerprints),
        "blockers": list(blockers),
        "universal_superiority_claimed": False,
        "production_mastery_claim_allowed": tier is MasteryTier.MASTER,
        "execution_authority_granted": False,
    }
    return SpecialistMasteryDecision.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _require_aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
