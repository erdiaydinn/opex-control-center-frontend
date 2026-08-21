"""Adaptive epistemic control for Jarvis investigations and live-world sensing.

The existing research engine deliberately plans bounded evidence missions, while
Autonomous Investigator evaluates competing hypotheses and Continuous World
Understanding decides whether prior beliefs remain reusable. This module closes
the missing sequential-control gap between those contracts.

It never browses, invokes a model/provider, mutates production policy, promotes
Company World truth, or grants business execution authority. It chooses the
next *read-only* epistemic move from existing evidence state: pursue the probe
with the highest expected uncertainty reduction, switch strategy when research
stalls, expand the hypothesis space for unresolved novel problems, and rank the
next live-world source to refresh by value, volatility, staleness and conflict
risk. Grounded calibration can make the controller demand more evidence after
past mistakes, but cannot self-activate weights or policy.
"""

from __future__ import annotations

import hashlib
import json
import math
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .autonomous_investigator import (
    AutonomousInvestigationReport,
    InvestigatorCalibrationProfile,
    InvestigatorDisposition,
    InvestigatorProblem,
    ProblemNovelty,
)
from .continuous_world_understanding import (
    ContinuousWorldAssessment,
    SourceFreshnessExpectation,
)
from .research_engine import ResearchRole

ADAPTIVE_EPISTEMIC_CONTROL_CONTRACT = "eay-adaptive-epistemic-control-v1"


class EpistemicStrategy(str, Enum):
    PRIMARY_TRIANGULATION = "primary_triangulation"
    INDEPENDENT_CORROBORATION = "independent_corroboration"
    CONTRADICTION_FIRST = "contradiction_first"
    FALSIFICATION = "falsification"
    TEMPORAL_REFRESH = "temporal_refresh"
    CROSS_DOMAIN_EXPANSION = "cross_domain_expansion"
    QUANTITATIVE_VALIDATION = "quantitative_validation"
    ALTERNATIVE_HYPOTHESIS = "alternative_hypothesis"


class EpistemicMoveKind(str, Enum):
    PROBE = "probe"
    SWITCH_STRATEGY = "switch_strategy"
    EXPAND_HYPOTHESIS_SPACE = "expand_hypothesis_space"
    STOP_EVIDENCE_SUFFICIENT = "stop_evidence_sufficient"
    HOLD_LIMIT_REACHED = "hold_limit_reached"


class AdaptiveEpistemicPolicy(BaseModel):
    maximum_rounds: int = Field(default=8, ge=1, le=32)
    minimum_expected_information_gain: float = Field(default=0.18, ge=0.0, le=1.0)
    target_effective_confidence: float = Field(default=0.78, ge=0.50, le=0.99)
    minimum_decisive_margin: float = Field(default=0.15, ge=0.0, le=1.0)
    minimum_confidence_delta: float = Field(default=0.025, ge=0.0, le=0.25)
    stall_rounds_before_switch: int = Field(default=2, ge=1, le=8)
    stall_rounds_before_hypothesis_expansion: int = Field(default=3, ge=2, le=12)
    repeated_probe_penalty: float = Field(default=0.22, ge=0.0, le=0.80)

    @model_validator(mode="after")
    def strategy_switch_precedes_expansion(self) -> "AdaptiveEpistemicPolicy":
        if self.stall_rounds_before_hypothesis_expansion <= self.stall_rounds_before_switch:
            raise ValueError("epistemic_hypothesis_expansion_must_follow_strategy_switch")
        return self


class EpistemicRoundObservation(BaseModel):
    round_index: int = Field(ge=0)
    report_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    leading_hypothesis_id: str | None = None
    leading_confidence: float = Field(ge=0.0, le=1.0)
    leading_margin: float | None = Field(default=None, ge=-1.0, le=1.0)
    evidence_ref_count: int = Field(ge=0)
    unresolved_task_count: int = Field(ge=0)
    selected_probe_id: str | None = None
    selected_strategy: EpistemicStrategy | None = None


