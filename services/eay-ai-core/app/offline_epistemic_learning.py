"""Offline strategy learning for Jarvis epistemic control.

The learner may propose a sealed strategy profile from historical, tenant-bound
research outcomes. It never mutates production policy, grants research/tool
authority, or bypasses the existing benchmark-promotion contract.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .adaptive_epistemic_control import EpistemicStrategy
from .benchmark_promotion import VerifiedEngineBenchmarkPromotion

OFFLINE_EPISTEMIC_LEARNING_CONTRACT = "eay-offline-epistemic-learning-v1"
EPISTEMIC_PROMOTION_BINDING_CONTRACT = "eay-epistemic-promotion-binding-v1"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class LearningDisposition(str, Enum):
    CANDIDATE = "candidate"
    HOLD = "hold"


class EpistemicLearningPolicy(BaseModel):
    minimum_samples_per_strategy: int = Field(default=6, ge=3, le=1000)
    minimum_strategy_diversity: int = Field(default=3, ge=2, le=8)
    minimum_problem_evidence_count: int = Field(default=18, ge=6, le=10000)
    minimum_source_families_per_strategy: int = Field(default=2, ge=1, le=100)
    minimum_quality_improvement: float = Field(default=0.03, ge=0.0, le=0.25)
    maximum_mean_brier_score: float = Field(default=0.30, ge=0.0, le=1.0)
    require_perfect_grounding_integrity: bool = True
    require_perfect_authority_integrity: bool = True


class EpistemicLearningEpisode(BaseModel):
    contract: str = OFFLINE_EPISTEMIC_LEARNING_CONTRACT
    episode_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    strategy: EpistemicStrategy
    completed_at: datetime
    correctness: float = Field(ge=0.0, le=1.0)
    brier_score: float = Field(ge=0.0, le=1.0)
    falsification_success: float = Field(ge=0.0, le=1.0)
    contradiction_resolution: float = Field(ge=0.0, le=1.0)
    information_gain_per_probe: float = Field(ge=0.0, le=1.0)
    cost_efficiency: float = Field(ge=0.0, le=1.0)
    latency_efficiency: float = Field(ge=0.0, le=1.0)
    grounding_integrity: bool
    authority_integrity: bool
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    source_family_refs: tuple[str, ...] = Field(min_length=1)
    episode_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sealed_and_time_aware(self) -> "EpistemicLearningEpisode":
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("epistemic_learning_episode_requires_timezone")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("epistemic_learning_evidence_refs_must_be_unique")
        if len(self.source_family_refs) != len(set(self.source_family_refs)):
            raise ValueError("epistemic_learning_source_families_must_be_unique")
        if self.episode_fingerprint != _fingerprint(_episode_payload(self)):
            raise ValueError("epistemic_learning_episode_fingerprint_mismatch")
        return self


class StrategyQuality(BaseModel):
    strategy: EpistemicStrategy
    sample_count: int = Field(ge=1)
    independent_source_family_count: int = Field(ge=1)
    mean_correctness: float = Field(ge=0.0, le=1.0)
    mean_brier_score: float = Field(ge=0.0, le=1.0)
    mean_falsification_success: float = Field(ge=0.0, le=1.0)
    mean_contradiction_resolution: float = Field(ge=0.0, le=1.0)
    mean_information_gain_per_probe: float = Field(ge=0.0, le=1.0)
    mean_cost_efficiency: float = Field(ge=0.0, le=1.0)
    mean_latency_efficiency: float = Field(ge=0.0, le=1.0)
    grounding_integrity_rate: float = Field(ge=0.0, le=1.0)
    authority_integrity_rate: float = Field(ge=0.0, le=1.0)
    quality_score: float = Field(ge=0.0, le=1.0)


class EpistemicStrategyCandidate(BaseModel):
    contract: str = OFFLINE_EPISTEMIC_LEARNING_CONTRACT
    tenant_id: str
    company_id: str
    problem_class: str
    baseline_strategy: EpistemicStrategy
    recommended_strategy_order: tuple[EpistemicStrategy, ...]
    strategy_qualities: tuple[StrategyQuality, ...]
    sample_count: int = Field(ge=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    source_family_count: int = Field(ge=1)
    baseline_quality_score: float = Field(ge=0.0, le=1.0)
    challenger_quality_score: float = Field(ge=0.0, le=1.0)
    measured_improvement: float = Field(ge=-1.0, le=1.0)
    disposition: LearningDisposition
    candidate_system_id: str = Field(min_length=1)
    candidate_version: str = Field(min_length=1)
    blockers: tuple[str, ...] = ()
    automatic_policy_update_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_research_execution_allowed: bool = False
    direct_provider_call_allowed: bool = False
    execution_authority_granted: bool = False
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def sealed_and_non_authoritative(self) -> "EpistemicStrategyCandidate":
        if (
            self.automatic_policy_update_allowed
            or self.automatic_model_weight_update_allowed
            or self.automatic_research_execution_allowed
            or self.direct_provider_call_allowed
            or self.execution_authority_granted
        ):
            raise ValueError("epistemic_learning_candidate_never_self_activates")
        if self.disposition is LearningDisposition.CANDIDATE and self.blockers:
            raise ValueError("epistemic_learning_candidate_cannot_ignore_blockers")
        if self.candidate_fingerprint != _fingerprint(_candidate_payload(self)):
            raise ValueError("epistemic_learning_candidate_fingerprint_mismatch")
        return self


class EpistemicPromotionBinding(BaseModel):
    contract: str = EPISTEMIC_PROMOTION_BINDING_CONTRACT
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    candidate_system_id: str = Field(min_length=1)
    candidate_version: str = Field(min_length=1)
    benchmark_verification_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    benchmark_evidence_ref: str = Field(pattern=r"^benchmark://[0-9a-f]{64}$")
    benchmark_promotion_allowed: bool
    canary_required: bool = True
    automatic_activation_allowed: bool = False
    execution_authority_granted: bool = False
    blockers: tuple[str, ...] = ()
    binding_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def promotion_does_not_self_activate(self) -> "EpistemicPromotionBinding":
        if self.automatic_activation_allowed or self.execution_authority_granted:
            raise ValueError("epistemic_promotion_binding_never_self_activates")
        if self.benchmark_promotion_allowed and self.blockers:
            raise ValueError("epistemic_promotion_binding_cannot_ignore_blockers")
        if self.binding_fingerprint != _fingerprint(_binding_payload(self)):
            raise ValueError("epistemic_promotion_binding_fingerprint_mismatch")
        return self


def seal_learning_episode(
    *,
    episode_id: str,
    tenant_id: str,
    company_id: str,
    problem_class: str,
    strategy: EpistemicStrategy,
    completed_at: datetime,
    correctness: float,
    brier_score: float,
    falsification_success: float,
    contradiction_resolution: float,
    information_gain_per_probe: float,
    cost_efficiency: float,
    latency_efficiency: float,
    grounding_integrity: bool,
    authority_integrity: bool,
    evidence_refs: tuple[str, ...],
    source_family_refs: tuple[str, ...],
) -> EpistemicLearningEpisode:
    values = {
        "contract": OFFLINE_EPISTEMIC_LEARNING_CONTRACT,
        "episode_id": episode_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "problem_class": problem_class,
        "strategy": strategy,
        "completed_at": completed_at,
        "correctness": correctness,
        "brier_score": brier_score,
        "falsification_success": falsification_success,
        "contradiction_resolution": contradiction_resolution,
        "information_gain_per_probe": information_gain_per_probe,
        "cost_efficiency": cost_efficiency,
        "latency_efficiency": latency_efficiency,
        "grounding_integrity": grounding_integrity,
        "authority_integrity": authority_integrity,
        "evidence_refs": evidence_refs,
        "source_family_refs": source_family_refs,
    }
    draft = EpistemicLearningEpisode.model_construct(
        **values,
        episode_fingerprint="0" * 64,
    )
    return EpistemicLearningEpisode(
        **values,
        episode_fingerprint=_fingerprint(_episode_payload(draft)),
    )


def learn_epistemic_strategy_candidate(
    *,
    episodes: tuple[EpistemicLearningEpisode, ...],
    baseline_strategy: EpistemicStrategy,
    candidate_version: str,
    policy: EpistemicLearningPolicy | None = None,
) -> EpistemicStrategyCandidate:
    rules = policy or EpistemicLearningPolicy()
    if not episodes:
        raise ValueError("epistemic_learning_requires_episodes")
    validated = tuple(
        EpistemicLearningEpisode.model_validate(item.model_dump(mode="json"))
        for item in episodes
    )
    tenant_id = validated[0].tenant_id
    company_id = validated[0].company_id
    problem_class = validated[0].problem_class
    if any(item.tenant_id != tenant_id for item in validated):
        raise ValueError("epistemic_learning_cross_tenant_evidence_forbidden")
    if any(item.company_id != company_id for item in validated):
        raise ValueError("epistemic_learning_cross_company_evidence_forbidden")
    if any(item.problem_class != problem_class for item in validated):
        raise ValueError("epistemic_learning_problem_class_mismatch")

    episode_ids = [item.episode_id for item in validated]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("epistemic_learning_duplicate_episode")

    grouped: dict[EpistemicStrategy, list[EpistemicLearningEpisode]] = {}
    for item in validated:
        grouped.setdefault(item.strategy, []).append(item)
    qualities = tuple(
        sorted(
            (_quality(strategy, values) for strategy, values in grouped.items()),
            key=lambda item: (-item.quality_score, item.strategy.value),
        )
    )
    quality_map = {item.strategy: item for item in qualities}
    blockers: list[str] = []
    if len(validated) < rules.minimum_problem_evidence_count:
        blockers.append("epistemic_learning_problem_sample_floor_not_met")
    if len(grouped) < rules.minimum_strategy_diversity:
        blockers.append("epistemic_learning_strategy_diversity_not_met")
    for strategy, values in grouped.items():
        if len(values) < rules.minimum_samples_per_strategy:
            blockers.append(
                f"epistemic_learning_strategy_sample_floor_not_met:{strategy.value}"
            )
        quality = quality_map[strategy]
        if (
            quality.independent_source_family_count
            < rules.minimum_source_families_per_strategy
        ):
            blockers.append(
                "epistemic_learning_source_family_diversity_not_met:"
                f"{strategy.value}"
            )
    if baseline_strategy not in quality_map:
        blockers.append("epistemic_learning_baseline_strategy_missing")
    if rules.require_perfect_grounding_integrity and any(
        not item.grounding_integrity for item in validated
    ):
        blockers.append("epistemic_learning_grounding_integrity_regression")
    if rules.require_perfect_authority_integrity and any(
        not item.authority_integrity for item in validated
    ):
        blockers.append("epistemic_learning_authority_integrity_regression")

    baseline = quality_map.get(baseline_strategy)
    challenger = qualities[0]
    baseline_score = baseline.quality_score if baseline else 0.0
    improvement = round(challenger.quality_score - baseline_score, 6)
    if challenger.mean_brier_score > rules.maximum_mean_brier_score:
        blockers.append("epistemic_learning_calibration_floor_not_met")
    if challenger.strategy is baseline_strategy:
        blockers.append("epistemic_learning_no_strategy_change")
    if improvement < rules.minimum_quality_improvement:
        blockers.append("epistemic_learning_improvement_below_floor")

    evidence_refs = tuple(
        sorted({ref for item in validated for ref in item.evidence_refs})
    )
    if len(evidence_refs) < rules.minimum_problem_evidence_count:
        blockers.append("epistemic_learning_evidence_diversity_not_met")
    source_families = {
        ref for item in validated for ref in item.source_family_refs
    }
    disposition = (
        LearningDisposition.CANDIDATE
        if not blockers
        else LearningDisposition.HOLD
    )
    system_id = f"jarvis-epistemic-profile:{problem_class}:{challenger.strategy.value}"
    payload = {
        "contract": OFFLINE_EPISTEMIC_LEARNING_CONTRACT,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "problem_class": problem_class,
        "baseline_strategy": baseline_strategy,
        "recommended_strategy_order": tuple(item.strategy for item in qualities),
        "strategy_qualities": qualities,
        "sample_count": len(validated),
        "evidence_refs": evidence_refs,
        "source_family_count": len(source_families),
        "baseline_quality_score": baseline_score,
        "challenger_quality_score": challenger.quality_score,
        "measured_improvement": improvement,
        "disposition": disposition,
        "candidate_system_id": system_id,
        "candidate_version": candidate_version,
        "blockers": tuple(dict.fromkeys(blockers)),
        "automatic_policy_update_allowed": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_research_execution_allowed": False,
        "direct_provider_call_allowed": False,
        "execution_authority_granted": False,
    }
    draft = EpistemicStrategyCandidate.model_construct(
        **payload,
        candidate_fingerprint="0" * 64,
    )
    return EpistemicStrategyCandidate(
        **payload,
        candidate_fingerprint=_fingerprint(_candidate_payload(draft)),
    )


def bind_candidate_to_verified_benchmark(
    *,
    candidate: EpistemicStrategyCandidate,
    promotion: VerifiedEngineBenchmarkPromotion,
) -> EpistemicPromotionBinding:
    candidate = EpistemicStrategyCandidate.model_validate(
        candidate.model_dump(mode="json")
    )
    promotion = VerifiedEngineBenchmarkPromotion.model_validate(
        promotion.model_dump(mode="json")
    )
    blockers: list[str] = []
    if candidate.disposition is not LearningDisposition.CANDIDATE:
        blockers.append("epistemic_promotion_candidate_not_eligible")
    if promotion.attestation.engine_id != candidate.candidate_system_id:
        blockers.append("epistemic_promotion_candidate_system_mismatch")
    if promotion.attestation.system_version != candidate.candidate_version:
        blockers.append("epistemic_promotion_candidate_version_mismatch")
    if not promotion.attestation.promotion_allowed:
        blockers.append("epistemic_promotion_benchmark_not_approved")
    if promotion.attestation.critical_safety_regression:
        blockers.append("epistemic_promotion_critical_safety_regression")

    benchmark_allowed = not blockers
    payload = {
        "contract": EPISTEMIC_PROMOTION_BINDING_CONTRACT,
        "candidate_fingerprint": candidate.candidate_fingerprint,
        "candidate_system_id": candidate.candidate_system_id,
        "candidate_version": candidate.candidate_version,
        "benchmark_verification_fingerprint": promotion.verification_fingerprint,
        "benchmark_evidence_ref": promotion.attestation.evidence_ref,
        "benchmark_promotion_allowed": benchmark_allowed,
        "canary_required": True,
        "automatic_activation_allowed": False,
        "execution_authority_granted": False,
        "blockers": tuple(blockers),
    }
    draft = EpistemicPromotionBinding.model_construct(
        **payload,
        binding_fingerprint="0" * 64,
    )
    return EpistemicPromotionBinding(
        **payload,
        binding_fingerprint=_fingerprint(_binding_payload(draft)),
    )


def _quality(
    strategy: EpistemicStrategy,
    episodes: list[EpistemicLearningEpisode],
) -> StrategyQuality:
    count = len(episodes)

    def mean(field: str) -> float:
        return sum(float(getattr(item, field)) for item in episodes) / count

    correctness = mean("correctness")
    brier = mean("brier_score")
    falsification = mean("falsification_success")
    contradiction = mean("contradiction_resolution")
    information_gain = mean("information_gain_per_probe")
    cost = mean("cost_efficiency")
    latency = mean("latency_efficiency")
    grounding = sum(item.grounding_integrity for item in episodes) / count
    authority = sum(item.authority_integrity for item in episodes) / count
    score = (
        0.24 * correctness
        + 0.16 * (1.0 - brier)
        + 0.15 * falsification
        + 0.10 * contradiction
        + 0.12 * information_gain
        + 0.08 * cost
        + 0.05 * latency
        + 0.05 * grounding
        + 0.05 * authority
    )
    source_families = {
        ref for item in episodes for ref in item.source_family_refs
    }
    return StrategyQuality(
        strategy=strategy,
        sample_count=count,
        independent_source_family_count=len(source_families),
        mean_correctness=round(correctness, 6),
        mean_brier_score=round(brier, 6),
        mean_falsification_success=round(falsification, 6),
        mean_contradiction_resolution=round(contradiction, 6),
        mean_information_gain_per_probe=round(information_gain, 6),
        mean_cost_efficiency=round(cost, 6),
        mean_latency_efficiency=round(latency, 6),
        grounding_integrity_rate=round(grounding, 6),
        authority_integrity_rate=round(authority, 6),
        quality_score=round(score, 6),
    )


def _episode_payload(item: EpistemicLearningEpisode) -> dict[str, object]:
    return item.model_dump(
        mode="json",
        exclude={"episode_fingerprint"},
    )


def _candidate_payload(item: EpistemicStrategyCandidate) -> dict[str, object]:
    return item.model_dump(
        mode="json",
        exclude={"candidate_fingerprint"},
    )


def _binding_payload(item: EpistemicPromotionBinding) -> dict[str, object]:
    return item.model_dump(
        mode="json",
        exclude={"binding_fingerprint"},
    )
