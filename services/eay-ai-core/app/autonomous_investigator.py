"""Autonomous epistemic investigation supervisor for Jarvis.

This module composes the existing research, competing-hypothesis, Company World,
outcome-learning and episodic-memory contracts into one fail-closed lifecycle.
It does not browse, call models, execute tools, promote Company World truth or
grant business authority. Instead, it makes the missing scientific behavior
explicit and testable: decompose unfamiliar problems, seek independent evidence,
actively falsify the leading explanation, refuse stale/contested conclusions,
and turn grounded outcomes into recallable, calibratable lessons.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .episodic_memory import EpisodeKind, MemoryEpisode, RetentionClass
from .hypothesis_intelligence import (
    EvidenceDirection,
    HypothesisCandidate,
    HypothesisEvidence,
    HypothesisRanking,
    rank_hypotheses,
)
from .outcome_learning import DecisionOutcomeAssessment
from .research_engine import (
    ResearchAssessment,
    ResearchEvidence,
    ResearchMission,
    ResearchQuestion,
    ResearchRisk,
    ResearchVerdict,
    assess_research,
    plan_research,
)
from .world_model import WorldSnapshot

AUTONOMOUS_INVESTIGATOR_CONTRACT = "eay-autonomous-investigator-v1"


class ProblemNovelty(str, Enum):
    FAMILIAR = "familiar"
    ADJACENT = "adjacent"
    NOVEL = "novel"


class InvestigatorDisposition(str, Enum):
    RESEARCH_MORE = "research_more"
    HOLD = "hold"
    DECISION_READY = "decision_ready"


class FalsificationVerdict(str, Enum):
    SURVIVED = "survived"
    REFUTED = "refuted"
    INCONCLUSIVE = "inconclusive"


class InvestigatorProblem(BaseModel):
    problem_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    question: str = Field(min_length=8)
    domains: tuple[str, ...] = ()
    as_of: datetime
    risk: ResearchRisk
    novelty: ProblemNovelty
    minimum_independent_sources: int = Field(default=2, ge=2, le=8)
    maximum_world_age_seconds: int = Field(default=900, ge=1, le=86_400)
    evidence_freshness_seconds: int = Field(default=86_400, ge=60, le=31_536_000)

    @model_validator(mode="after")
    def time_is_aware(self) -> "InvestigatorProblem":
        if self.as_of.tzinfo is None or self.as_of.utcoffset() is None:
            raise ValueError("investigator_problem_as_of_requires_timezone")
        return self


class InvestigatorHypothesis(BaseModel):
    hypothesis_id: str = Field(min_length=1)
    label: str = Field(min_length=3)
    claim_key: str = Field(min_length=1)
    required_falsification_test_ids: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def falsification_tests_are_unique(self) -> "InvestigatorHypothesis":
        if len(self.required_falsification_test_ids) != len(
            set(self.required_falsification_test_ids)
        ):
            raise ValueError("investigator_duplicate_falsification_test")
        return self


class SourceIndependenceBinding(BaseModel):
    evidence_id: str = Field(min_length=1)
    source_family_key: str = Field(min_length=1)


class FalsificationResult(BaseModel):
    test_id: str = Field(min_length=1)
    hypothesis_id: str = Field(min_length=1)
    verdict: FalsificationVerdict
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    completed_at: datetime

    @model_validator(mode="after")
    def completed_time_is_aware(self) -> "FalsificationResult":
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("investigator_falsification_time_requires_timezone")
        return self


class HypothesisResearchPlan(BaseModel):
    hypothesis_id: str
    claim_key: str
    mission: ResearchMission


class HypothesisResearchState(BaseModel):
    hypothesis_id: str
    claim_key: str
    assessment: ResearchAssessment
    independent_source_family_count: int = Field(ge=0)
    falsification_completed: bool
    falsification_refuted: bool
    material_contestation_resolved: bool
    blockers: tuple[str, ...] = ()


class AutonomousInvestigationReport(BaseModel):
    contract: str = AUTONOMOUS_INVESTIGATOR_CONTRACT
    problem_id: str
    tenant_id: str
    company_id: str
    world_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    novelty: ProblemNovelty
    disposition: InvestigatorDisposition
    ranking: HypothesisRanking | None
    research_states: tuple[HypothesisResearchState, ...]
    next_research_tasks: tuple[str, ...]
    blockers: tuple[str, ...]
    calibrated_confidence_cap: float = Field(ge=0.0, le=1.0)
    firm_company_claim_authorized: bool = False
    execution_authority_granted: bool = False
    production_truth_promoted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def report_is_advisory_and_integral(self) -> "AutonomousInvestigationReport":
        if (
            self.firm_company_claim_authorized
            or self.execution_authority_granted
            or self.production_truth_promoted
        ):
            raise ValueError("autonomous_investigator_never_grants_authority")
        if self.disposition is InvestigatorDisposition.DECISION_READY and self.blockers:
            raise ValueError("investigator_decision_ready_cannot_have_blockers")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("autonomous_investigator_fingerprint_mismatch")
        return self


class InvestigatorLesson(BaseModel):
    contract: str = AUTONOMOUS_INVESTIGATOR_CONTRACT
    lesson_id: str = Field(min_length=1)
    tenant_id: str
    company_id: str
    problem_id: str
    predicted_hypothesis_id: str
    resolved_hypothesis_id: str
    prediction_correct: bool
    brier_score: float = Field(ge=0.0, le=1.0)
    prior_confidence: float = Field(ge=0.0, le=1.0)
    suggested_confidence_multiplier: float = Field(ge=0.25, le=1.0)
    failure_codes: tuple[str, ...]
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    recorded_at: datetime
    model_weights_mutated: bool = False
    business_policy_mutated: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def lesson_is_grounded_and_non_mutating(self) -> "InvestigatorLesson":
        if self.recorded_at.tzinfo is None or self.recorded_at.utcoffset() is None:
            raise ValueError("investigator_lesson_recorded_at_requires_timezone")
        if self.model_weights_mutated or self.business_policy_mutated:
            raise ValueError("investigator_lesson_cannot_self_modify_production")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("investigator_lesson_fingerprint_mismatch")
        return self


class InvestigatorCalibrationProfile(BaseModel):
    contract: str = AUTONOMOUS_INVESTIGATOR_CONTRACT
    tenant_id: str
    company_id: str
    sample_count: int = Field(ge=1)
    mean_brier_score: float = Field(ge=0.0, le=1.0)
    prediction_error_rate: float = Field(ge=0.0, le=1.0)
    suggested_confidence_multiplier: float = Field(ge=0.25, le=1.0)
    lesson_fingerprints: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    automatic_activation_allowed: bool = False
    model_weights_mutated: bool = False
    business_policy_mutated: bool = False

    @model_validator(mode="after")
    def profile_cannot_self_activate(self) -> "InvestigatorCalibrationProfile":
        if (
            self.automatic_activation_allowed
            or self.model_weights_mutated
            or self.business_policy_mutated
        ):
            raise ValueError("investigator_calibration_cannot_self_modify_production")
        return self


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


def plan_autonomous_research(
    *,
    problem: InvestigatorProblem,
    hypotheses: tuple[InvestigatorHypothesis, ...],
) -> tuple[HypothesisResearchPlan, ...]:
    """Create contradiction-aware research missions for every competing hypothesis."""

    _validate_hypothesis_set(problem=problem, hypotheses=hypotheses)
    plans: list[HypothesisResearchPlan] = []
    for hypothesis in hypotheses:
        question = ResearchQuestion(
            question_id=f"{problem.problem_id}:{hypothesis.hypothesis_id}",
            question=(
                f"{problem.question} Test the competing hypothesis: {hypothesis.label}. "
                "Search for evidence that would falsify it, not only evidence that supports it."
            ),
            risk=problem.risk,
            domains=problem.domains,
            as_of=problem.as_of,
            requires_current_information=True,
            minimum_independent_sources=problem.minimum_independent_sources,
        )
        plans.append(
            HypothesisResearchPlan(
                hypothesis_id=hypothesis.hypothesis_id,
                claim_key=hypothesis.claim_key,
                mission=plan_research(question),
            )
        )
    return tuple(plans)


def evaluate_autonomous_investigation(
    *,
    problem: InvestigatorProblem,
    world: WorldSnapshot,
    hypotheses: tuple[InvestigatorHypothesis, ...],
    evidence: tuple[ResearchEvidence, ...],
    source_bindings: tuple[SourceIndependenceBinding, ...],
    falsification_results: tuple[FalsificationResult, ...],
) -> AutonomousInvestigationReport:
    """Evaluate research while aggressively refusing false certainty."""

    _validate_hypothesis_set(problem=problem, hypotheses=hypotheses)
    if world.tenant_id != problem.tenant_id:
        raise ValueError("investigator_world_tenant_mismatch")
    if world.as_of > problem.as_of:
        raise ValueError("investigator_world_snapshot_from_future")

    evidence_ids = [item.evidence_id for item in evidence]
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("investigator_duplicate_evidence_id")
    binding_map = {item.evidence_id: item.source_family_key for item in source_bindings}
    if len(binding_map) != len(source_bindings):
        raise ValueError("investigator_duplicate_source_binding")
    if set(binding_map) - set(evidence_ids):
        raise ValueError("investigator_source_binding_unknown_evidence")

    falsification_keys = [(item.hypothesis_id, item.test_id) for item in falsification_results]
    if len(falsification_keys) != len(set(falsification_keys)):
        raise ValueError("investigator_duplicate_falsification_result")

    hypothesis_map = {item.hypothesis_id: item for item in hypotheses}
    if any(item.hypothesis_id not in hypothesis_map for item in falsification_results):
        raise ValueError("investigator_falsification_unknown_hypothesis")

    blockers: list[str] = []
    age_seconds = (problem.as_of - world.as_of).total_seconds()
    if age_seconds > problem.maximum_world_age_seconds:
        blockers.append("investigator_world_state_stale")
    if world.blocked_field_keys:
        blockers.append("investigator_world_state_contradicted")

    high_stakes = problem.risk in {ResearchRisk.HIGH, ResearchRisk.CRITICAL}
    if high_stakes and set(evidence_ids) - set(binding_map):
        blockers.append("investigator_source_family_binding_incomplete")

    states: list[HypothesisResearchState] = []
    candidates: list[HypothesisCandidate] = []
    all_candidates_have_directional_evidence = True
    next_tasks: list[str] = []

    for hypothesis in hypotheses:
        question = ResearchQuestion(
            question_id=f"{problem.problem_id}:{hypothesis.hypothesis_id}",
            question=f"{problem.question} Hypothesis: {hypothesis.label}",
            risk=problem.risk,
            domains=problem.domains,
            as_of=problem.as_of,
            requires_current_information=True,
            minimum_independent_sources=problem.minimum_independent_sources,
        )
        assessment = assess_research(
            question,
            claim_key=hypothesis.claim_key,
            evidence=list(evidence),
            freshness_window=timedelta(seconds=problem.evidence_freshness_seconds),
        )

        relevant = [item for item in evidence if item.claim_key == hypothesis.claim_key]
        families = {
            binding_map.get(item.evidence_id, item.publisher_key)
            for item in relevant
            if item.supports_claim or item.contradicts_claim
        }
        directional = [
            item
            for item in relevant
            if item.supports_claim or item.contradicts_claim
        ]
        hypothesis_evidence: list[HypothesisEvidence] = []
        for item in directional:
            direction = (
                EvidenceDirection.SUPPORT
                if item.supports_claim
                else EvidenceDirection.REFUTE
            )
            if item.source_tier.value == "primary":
                quality = 1.0
            elif item.source_tier.value == "authoritative_secondary":
                quality = 0.9
            elif item.source_tier.value == "reputable_secondary":
                quality = 0.75
            else:
                quality = 0.35
            hypothesis_evidence.append(
                HypothesisEvidence(
                    evidence_ref=item.evidence_ref,
                    direction=direction,
                    weight=1.0,
                    source_quality=quality,
                    independent_source_key=binding_map.get(
                        item.evidence_id,
                        item.publisher_key,
                    ),
                )
            )

        required_tests = set(hypothesis.required_falsification_test_ids)
        completed = {
            item.test_id: item
            for item in falsification_results
            if item.hypothesis_id == hypothesis.hypothesis_id
            and item.test_id in required_tests
        }
        falsification_completed = required_tests.issubset(completed)
        falsification_refuted = any(
            item.verdict is FalsificationVerdict.REFUTED
            for item in completed.values()
        )
        falsification_survived = (
            falsification_completed
            and bool(completed)
            and all(
                item.verdict is FalsificationVerdict.SURVIVED
                for item in completed.values()
            )
        )
        material_contestation_resolved = (
            assessment.verdict is ResearchVerdict.CONTESTED
            and falsification_survived
        )

        state_blockers = list(assessment.blockers)
        if material_contestation_resolved:
            state_blockers = [
                item
                for item in state_blockers
                if item != "research_material_contradiction_unresolved"
            ]
        if len(families) < problem.minimum_independent_sources:
            state_blockers.append("investigator_independent_source_family_quorum_missing")
        if not falsification_completed:
            state_blockers.append("investigator_falsification_incomplete")
        if any(
            item.verdict is FalsificationVerdict.INCONCLUSIVE
            for item in completed.values()
        ):
            state_blockers.append("investigator_falsification_inconclusive")
        if falsification_refuted and not any(
            item.direction is EvidenceDirection.REFUTE for item in hypothesis_evidence
        ):
            state_blockers.append("investigator_refutation_not_reflected_in_evidence")

        for gap in assessment.unresolved_gaps:
            if not (
                material_contestation_resolved
                and gap == "resolve_contradictory_evidence"
            ):
                next_tasks.append(f"{hypothesis.hypothesis_id}:{gap}")
        for test_id in sorted(required_tests - set(completed)):
            next_tasks.append(f"{hypothesis.hypothesis_id}:run_falsification:{test_id}")

        states.append(
            HypothesisResearchState(
                hypothesis_id=hypothesis.hypothesis_id,
                claim_key=hypothesis.claim_key,
                assessment=assessment,
                independent_source_family_count=len(families),
                falsification_completed=falsification_completed,
                falsification_refuted=falsification_refuted,
                material_contestation_resolved=material_contestation_resolved,
                blockers=tuple(dict.fromkeys(state_blockers)),
            )
        )

        if hypothesis_evidence:
            missing_tests = () if falsification_completed else tuple(
                sorted(required_tests - set(completed))
            )
            candidates.append(
                HypothesisCandidate(
                    hypothesis_id=hypothesis.hypothesis_id,
                    label=hypothesis.label,
                    evidence=tuple(hypothesis_evidence),
                    missing_tests=missing_tests,
                )
            )
        else:
            all_candidates_have_directional_evidence = False
            next_tasks.append(f"{hypothesis.hypothesis_id}:obtain_directional_evidence")

    ranking: HypothesisRanking | None = None
    if all_candidates_have_directional_evidence and len(candidates) == len(hypotheses):
        ranking = rank_hypotheses(candidates)
    else:
        blockers.append("investigator_hypothesis_evidence_incomplete")

    leader_state: HypothesisResearchState | None = None
    if ranking is not None:
        blockers.extend(ranking.blockers)
        if ranking.leading_hypothesis_id is not None:
            leader_state = next(
                item
                for item in states
                if item.hypothesis_id == ranking.leading_hypothesis_id
            )
            blockers.extend(leader_state.blockers)
            research_supported = (
                leader_state.assessment.verdict is ResearchVerdict.SUPPORTED
                or leader_state.material_contestation_resolved
            )
            if not research_supported:
                blockers.append("investigator_leading_hypothesis_not_research_supported")
            if leader_state.falsification_refuted:
                blockers.append("investigator_leading_hypothesis_refuted")
        if not ranking.decisive:
            blockers.append("investigator_hypothesis_ranking_not_decisive")

    blockers = list(dict.fromkeys(blockers))
    if not evidence:
        disposition = InvestigatorDisposition.RESEARCH_MORE
    elif blockers:
        hard_hold = any(
            item in blockers
            for item in (
                "investigator_world_state_stale",
                "investigator_world_state_contradicted",
                "investigator_leading_hypothesis_refuted",
                "research_material_contradiction_unresolved",
            )
        )
        disposition = (
            InvestigatorDisposition.HOLD
            if hard_hold
            else InvestigatorDisposition.RESEARCH_MORE
        )
    else:
        disposition = InvestigatorDisposition.DECISION_READY

    if ranking is not None and ranking.assessments and leader_state is not None:
        confidence_cap = min(
            ranking.assessments[0].confidence,
            leader_state.assessment.confidence_cap,
        )
    else:
        confidence_cap = min(
            (item.assessment.confidence_cap for item in states),
            default=0.0,
        )
    if disposition is not InvestigatorDisposition.DECISION_READY:
        confidence_cap = min(confidence_cap, 0.60)

    draft = {
        "contract": AUTONOMOUS_INVESTIGATOR_CONTRACT,
        "problem_id": problem.problem_id,
        "tenant_id": problem.tenant_id,
        "company_id": problem.company_id,
        "world_snapshot_fingerprint": world.fingerprint,
        "novelty": problem.novelty.value,
        "disposition": disposition.value,
        "ranking": ranking.model_dump(mode="json") if ranking is not None else None,
        "research_states": [item.model_dump(mode="json") for item in states],
        "next_research_tasks": list(dict.fromkeys(next_tasks)),
        "blockers": blockers,
        "calibrated_confidence_cap": round(max(0.0, min(confidence_cap, 1.0)), 6),
        "firm_company_claim_authorized": False,
        "execution_authority_granted": False,
        "production_truth_promoted": False,
    }
    return AutonomousInvestigationReport.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def build_investigator_lesson(
    *,
    report: AutonomousInvestigationReport,
    resolved_hypothesis_id: str,
    outcome: DecisionOutcomeAssessment,
    recorded_at: datetime,
) -> tuple[InvestigatorLesson, MemoryEpisode]:
    """Turn a grounded measured outcome into a calibrated, recallable lesson."""

    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ValueError("investigator_lesson_recorded_at_requires_timezone")
    if outcome.tenant_id != report.tenant_id:
        raise ValueError("investigator_lesson_tenant_mismatch")
    if not outcome.metric_results or not outcome.learning_evidence_refs:
        raise ValueError("investigator_lesson_requires_grounded_measured_outcome")
    if report.ranking is None or report.ranking.leading_hypothesis_id is None:
        raise ValueError("investigator_lesson_requires_prior_prediction")
    known_hypotheses = {item.hypothesis_id for item in report.ranking.assessments}
    if resolved_hypothesis_id not in known_hypotheses:
        raise ValueError("investigator_lesson_unknown_resolved_hypothesis")

    predicted = report.ranking.leading_hypothesis_id
    leader = next(
        item
        for item in report.ranking.assessments
        if item.hypothesis_id == predicted
    )
    probability = leader.confidence
    truth = 1.0 if predicted == resolved_hypothesis_id else 0.0
    brier = (probability - truth) ** 2
    failure_codes = list(report.blockers)
    if predicted != resolved_hypothesis_id:
        failure_codes.append("investigator_leading_hypothesis_was_wrong")
    if outcome.direction_accuracy is not None and outcome.direction_accuracy < 0.5:
        failure_codes.append("investigator_outcome_direction_accuracy_low")

    multiplier = min(1.0, outcome.suggested_confidence_multiplier)
    if predicted != resolved_hypothesis_id:
        multiplier = min(multiplier, 0.75)
    if brier > 0.25:
        multiplier = min(multiplier, 0.70)

    evidence_refs = tuple(dict.fromkeys(outcome.learning_evidence_refs))
    lesson_seed = {
        "contract": AUTONOMOUS_INVESTIGATOR_CONTRACT,
        "lesson_id": f"lesson:{report.problem_id}:{outcome.decision_id}",
        "tenant_id": report.tenant_id,
        "company_id": report.company_id,
        "problem_id": report.problem_id,
        "predicted_hypothesis_id": predicted,
        "resolved_hypothesis_id": resolved_hypothesis_id,
        "prediction_correct": predicted == resolved_hypothesis_id,
        "brier_score": round(brier, 6),
        "prior_confidence": probability,
        "suggested_confidence_multiplier": round(multiplier, 6),
        "failure_codes": list(dict.fromkeys(failure_codes)),
        "evidence_refs": list(evidence_refs),
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "model_weights_mutated": False,
        "business_policy_mutated": False,
    }
    lesson = InvestigatorLesson.model_validate(
        {**lesson_seed, "fingerprint": _fingerprint(lesson_seed)}
    )
    episode = MemoryEpisode(
        episode_id=lesson.lesson_id,
        tenant_id=lesson.tenant_id,
        kind=EpisodeKind.LESSON,
        occurred_at=recorded_at,
        recorded_at=recorded_at,
        title=f"Investigator lesson for {lesson.problem_id}",
        content_ref=f"artifact://jarvis/investigator-lesson/{lesson.fingerprint}",
        evidence_refs=lesson.evidence_refs,
        entity_refs=(f"company:{lesson.company_id}",),
        tags=(
            "autonomous-investigator",
            f"problem:{lesson.problem_id}",
            f"predicted:{lesson.predicted_hypothesis_id}",
            f"resolved:{lesson.resolved_hypothesis_id}",
            *(f"failure:{item}" for item in lesson.failure_codes),
        ),
        importance=0.9 if not lesson.prediction_correct else 0.7,
        retention_class=RetentionClass.LONG_TERM,
        model_summary=None,
        model_summary_is_truth=False,
    )
    return lesson, episode


def calibrate_investigator_lessons(
    lessons: tuple[InvestigatorLesson, ...],
) -> InvestigatorCalibrationProfile:
    """Aggregate grounded errors into a bounded confidence recommendation."""

    if not lessons:
        raise ValueError("investigator_calibration_requires_lessons")
    tenants = {item.tenant_id for item in lessons}
    companies = {item.company_id for item in lessons}
    if len(tenants) != 1 or len(companies) != 1:
        raise ValueError("investigator_calibration_scope_mismatch")
    fingerprints = tuple(item.fingerprint for item in lessons)
    if len(fingerprints) != len(set(fingerprints)):
        raise ValueError("investigator_calibration_duplicate_lesson")

    mean_brier = sum(item.brier_score for item in lessons) / len(lessons)
    error_rate = sum(1 for item in lessons if not item.prediction_correct) / len(lessons)
    lesson_multiplier = sum(
        item.suggested_confidence_multiplier for item in lessons
    ) / len(lessons)
    calibration_penalty = 1.0 - 0.50 * mean_brier - 0.25 * error_rate
    multiplier = max(0.25, min(1.0, lesson_multiplier, calibration_penalty))
    evidence_refs = tuple(
        dict.fromkeys(
            ref
            for lesson in lessons
            for ref in lesson.evidence_refs
        )
    )
    return InvestigatorCalibrationProfile(
        tenant_id=next(iter(tenants)),
        company_id=next(iter(companies)),
        sample_count=len(lessons),
        mean_brier_score=round(mean_brier, 6),
        prediction_error_rate=round(error_rate, 6),
        suggested_confidence_multiplier=round(multiplier, 6),
        lesson_fingerprints=fingerprints,
        evidence_refs=evidence_refs,
    )


def _validate_hypothesis_set(
    *,
    problem: InvestigatorProblem,
    hypotheses: tuple[InvestigatorHypothesis, ...],
) -> None:
    minimum = 3 if problem.novelty is ProblemNovelty.NOVEL else 2
    if len(hypotheses) < minimum:
        raise ValueError("investigator_competing_hypotheses_insufficient")
    ids = [item.hypothesis_id for item in hypotheses]
    claims = [item.claim_key for item in hypotheses]
    if len(ids) != len(set(ids)):
        raise ValueError("investigator_duplicate_hypothesis_id")
    if len(claims) != len(set(claims)):
        raise ValueError("investigator_duplicate_hypothesis_claim_key")