class EpistemicProbe(BaseModel):
    probe_id: str = Field(min_length=1)
    hypothesis_id: str | None = None
    task_ref: str = Field(min_length=1)
    role: ResearchRole
    strategy: EpistemicStrategy
    query_intent: str = Field(min_length=8)
    expected_information_gain: float = Field(ge=0.0, le=1.0)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    read_only: bool = True
    automatic_execution_allowed: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def probe_is_planning_only(self) -> "EpistemicProbe":
        if not self.read_only:
            raise ValueError("epistemic_probe_must_be_read_only")
        if self.automatic_execution_allowed or self.execution_authority_granted:
            raise ValueError("epistemic_probe_never_grants_execution")
        return self


class AdaptiveEpistemicDirective(BaseModel):
    contract: str = ADAPTIVE_EPISTEMIC_CONTROL_CONTRACT
    problem_id: str
    tenant_id: str
    company_id: str
    round_index: int = Field(ge=0)
    move_kind: EpistemicMoveKind
    uncertainty: float = Field(ge=0.0, le=1.0)
    raw_leading_confidence: float = Field(ge=0.0, le=1.0)
    effective_leading_confidence: float = Field(ge=0.0, le=1.0)
    calibration_multiplier: float = Field(ge=0.25, le=1.0)
    stall_count: int = Field(ge=0)
    selected_probe: EpistemicProbe | None = None
    candidate_probes: tuple[EpistemicProbe, ...] = ()
    reason_codes: tuple[str, ...] = Field(min_length=1)
    blockers: tuple[str, ...] = ()
    firm_company_claim_authorized: bool = False
    production_truth_promoted: bool = False
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    automatic_research_execution_allowed: bool = False
    execution_authority_granted: bool = False
    direct_provider_call_allowed: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def directive_is_integral_and_non_authoritative(self) -> "AdaptiveEpistemicDirective":
        if any(
            (
                self.firm_company_claim_authorized,
                self.production_truth_promoted,
                self.automatic_model_weight_update_allowed,
                self.automatic_policy_update_allowed,
                self.automatic_research_execution_allowed,
                self.execution_authority_granted,
                self.direct_provider_call_allowed,
            )
        ):
            raise ValueError("adaptive_epistemic_control_never_grants_authority")
        if self.move_kind in {
            EpistemicMoveKind.PROBE,
            EpistemicMoveKind.SWITCH_STRATEGY,
        } and self.selected_probe is None:
            raise ValueError("epistemic_probe_move_requires_selected_probe")
        if self.move_kind in {
            EpistemicMoveKind.STOP_EVIDENCE_SUFFICIENT,
            EpistemicMoveKind.HOLD_LIMIT_REACHED,
            EpistemicMoveKind.EXPAND_HYPOTHESIS_SPACE,
        } and self.selected_probe is not None:
            raise ValueError("epistemic_non_probe_move_cannot_select_probe")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("adaptive_epistemic_control_fingerprint_mismatch")
        return self


class WorldSourceValueSignal(BaseModel):
    source_key: str = Field(min_length=1)
    business_importance: float = Field(default=0.50, ge=0.0, le=1.0)
    volatility: float = Field(default=0.50, ge=0.0, le=1.0)
    contradiction_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    information_gain_hint: float = Field(default=0.50, ge=0.0, le=1.0)


class WorldRefreshPriority(BaseModel):
    source_key: str
    priority_score: float = Field(ge=0.0, le=1.0)
    freshness_pressure: float = Field(ge=0.0, le=1.0)
    expected_information_gain: float = Field(ge=0.0, le=1.0)
    reason_codes: tuple[str, ...] = Field(min_length=1)
    evidence_ref: str | None = None
    read_only: bool = True
    automatic_refresh_allowed: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def refresh_priority_is_advisory(self) -> "WorldRefreshPriority":
        if not self.read_only:
            raise ValueError("world_refresh_priority_must_be_read_only")
        if self.automatic_refresh_allowed or self.execution_authority_granted:
            raise ValueError("world_refresh_priority_never_grants_execution")
        return self


class EpistemicBenchmarkScore(BaseModel):
    general_reasoning: float = Field(ge=0.0, le=1.0)
    deep_research: float = Field(ge=0.0, le=1.0)
    live_world_understanding: float = Field(ge=0.0, le=1.0)
    systematic_self_correction: float = Field(ge=0.0, le=1.0)
    novel_problem_solving: float = Field(ge=0.0, le=1.0)
    grounding_integrity: float = Field(ge=0.0, le=1.0)
    authority_integrity: float = Field(ge=0.0, le=1.0)
    overall: float = Field(ge=0.0, le=1.0)
    benchmark_complete: bool


