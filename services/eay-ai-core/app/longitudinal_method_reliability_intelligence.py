"""Longitudinal method reliability and non-stationarity authority for Jarvis.

Transfer/OOD evidence can show that a selected mechanism generalizes across a
bounded test surface. This layer asks a harder operational intelligence question:
does that method remain reliable as realized outcomes accumulate and the operating
regime changes?

A TRUSTED artifact authorizes only a bounded claim that the method is reliable in
the assessed current regime. It never mints Company Truth, provider authority,
model/policy updates, execution authority, or side effects.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .transfer_generalization_intelligence import (
    TransferDisposition,
    TransferGeneralizationArtifact,
)

LONGITUDINAL_METHOD_RELIABILITY_CONTRACT = "eay-longitudinal-method-reliability-v1"
_SCOPE = r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,239}$"
_DIGEST = r"^[0-9a-f]{64}$"


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class MethodReliabilityState(str, Enum):
    TRUSTED = "trusted"
    LIMITED = "limited"
    DISTRUSTED = "distrusted"


class OutcomeEvaluationOutcome(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class MethodReliabilityPolicy(SealedModel):
    minimum_total_episodes: int = Field(default=6, ge=4, le=128)
    minimum_distinct_regimes: int = Field(default=2, ge=2, le=16)
    minimum_current_regime_episodes: int = Field(default=4, ge=3, le=64)
    minimum_current_negative_controls: int = Field(default=1, ge=1, le=16)
    minimum_independent_evaluators: int = Field(default=2, ge=2, le=8)
    minimum_conservative_score: float = Field(default=0.75, ge=0.0, le=1.0)
    near_threshold_margin: float = Field(default=0.03, ge=0.0, le=0.20)
    minimum_recovery_episodes_after_degradation: int = Field(default=3, ge=2, le=16)

    @model_validator(mode="after")
    def strict_thresholds(self) -> "MethodReliabilityPolicy":
        if self.minimum_conservative_score + self.near_threshold_margin > 1.0:
            raise ValueError("method_reliability_near_threshold_exceeds_one")
        return self


class MethodOutcomeEpisode(SealedModel):
    episode_id: str = Field(pattern=_SCOPE)
    regime_id: str = Field(pattern=_SCOPE)
    description: str = Field(min_length=8)
    expected_method_applicable: bool
    method_applied: bool
    prediction_at: datetime
    observed_at: datetime
    independently_observed: bool
    preserved_constraints: tuple[str, ...] = Field(min_length=1)
    challenged_assumptions: tuple[str, ...] = ()
    outcome_evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def chronology_and_uniqueness(self) -> "MethodOutcomeEpisode":
        if self.prediction_at.tzinfo is None or self.observed_at.tzinfo is None:
            raise ValueError("method_reliability_episode_timestamps_must_be_timezone_aware")
        if self.prediction_at >= self.observed_at:
            raise ValueError("method_reliability_prediction_must_precede_observation")
        for code, values in (
            ("preserved_constraints", self.preserved_constraints),
            ("challenged_assumptions", self.challenged_assumptions),
            ("outcome_evidence_refs", self.outcome_evidence_refs),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"method_reliability_{code}_must_be_unique")
        return self


class IndependentOutcomeEvaluation(SealedModel):
    evaluation_id: str = Field(pattern=_SCOPE)
    episode_id: str = Field(pattern=_SCOPE)
    evaluator_ref: str = Field(pattern=_SCOPE)
    independent_evaluator: bool
    outcome: OutcomeEvaluationOutcome
    boundary_respected: bool
    constraints_satisfied: bool
    outcome_alignment: float = Field(ge=0.0, le=1.0)
    mechanism_reliability: float = Field(ge=0.0, le=1.0)
    regime_robustness: float = Field(ge=0.0, le=1.0)
    calibration: float = Field(ge=0.0, le=1.0)
    evidence_strength: float = Field(ge=0.0, le=1.0)
    unresolved_material_objections: int = Field(ge=0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_evidence(self) -> "IndependentOutcomeEvaluation":
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("method_reliability_evaluation_evidence_refs_must_be_unique")
        return self

    @property
    def composite_score(self) -> float:
        return round(
            (
                self.outcome_alignment
                + self.mechanism_reliability
                + self.regime_robustness
                + self.calibration
                + self.evidence_strength
            )
            / 5.0,
            6,
        )


class MethodEpisodeScore(SealedModel):
    episode_id: str = Field(pattern=_SCOPE)
    regime_id: str = Field(pattern=_SCOPE)
    current_regime: bool
    expected_method_applicable: bool
    method_applied: bool
    conservative_score: float = Field(ge=0.0, le=1.0)
    independent_evaluator_count: int = Field(ge=0)
    clean: bool
    decisive_degradation: bool
    blockers: tuple[str, ...] = ()


class LongitudinalMethodReliabilityArtifact(SealedModel):
    contract: str = LONGITUDINAL_METHOD_RELIABILITY_CONTRACT
    problem_id: str = Field(pattern=_SCOPE)
    tenant_id: str = Field(pattern=_SCOPE)
    company_id: str = Field(pattern=_SCOPE)
    method_id: str = Field(pattern=_SCOPE)
    source_transfer_artifact_fingerprint: str = Field(pattern=_DIGEST)
    current_regime_id: str = Field(pattern=_SCOPE)
    assessment_as_of: datetime
    episode_count: int = Field(ge=0)
    distinct_regime_count: int = Field(ge=0)
    current_regime_episode_count: int = Field(ge=0)
    current_negative_control_count: int = Field(ge=0)
    recovery_clean_episode_count: int = Field(ge=0)
    current_regime_worst_score: float = Field(ge=0.0, le=1.0)
    episode_scores: tuple[MethodEpisodeScore, ...]
    state: MethodReliabilityState
    blockers: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    bounded_current_regime_reliability_claim_allowed: bool
    universal_reliability_claim_allowed: bool = False
    company_truth_promoted: bool = False
    provider_authority_granted: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False
    fingerprint: str = Field(pattern=_DIGEST)

    @model_validator(mode="after")
    def integral_and_non_authoritative(self) -> "LongitudinalMethodReliabilityArtifact":
        if self.assessment_as_of.tzinfo is None:
            raise ValueError("method_reliability_assessment_as_of_must_be_timezone_aware")
        if any(
            (
                self.universal_reliability_claim_allowed,
                self.company_truth_promoted,
                self.provider_authority_granted,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("method_reliability_never_mints_authority_or_universal_claim")
        if self.state is MethodReliabilityState.TRUSTED:
            if self.blockers or not self.bounded_current_regime_reliability_claim_allowed:
                raise ValueError("method_reliability_trusted_requires_bounded_claim_without_blockers")
        elif self.bounded_current_regime_reliability_claim_allowed:
            raise ValueError("method_reliability_non_trusted_cannot_allow_bounded_claim")
        if self.fingerprint != _seal(_payload(self)):
            raise ValueError("method_reliability_fingerprint_mismatch")
        return self


def _seal(value: object) -> str:
    canonical = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _payload(item: BaseModel) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={"fingerprint"})


def _validate_source(
    *,
    source: TransferGeneralizationArtifact,
    tenant_id: str,
    company_id: str,
    problem_id: str,
    method_id: str,
) -> TransferGeneralizationArtifact:
    source = TransferGeneralizationArtifact.model_validate(source.model_dump(mode="json"))
    if source.tenant_id != tenant_id:
        raise ValueError("method_reliability_cross_tenant_source_forbidden")
    if source.company_id != company_id:
        raise ValueError("method_reliability_cross_company_source_forbidden")
    if source.problem_id != problem_id:
        raise ValueError("method_reliability_problem_scope_mismatch")
    if source.disposition is not TransferDisposition.READY:
        raise ValueError("method_reliability_requires_ready_transfer_source")
    if source.selected_solution_id != method_id:
        raise ValueError("method_reliability_method_scope_mismatch")
    return source


def evaluate_longitudinal_method_reliability(
    *,
    source: TransferGeneralizationArtifact,
    tenant_id: str,
    company_id: str,
    problem_id: str,
    method_id: str,
    current_regime_id: str,
    assessment_as_of: datetime,
    episodes: tuple[MethodOutcomeEpisode, ...],
    evaluations: tuple[IndependentOutcomeEvaluation, ...],
    policy: MethodReliabilityPolicy | None = None,
) -> LongitudinalMethodReliabilityArtifact:
    """Qualify current-regime method trust from realized outcomes without authority escalation."""

    if assessment_as_of.tzinfo is None:
        raise ValueError("method_reliability_assessment_as_of_must_be_timezone_aware")
    source = _validate_source(
        source=source,
        tenant_id=tenant_id,
        company_id=company_id,
        problem_id=problem_id,
        method_id=method_id,
    )
    rules = policy or MethodReliabilityPolicy()
    episodes = tuple(MethodOutcomeEpisode.model_validate(item.model_dump(mode="json")) for item in episodes)
    evaluations = tuple(
        IndependentOutcomeEvaluation.model_validate(item.model_dump(mode="json"))
        for item in evaluations
    )

    episode_ids = [item.episode_id for item in episodes]
    evaluation_ids = [item.evaluation_id for item in evaluations]
    if len(episode_ids) != len(set(episode_ids)):
        raise ValueError("method_reliability_episode_ids_must_be_unique")
    if len(evaluation_ids) != len(set(evaluation_ids)):
        raise ValueError("method_reliability_evaluation_ids_must_be_unique")
    known_episodes = set(episode_ids)
    if any(item.episode_id not in known_episodes for item in evaluations):
        raise ValueError("method_reliability_evaluation_references_unknown_episode")
    if any(item.observed_at > assessment_as_of for item in episodes):
        raise ValueError("method_reliability_future_outcome_evidence_forbidden")

    ordered = tuple(sorted(episodes, key=lambda item: (item.observed_at, item.episode_id)))
    source_evidence = set(source.evidence_refs)
    all_evidence: set[str] = set()
    scores: list[MethodEpisodeScore] = []

    for episode in ordered:
        all_evidence.update(episode.outcome_evidence_refs)
        blockers: list[str] = []
        decisive = False

        if not episode.independently_observed:
            blockers.append("method_reliability_independent_outcome_observation_required")

        if not any(ref not in source_evidence for ref in episode.outcome_evidence_refs):
            blockers.append("method_reliability_fresh_realized_outcome_evidence_required")

        items = [item for item in evaluations if item.episode_id == episode.episode_id]
        independent = [item for item in items if item.independent_evaluator]
        evaluator_refs = {item.evaluator_ref for item in independent}
        if len(evaluator_refs) < rules.minimum_independent_evaluators:
            blockers.append("method_reliability_independent_evaluator_quorum_missing")

        fresh_evaluation_evidence = False
        for item in independent:
            all_evidence.update(item.evidence_refs)
            if any(ref not in source_evidence for ref in item.evidence_refs):
                fresh_evaluation_evidence = True
            if item.outcome is OutcomeEvaluationOutcome.FAILED:
                blockers.append("method_reliability_realized_outcome_failed")
                decisive = True
            elif item.outcome is OutcomeEvaluationOutcome.INCONCLUSIVE:
                blockers.append("method_reliability_realized_outcome_inconclusive")
                decisive = True
            if not item.boundary_respected:
                blockers.append("method_reliability_decision_boundary_violated")
                decisive = True
            if not item.constraints_satisfied:
                blockers.append("method_reliability_constraint_integrity_failed")
                decisive = True
            if item.unresolved_material_objections:
                blockers.append("method_reliability_material_objection_unresolved")
                decisive = True

        if independent and not fresh_evaluation_evidence:
            blockers.append("method_reliability_fresh_evaluation_evidence_required")

        conservative = min((item.composite_score for item in independent), default=0.0)
        if conservative < rules.minimum_conservative_score:
            blockers.append("method_reliability_conservative_score_below_floor")
            decisive = True
        elif conservative < rules.minimum_conservative_score + rules.near_threshold_margin:
            blockers.append("method_reliability_near_threshold_requires_limited_state")

        if episode.expected_method_applicable and not episode.method_applied:
            blockers.append("method_reliability_applicable_episode_not_exercised")
        if not episode.expected_method_applicable and episode.method_applied:
            blockers.append("method_reliability_negative_control_overgeneralization")
            decisive = True

        unique_blockers = tuple(dict.fromkeys(blockers))
        scores.append(
            MethodEpisodeScore(
                episode_id=episode.episode_id,
                regime_id=episode.regime_id,
                current_regime=episode.regime_id == current_regime_id,
                expected_method_applicable=episode.expected_method_applicable,
                method_applied=episode.method_applied,
                conservative_score=conservative,
                independent_evaluator_count=len(evaluator_refs),
                clean=not unique_blockers,
                decisive_degradation=decisive,
                blockers=unique_blockers,
            )
        )

    structural_blockers: list[str] = []
    regimes = {item.regime_id for item in ordered}
    current_scores = [item for item in scores if item.current_regime]
    current_episodes = [item for item in ordered if item.regime_id == current_regime_id]
    current_negative_controls = [
        item for item in current_episodes if not item.expected_method_applicable
    ]

    if len(ordered) < rules.minimum_total_episodes:
        structural_blockers.append("method_reliability_total_episode_quorum_missing")
    if len(regimes) < rules.minimum_distinct_regimes:
        structural_blockers.append("method_reliability_distinct_regime_quorum_missing")
    if len(current_episodes) < rules.minimum_current_regime_episodes:
        structural_blockers.append("method_reliability_current_regime_episode_quorum_missing")
    if len(current_negative_controls) < rules.minimum_current_negative_controls:
        structural_blockers.append("method_reliability_current_negative_control_quorum_missing")
    if not current_scores:
        structural_blockers.append("method_reliability_current_regime_evidence_missing")

    for score in scores:
        if score.current_regime:
            continue
        non_decisive_blockers = tuple(
            blocker
            for blocker in score.blockers
            if blocker
            not in {
                "method_reliability_realized_outcome_failed",
                "method_reliability_realized_outcome_inconclusive",
                "method_reliability_decision_boundary_violated",
                "method_reliability_constraint_integrity_failed",
                "method_reliability_material_objection_unresolved",
                "method_reliability_conservative_score_below_floor",
                "method_reliability_negative_control_overgeneralization",
            }
        )
        if non_decisive_blockers:
            structural_blockers.append("method_reliability_historical_evidence_not_fully_qualified")
            break

    current_order = [score for score in scores if score.current_regime]
    last_degradation_index = max(
        (index for index, score in enumerate(current_order) if score.decisive_degradation),
        default=None,
    )
    recovery_clean_count = 0
    unresolved_degradation = False
    if last_degradation_index is not None:
        recovery_tail = current_order[last_degradation_index + 1 :]
        for score in recovery_tail:
            if score.clean and score.expected_method_applicable and score.method_applied:
                recovery_clean_count += 1
            elif score.decisive_degradation:
                recovery_clean_count = 0
        unresolved_degradation = (
            recovery_clean_count < rules.minimum_recovery_episodes_after_degradation
        )
        if unresolved_degradation:
            structural_blockers.append("method_reliability_recovery_hysteresis_not_satisfied")

    latest_recovery_start = (
        last_degradation_index + 1 if last_degradation_index is not None else 0
    )
    qualification_tail = current_order[latest_recovery_start:]
    current_non_decisive_blockers = [
        blocker
        for score in qualification_tail
        for blocker in score.blockers
        if not score.decisive_degradation
    ]
    if current_non_decisive_blockers:
        structural_blockers.append("method_reliability_current_regime_not_fully_qualified")

    current_worst = min(
        (item.conservative_score for item in qualification_tail),
        default=0.0,
    )

    blockers = tuple(dict.fromkeys(structural_blockers))
    if unresolved_degradation:
        state = MethodReliabilityState.DISTRUSTED
    elif blockers:
        state = MethodReliabilityState.LIMITED
    else:
        state = MethodReliabilityState.TRUSTED

    values = {
        "contract": LONGITUDINAL_METHOD_RELIABILITY_CONTRACT,
        "problem_id": problem_id,
        "tenant_id": tenant_id,
        "company_id": company_id,
        "method_id": method_id,
        "source_transfer_artifact_fingerprint": source.fingerprint,
        "current_regime_id": current_regime_id,
        "assessment_as_of": assessment_as_of,
        "episode_count": len(ordered),
        "distinct_regime_count": len(regimes),
        "current_regime_episode_count": len(current_episodes),
        "current_negative_control_count": len(current_negative_controls),
        "recovery_clean_episode_count": recovery_clean_count,
        "current_regime_worst_score": current_worst,
        "episode_scores": tuple(scores),
        "state": state,
        "blockers": blockers,
        "evidence_refs": tuple(sorted(all_evidence)),
        "bounded_current_regime_reliability_claim_allowed": state is MethodReliabilityState.TRUSTED,
        "universal_reliability_claim_allowed": False,
        "company_truth_promoted": False,
        "provider_authority_granted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "execution_authority_granted": False,
        "side_effect_authority_granted": False,
    }
    draft = LongitudinalMethodReliabilityArtifact.model_construct(
        **values,
        fingerprint="0" * 64,
    )
    return LongitudinalMethodReliabilityArtifact(
        **values,
        fingerprint=_seal(_payload(draft)),
    )