def observe_epistemic_round(
    *,
    report: AutonomousInvestigationReport,
    round_index: int,
    selected_probe: EpistemicProbe | None = None,
) -> EpistemicRoundObservation:
    confidence = 0.0
    margin: float | None = None
    leader_id: str | None = None
    if report.ranking is not None:
        leader_id = report.ranking.leading_hypothesis_id
        margin = report.ranking.leading_margin
        if leader_id is not None:
            leader = next(
                (
                    item
                    for item in report.ranking.assessments
                    if item.hypothesis_id == leader_id
                ),
                None,
            )
            if leader is not None:
                confidence = leader.confidence
    evidence_refs = {
        ref
        for state in report.research_states
        for ref in state.assessment.evidence_refs
    }
    return EpistemicRoundObservation(
        round_index=round_index,
        report_fingerprint=report.fingerprint,
        leading_hypothesis_id=leader_id,
        leading_confidence=confidence,
        leading_margin=margin,
        evidence_ref_count=len(evidence_refs),
        unresolved_task_count=len(report.next_research_tasks),
        selected_probe_id=(selected_probe.probe_id if selected_probe else None),
        selected_strategy=(selected_probe.strategy if selected_probe else None),
    )


def plan_adaptive_epistemic_round(
    *,
    problem: InvestigatorProblem,
    report: AutonomousInvestigationReport,
    round_index: int,
    history: tuple[EpistemicRoundObservation, ...] = (),
    calibration: InvestigatorCalibrationProfile | None = None,
    policy: AdaptiveEpistemicPolicy | None = None,
) -> AdaptiveEpistemicDirective:
    """Choose the next evidence-seeking move from the current investigation state."""

    rules = policy or AdaptiveEpistemicPolicy()
    _validate_problem_report_scope(problem=problem, report=report)
    if round_index < 0:
        raise ValueError("epistemic_round_index_negative")
    if history:
        if tuple(item.round_index for item in history) != tuple(
            sorted(item.round_index for item in history)
        ):
            raise ValueError("epistemic_history_round_order_invalid")
        if history[-1].round_index >= round_index:
            raise ValueError("epistemic_history_must_precede_current_round")

    multiplier = 1.0
    if calibration is not None:
        if calibration.tenant_id != problem.tenant_id:
            raise ValueError("epistemic_calibration_tenant_mismatch")
        if calibration.company_id != problem.company_id:
            raise ValueError("epistemic_calibration_company_mismatch")
        multiplier = min(1.0, calibration.suggested_confidence_multiplier)

    observation = observe_epistemic_round(report=report, round_index=round_index)
    raw_confidence = observation.leading_confidence
    effective_confidence = round(raw_confidence * multiplier, 6)
    uncertainty = _ranking_uncertainty(report)
    stall_count = _consecutive_stall_count(
        history=history,
        current=observation,
        minimum_confidence_delta=rules.minimum_confidence_delta,
    )

    margin = observation.leading_margin or 0.0
    evidence_sufficient = (
        report.disposition is InvestigatorDisposition.DECISION_READY
        and report.ranking is not None
        and report.ranking.decisive
        and effective_confidence >= rules.target_effective_confidence
        and margin >= rules.minimum_decisive_margin
    )
    if evidence_sufficient:
        return _directive(
            problem=problem,
            round_index=round_index,
            move_kind=EpistemicMoveKind.STOP_EVIDENCE_SUFFICIENT,
            uncertainty=uncertainty,
            raw_confidence=raw_confidence,
            effective_confidence=effective_confidence,
            multiplier=multiplier,
            stall_count=stall_count,
            reason_codes=("epistemic_evidence_sufficiency_reached",),
            blockers=(),
        )

    if round_index >= rules.maximum_rounds:
        return _directive(
            problem=problem,
            round_index=round_index,
            move_kind=EpistemicMoveKind.HOLD_LIMIT_REACHED,
            uncertainty=uncertainty,
            raw_confidence=raw_confidence,
            effective_confidence=effective_confidence,
            multiplier=multiplier,
            stall_count=stall_count,
            reason_codes=("epistemic_round_budget_exhausted",),
            blockers=("epistemic_unresolved_after_bounded_research",),
        )

    if (
        problem.novelty is ProblemNovelty.NOVEL
        and stall_count >= rules.stall_rounds_before_hypothesis_expansion
    ):
        return _directive(
            problem=problem,
            round_index=round_index,
            move_kind=EpistemicMoveKind.EXPAND_HYPOTHESIS_SPACE,
            uncertainty=uncertainty,
            raw_confidence=raw_confidence,
            effective_confidence=effective_confidence,
            multiplier=multiplier,
            stall_count=stall_count,
            reason_codes=(
                "epistemic_repeated_stall_detected",
                "epistemic_novel_problem_requires_alternative_hypothesis",
            ),
            blockers=("epistemic_current_hypothesis_space_not_resolving_uncertainty",),
        )

    candidates = _candidate_probes(
        problem=problem,
        report=report,
        history=history,
        uncertainty=uncertainty,
        repeated_probe_penalty=rules.repeated_probe_penalty,
        calibration_multiplier=multiplier,
    )
    if not candidates:
        candidates = (
            _calibration_or_gap_probe(
                problem=problem,
                report=report,
                uncertainty=uncertainty,
                calibration_multiplier=multiplier,
            ),
        )

    selected = candidates[0]
    switch_required = stall_count >= rules.stall_rounds_before_switch
    low_gain = selected.expected_information_gain < rules.minimum_expected_information_gain
    if switch_required or low_gain:
        switched = _select_diverse_probe(candidates=candidates, history=history)
        selected = switched or selected
        return _directive(
            problem=problem,
            round_index=round_index,
            move_kind=EpistemicMoveKind.SWITCH_STRATEGY,
            uncertainty=uncertainty,
            raw_confidence=raw_confidence,
            effective_confidence=effective_confidence,
            multiplier=multiplier,
            stall_count=stall_count,
            selected_probe=selected,
            candidates=candidates,
            reason_codes=tuple(
                dict.fromkeys(
                    (
                        "epistemic_strategy_switch_required",
                        *("epistemic_information_gain_below_floor",) if low_gain else (),
                        *("epistemic_repeated_stall_detected",) if switch_required else (),
                    )
                )
            ),
            blockers=report.blockers,
        )

    return _directive(
        problem=problem,
        round_index=round_index,
        move_kind=EpistemicMoveKind.PROBE,
        uncertainty=uncertainty,
        raw_confidence=raw_confidence,
        effective_confidence=effective_confidence,
        multiplier=multiplier,
        stall_count=stall_count,
        selected_probe=selected,
        candidates=candidates,
        reason_codes=("epistemic_highest_information_gain_probe_selected",),
        blockers=report.blockers,
    )


def prioritize_world_refresh(
    *,
    assessment: ContinuousWorldAssessment,
    expectations: tuple[SourceFreshnessExpectation, ...],
    value_signals: tuple[WorldSourceValueSignal, ...] = (),
) -> tuple[WorldRefreshPriority, ...]:
    """Rank the next live-world source to sense without performing the refresh."""

    expectation_map = {item.source_key: item for item in expectations}
    if len(expectation_map) != len(expectations):
        raise ValueError("world_refresh_duplicate_expectation")
    state_map = {item.source_key: item for item in assessment.source_states}
    if set(expectation_map) != set(state_map):
        raise ValueError("world_refresh_expectations_must_match_assessment")
    signal_map = {item.source_key: item for item in value_signals}
    if len(signal_map) != len(value_signals):
        raise ValueError("world_refresh_duplicate_value_signal")
    if set(signal_map) - set(state_map):
        raise ValueError("world_refresh_unknown_source_signal")

    priorities: list[WorldRefreshPriority] = []
    for source_key, state in sorted(state_map.items()):
        expectation = expectation_map[source_key]
        signal = signal_map.get(source_key) or WorldSourceValueSignal(source_key=source_key)
        if state.age_seconds is None:
            age_pressure = 1.0
        else:
            age_pressure = min(
                1.0,
                state.age_seconds / float(expectation.maximum_silence_seconds),
            )
        freshness_pressure = max(
            age_pressure,
            1.0 if not state.fresh else 0.0,
            0.90 if not state.authority_accepted else 0.0,
        )
        world_instability = min(
            1.0,
            assessment.world_change.change_ratio
            + min(assessment.world_change.changes_per_hour / 12.0, 1.0) * 0.35,
        )
        required_pressure = 1.0 if expectation.required_for_live_truth else 0.35
        expected_gain = min(
            1.0,
            0.38 * freshness_pressure
            + 0.22 * signal.contradiction_risk
            + 0.18 * signal.volatility
            + 0.12 * world_instability
            + 0.10 * signal.information_gain_hint,
        )
        score = min(
            1.0,
            0.28 * expected_gain
            + 0.24 * signal.business_importance
            + 0.16 * freshness_pressure
            + 0.12 * signal.volatility
            + 0.10 * signal.contradiction_risk
            + 0.10 * required_pressure,
        )
        reasons: list[str] = ["world_refresh_value_of_information_ranked"]
        if not state.fresh:
            reasons.append("world_refresh_source_not_fresh")
        if not state.authority_accepted:
            reasons.append("world_refresh_authority_gap")
        if expectation.required_for_live_truth:
            reasons.append("world_refresh_required_for_live_truth")
        if signal.business_importance >= 0.80:
            reasons.append("world_refresh_high_business_importance")
        if signal.volatility >= 0.70:
            reasons.append("world_refresh_high_volatility")
        if signal.contradiction_risk >= 0.50:
            reasons.append("world_refresh_material_contradiction_risk")
        priorities.append(
            WorldRefreshPriority(
                source_key=source_key,
                priority_score=round(score, 6),
                freshness_pressure=round(freshness_pressure, 6),
                expected_information_gain=round(expected_gain, 6),
                reason_codes=tuple(reasons),
                evidence_ref=state.evidence_ref,
            )
        )
    return tuple(sorted(priorities, key=lambda item: (-item.priority_score, item.source_key)))


def score_epistemic_benchmark(
    *,
    general_reasoning: float,
    deep_research: float,
    live_world_understanding: float,
    systematic_self_correction: float,
    novel_problem_solving: float,
    grounding_integrity: float,
    authority_integrity: float,
) -> EpistemicBenchmarkScore:
    """Score a named acceptance suite without converting it into a universal claim."""

    dimensions = (
        general_reasoning,
        deep_research,
        live_world_understanding,
        systematic_self_correction,
        novel_problem_solving,
    )
    if any(value < 0.0 or value > 1.0 for value in (*dimensions, grounding_integrity, authority_integrity)):
        raise ValueError("epistemic_benchmark_score_out_of_range")
    capability_mean = sum(dimensions) / len(dimensions)
    integrity_gate = min(grounding_integrity, authority_integrity)
    overall = round(capability_mean * integrity_gate, 6)
    complete = all(abs(value - 1.0) < 1e-12 for value in (*dimensions, grounding_integrity, authority_integrity))
    return EpistemicBenchmarkScore(
        general_reasoning=general_reasoning,
        deep_research=deep_research,
        live_world_understanding=live_world_understanding,
        systematic_self_correction=systematic_self_correction,
        novel_problem_solving=novel_problem_solving,
        grounding_integrity=grounding_integrity,
        authority_integrity=authority_integrity,
        overall=overall,
        benchmark_complete=complete,
    )


def _candidate_probes(
    *,
    problem: InvestigatorProblem,
    report: AutonomousInvestigationReport,
    history: tuple[EpistemicRoundObservation, ...],
    uncertainty: float,
    repeated_probe_penalty: float,
    calibration_multiplier: float,
) -> tuple[EpistemicProbe, ...]:
    assessment_map = {
        item.hypothesis_id: item
        for item in (report.ranking.assessments if report.ranking is not None else ())
    }
    leader_id = report.ranking.leading_hypothesis_id if report.ranking is not None else None
    repeated = {
        item.selected_probe_id
        for item in history
        if item.selected_probe_id is not None
    }
    probes: list[EpistemicProbe] = []
    for index, task_ref in enumerate(report.next_research_tasks):
        hypothesis_id = task_ref.split(":", 1)[0] if ":" in task_ref else None
        assessment = assessment_map.get(hypothesis_id or "")
        hypothesis_uncertainty = 1.0 - (assessment.confidence if assessment else 0.0)
        role, strategy, task_bonus = _task_strategy(task_ref)
        novelty_bonus = {
            ProblemNovelty.FAMILIAR: 0.0,
            ProblemNovelty.ADJACENT: 0.04,
            ProblemNovelty.NOVEL: 0.08,
        }[problem.novelty]
        leader_bonus = 0.06 if hypothesis_id and hypothesis_id == leader_id else 0.0
        calibration_pressure = max(0.0, 1.0 - calibration_multiplier) * 0.18
        gain = min(
            1.0,
            0.12
            + 0.30 * uncertainty
            + 0.28 * hypothesis_uncertainty
            + task_bonus
            + novelty_bonus
            + leader_bonus
            + calibration_pressure,
        )
        probe_id = _stable_probe_id(
            problem_id=problem.problem_id,
            task_ref=task_ref,
            strategy=strategy,
        )
        if probe_id in repeated:
            gain = max(0.0, gain - repeated_probe_penalty)
        probes.append(
            EpistemicProbe(
                probe_id=probe_id,
                hypothesis_id=hypothesis_id,
                task_ref=task_ref,
                role=role,
                strategy=strategy,
                query_intent=_query_intent(problem=problem, task_ref=task_ref, strategy=strategy),
                expected_information_gain=round(gain, 6),
                reason_codes=(
                    "epistemic_unresolved_research_gap",
                    f"epistemic_strategy:{strategy.value}",
                    f"epistemic_candidate_order:{index}",
                ),
            )
        )
    return tuple(
        sorted(
            probes,
            key=lambda item: (-item.expected_information_gain, item.probe_id),
        )
    )


def _calibration_or_gap_probe(
    *,
    problem: InvestigatorProblem,
    report: AutonomousInvestigationReport,
    uncertainty: float,
    calibration_multiplier: float,
) -> EpistemicProbe:
    leader_id = report.ranking.leading_hypothesis_id if report.ranking is not None else None
    if calibration_multiplier < 1.0:
        strategy = EpistemicStrategy.CONTRADICTION_FIRST
        role = ResearchRole.CONTRADICTION
        task_ref = f"{leader_id or 'global'}:post_error_revalidation"
        reason = "epistemic_grounded_error_requires_revalidation"
    else:
        strategy = EpistemicStrategy.CROSS_DOMAIN_EXPANSION
        role = ResearchRole.DOMAIN_SPECIALIST
        task_ref = f"{leader_id or 'global'}:resolve_residual_uncertainty"
        reason = "epistemic_residual_uncertainty_requires_new_angle"
    return EpistemicProbe(
        probe_id=_stable_probe_id(
            problem_id=problem.problem_id,
            task_ref=task_ref,
            strategy=strategy,
        ),
        hypothesis_id=leader_id,
        task_ref=task_ref,
        role=role,
        strategy=strategy,
        query_intent=_query_intent(problem=problem, task_ref=task_ref, strategy=strategy),
        expected_information_gain=round(
            min(1.0, 0.30 + 0.50 * uncertainty + (1.0 - calibration_multiplier) * 0.20),
            6,
        ),
        reason_codes=(reason,),
    )


def _task_strategy(task_ref: str) -> tuple[ResearchRole, EpistemicStrategy, float]:
    token = task_ref.casefold()
    if "run_falsification" in token:
        return ResearchRole.CONTRADICTION, EpistemicStrategy.FALSIFICATION, 0.24
    if "contradict" in token or "resolve_contradictory" in token:
        return ResearchRole.CONTRADICTION, EpistemicStrategy.CONTRADICTION_FIRST, 0.22
    if "primary" in token:
        return ResearchRole.PRIMARY_SOURCE, EpistemicStrategy.PRIMARY_TRIANGULATION, 0.18
    if "independent" in token or "corrobor" in token:
        return ResearchRole.CORROBORATION, EpistemicStrategy.INDEPENDENT_CORROBORATION, 0.17
    if "refresh" in token or "future_published" in token or "temporal" in token:
        return ResearchRole.TEMPORAL_UPDATE, EpistemicStrategy.TEMPORAL_REFRESH, 0.20
    if "quant" in token or "denominator" in token:
        return ResearchRole.QUANTITATIVE_CHECK, EpistemicStrategy.QUANTITATIVE_VALIDATION, 0.18
    return ResearchRole.DOMAIN_SPECIALIST, EpistemicStrategy.CROSS_DOMAIN_EXPANSION, 0.12


def _query_intent(
    *,
    problem: InvestigatorProblem,
    task_ref: str,
    strategy: EpistemicStrategy,
) -> str:
    return (
        f"Resolve '{task_ref}' for '{problem.question}' using {strategy.value}; "
        "prefer independent, time-valid evidence and actively search for disconfirmation."
    )


def _ranking_uncertainty(report: AutonomousInvestigationReport) -> float:
    if report.ranking is None or not report.ranking.assessments:
        return 1.0
    values = [max(item.confidence, 0.01) for item in report.ranking.assessments]
    if len(values) == 1:
        return round(1.0 - values[0], 6)
    total = sum(values)
    probabilities = [value / total for value in values]
    entropy = -sum(value * math.log(value, 2) for value in probabilities)
    normalized = entropy / math.log(len(probabilities), 2)
    decisiveness_pressure = 0.0 if report.ranking.decisive else 0.15
    return round(min(1.0, normalized + decisiveness_pressure), 6)


def _consecutive_stall_count(
    *,
    history: tuple[EpistemicRoundObservation, ...],
    current: EpistemicRoundObservation,
    minimum_confidence_delta: float,
) -> int:
    if not history:
        return 0
    count = 0
    newer = current
    for older in reversed(history):
        same_report = older.report_fingerprint == newer.report_fingerprint
        confidence_delta = abs(newer.leading_confidence - older.leading_confidence)
        no_new_evidence = newer.evidence_ref_count <= older.evidence_ref_count
        unresolved_not_improving = newer.unresolved_task_count >= older.unresolved_task_count
        stalled = same_report or (
            confidence_delta < minimum_confidence_delta
            and no_new_evidence
            and unresolved_not_improving
        )
        if not stalled:
            break
        count += 1
        newer = older
    return count


def _select_diverse_probe(
    *,
    candidates: tuple[EpistemicProbe, ...],
    history: tuple[EpistemicRoundObservation, ...],
) -> EpistemicProbe | None:
    previous_strategy = history[-1].selected_strategy if history else None
    for candidate in candidates:
        if candidate.strategy is not previous_strategy:
            return candidate
    return candidates[0] if candidates else None


def _validate_problem_report_scope(
    *,
    problem: InvestigatorProblem,
    report: AutonomousInvestigationReport,
) -> None:
    if report.problem_id != problem.problem_id:
        raise ValueError("epistemic_problem_report_id_mismatch")
    if report.tenant_id != problem.tenant_id:
        raise ValueError("epistemic_problem_report_tenant_mismatch")
    if report.company_id != problem.company_id:
        raise ValueError("epistemic_problem_report_company_mismatch")


def _stable_probe_id(
    *,
    problem_id: str,
    task_ref: str,
    strategy: EpistemicStrategy,
) -> str:
    payload = f"{problem_id}|{task_ref}|{strategy.value}".encode()
    return f"probe:{hashlib.sha256(payload).hexdigest()[:24]}"


def _directive(
    *,
    problem: InvestigatorProblem,
    round_index: int,
    move_kind: EpistemicMoveKind,
    uncertainty: float,
    raw_confidence: float,
    effective_confidence: float,
    multiplier: float,
    stall_count: int,
    reason_codes: tuple[str, ...],
    blockers: tuple[str, ...],
    selected_probe: EpistemicProbe | None = None,
    candidates: tuple[EpistemicProbe, ...] = (),
) -> AdaptiveEpistemicDirective:
    draft = {
        "contract": ADAPTIVE_EPISTEMIC_CONTROL_CONTRACT,
        "problem_id": problem.problem_id,
        "tenant_id": problem.tenant_id,
        "company_id": problem.company_id,
        "round_index": round_index,
        "move_kind": move_kind.value,
        "uncertainty": uncertainty,
        "raw_leading_confidence": raw_confidence,
        "effective_leading_confidence": effective_confidence,
        "calibration_multiplier": multiplier,
        "stall_count": stall_count,
        "selected_probe": selected_probe.model_dump(mode="json") if selected_probe else None,
        "candidate_probes": [item.model_dump(mode="json") for item in candidates],
        "reason_codes": list(dict.fromkeys(reason_codes)),
        "blockers": list(dict.fromkeys(blockers)),
        "firm_company_claim_authorized": False,
        "production_truth_promoted": False,
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "automatic_research_execution_allowed": False,
        "execution_authority_granted": False,
        "direct_provider_call_allowed": False,
    }
    return AdaptiveEpistemicDirective.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
