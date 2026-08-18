"""Evidence-bound adaptive teaching intelligence for EAY Jarvis.

Jarvis should not merely explain; it should diagnose what a learner knows,
select the next prerequisite or target, make the learner retrieve and explain,
challenge transfer, schedule review, and measure durable mastery.  This module
keeps pedagogical adaptation separate from model self-modification: teaching
strategy may be proposed from measured outcomes, but production model weights,
policies, permissions and hidden reasoning are never changed or exposed here.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

TEACHING_INTELLIGENCE_CONTRACT = "eay-teaching-intelligence-v1"


class TeachingMove(str, Enum):
    DIAGNOSTIC = "diagnostic"
    EXPLAIN = "explain"
    WORKED_EXAMPLE = "worked_example"
    CONTRASTIVE_EXAMPLE = "contrastive_example"
    RETRIEVAL_PRACTICE = "retrieval_practice"
    TEACH_BACK = "teach_back"
    TRANSFER_CHALLENGE = "transfer_challenge"
    FEEDBACK = "feedback"
    SPACED_REVIEW = "spaced_review"


class MasteryStatus(str, Enum):
    NOT_ASSESSED = "not_assessed"
    DEVELOPING = "developing"
    PROVISIONAL = "provisional"
    MASTERED = "mastered"


class LearningObjective(BaseModel):
    objective_id: str = Field(min_length=1)
    domain: str = Field(min_length=1)
    title: str = Field(min_length=1)
    prerequisite_ids: tuple[str, ...] = ()
    source_refs: tuple[str, ...] = Field(min_length=1)
    required_mastery_score: float = Field(default=0.85, ge=0.60, le=1.0)
    transfer_required: bool = True


class CurriculumGraph(BaseModel):
    objectives: tuple[LearningObjective, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def graph_is_valid(self) -> "CurriculumGraph":
        ids = [item.objective_id for item in self.objectives]
        if len(ids) != len(set(ids)):
            raise ValueError("teaching_curriculum_duplicate_objective")
        known = set(ids)
        for item in self.objectives:
            if item.objective_id in item.prerequisite_ids:
                raise ValueError("teaching_curriculum_self_prerequisite")
            if any(ref not in known for ref in item.prerequisite_ids):
                raise ValueError("teaching_curriculum_unknown_prerequisite")

        edges = {item.objective_id: item.prerequisite_ids for item in self.objectives}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("teaching_curriculum_cycle_detected")
            if node in visited:
                return
            visiting.add(node)
            for parent in edges[node]:
                visit(parent)
            visiting.remove(node)
            visited.add(node)

        for node in ids:
            visit(node)
        return self

    def by_id(self) -> dict[str, LearningObjective]:
        return {item.objective_id: item for item in self.objectives}


class LearningObservation(BaseModel):
    objective_id: str = Field(min_length=1)
    observed_at: datetime
    retrieval_score: float = Field(ge=0.0, le=1.0)
    explanation_score: float = Field(ge=0.0, le=1.0)
    transfer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    learner_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    answer_text_retained: bool = False
    hidden_reasoning_requested: bool = False

    @model_validator(mode="after")
    def observation_is_safe(self) -> "LearningObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("teaching_observation_requires_timezone")
        if self.answer_text_retained:
            raise ValueError("teaching_observation_should_retain_scores_not_raw_answer")
        if self.hidden_reasoning_requested:
            raise ValueError("teaching_cannot_require_hidden_reasoning")
        return self


class ConceptMastery(BaseModel):
    objective_id: str
    status: MasteryStatus
    mastery_score: float = Field(ge=0.0, le=1.0)
    retrieval_score: float = Field(ge=0.0, le=1.0)
    explanation_score: float = Field(ge=0.0, le=1.0)
    transfer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    attempts: int = Field(ge=0)
    delayed_retrieval_observed: bool = False
    next_review_at: datetime | None = None
    blockers: tuple[str, ...] = ()


class LearnerProfile(BaseModel):
    learner_ref: str = Field(min_length=1)
    preferred_language: str = Field(min_length=2)
    goal_refs: tuple[str, ...] = Field(min_length=1)
    mastery: tuple[ConceptMastery, ...] = ()
    private_content_retained: bool = False

    @model_validator(mode="after")
    def profile_is_minimal(self) -> "LearnerProfile":
        if self.private_content_retained:
            raise ValueError("teaching_profile_cannot_retain_private_learning_content")
        ids = [item.objective_id for item in self.mastery]
        if len(ids) != len(set(ids)):
            raise ValueError("teaching_profile_duplicate_mastery")
        return self

    def mastery_by_id(self) -> dict[str, ConceptMastery]:
        return {item.objective_id: item for item in self.mastery}


class LessonStep(BaseModel):
    order: int = Field(ge=1)
    move: TeachingMove
    objective_id: str = Field(min_length=1)
    purpose: str = Field(min_length=1)
    source_refs: tuple[str, ...] = Field(min_length=1)
    low_stakes: bool = True


class AdaptiveLessonPlan(BaseModel):
    contract: str = TEACHING_INTELLIGENCE_CONTRACT
    learner_ref: str
    target_objective_id: str
    effective_objective_id: str
    prerequisite_remediation: bool = False
    steps: tuple[LessonStep, ...] = Field(min_length=1)
    mastery_must_be_measured: bool = True
    automatic_model_weight_update_allowed: bool = False
    hidden_reasoning_required: bool = False

    @model_validator(mode="after")
    def lesson_preserves_boundaries(self) -> "AdaptiveLessonPlan":
        if self.automatic_model_weight_update_allowed:
            raise ValueError("teaching_plan_cannot_self_modify_model")
        if self.hidden_reasoning_required:
            raise ValueError("teaching_plan_cannot_require_hidden_reasoning")
        orders = [step.order for step in self.steps]
        if orders != list(range(1, len(orders) + 1)):
            raise ValueError("teaching_plan_steps_must_be_contiguous")
        return self


class TeachingOutcome(BaseModel):
    learner_ref: str
    objective_id: str
    pretest_score: float = Field(ge=0.0, le=1.0)
    posttest_score: float = Field(ge=0.0, le=1.0)
    delayed_score: float | None = Field(default=None, ge=0.0, le=1.0)
    transfer_score: float | None = Field(default=None, ge=0.0, le=1.0)
    strategy_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class TeachingEffectiveness(BaseModel):
    contract: str = TEACHING_INTELLIGENCE_CONTRACT
    objective_id: str
    immediate_gain: float
    delayed_retention: float | None
    transfer_score: float | None
    strategy_ref: str
    promotion_candidate: bool = False
    automatic_strategy_promotion_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def effectiveness_does_not_self_promote(self) -> "TeachingEffectiveness":
        if self.automatic_strategy_promotion_allowed:
            raise ValueError("teaching_effectiveness_cannot_self_promote_strategy")
        return self


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def assess_mastery(
    *,
    objective: LearningObjective,
    observations: list[LearningObservation],
    now: datetime,
) -> ConceptMastery:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("teaching_mastery_now_requires_timezone")
    relevant = sorted(
        (item for item in observations if item.objective_id == objective.objective_id),
        key=lambda item: item.observed_at,
    )
    if not relevant:
        return ConceptMastery(
            objective_id=objective.objective_id,
            status=MasteryStatus.NOT_ASSESSED,
            mastery_score=0.0,
            retrieval_score=0.0,
            explanation_score=0.0,
            attempts=0,
            next_review_at=now,
            blockers=("teaching_mastery_evidence_missing",),
        )

    retrieval = _mean([item.retrieval_score for item in relevant])
    explanation = _mean([item.explanation_score for item in relevant])
    transfers = [item.transfer_score for item in relevant if item.transfer_score is not None]
    transfer = _mean(transfers) if transfers else None
    weights = [(retrieval, 0.50), (explanation, 0.25)]
    if transfer is not None:
        weights.append((transfer, 0.25))
    else:
        weights = [(retrieval, 2 / 3), (explanation, 1 / 3)]
    mastery_score = sum(score * weight for score, weight in weights)

    delayed = False
    if len(relevant) >= 2:
        delayed = relevant[-1].observed_at - relevant[0].observed_at >= timedelta(hours=20)

    blockers: list[str] = []
    if retrieval < objective.required_mastery_score:
        blockers.append("teaching_retrieval_below_mastery_floor")
    if explanation < 0.70:
        blockers.append("teaching_explanation_below_mastery_floor")
    if objective.transfer_required and (transfer is None or transfer < 0.70):
        blockers.append("teaching_transfer_evidence_insufficient")
    if not delayed:
        blockers.append("teaching_delayed_retrieval_missing")
    if len(relevant) < 2:
        blockers.append("teaching_repeated_evidence_missing")

    if not blockers and mastery_score >= objective.required_mastery_score:
        status = MasteryStatus.MASTERED
        review_gap = timedelta(days=30)
    elif mastery_score >= objective.required_mastery_score:
        status = MasteryStatus.PROVISIONAL
        review_gap = timedelta(days=7)
    else:
        status = MasteryStatus.DEVELOPING
        if mastery_score < 0.50:
            review_gap = timedelta(days=1)
        elif mastery_score < 0.70:
            review_gap = timedelta(days=3)
        else:
            review_gap = timedelta(days=7)

    return ConceptMastery(
        objective_id=objective.objective_id,
        status=status,
        mastery_score=round(mastery_score, 6),
        retrieval_score=round(retrieval, 6),
        explanation_score=round(explanation, 6),
        transfer_score=round(transfer, 6) if transfer is not None else None,
        attempts=len(relevant),
        delayed_retrieval_observed=delayed,
        next_review_at=now + review_gap,
        blockers=tuple(dict.fromkeys(blockers)),
    )


def _effective_objective(
    *,
    target: LearningObjective,
    curriculum: CurriculumGraph,
    profile: LearnerProfile,
) -> tuple[LearningObjective, bool]:
    by_id = curriculum.by_id()
    mastery = profile.mastery_by_id()
    for prerequisite_id in target.prerequisite_ids:
        state = mastery.get(prerequisite_id)
        if state is None or state.status is not MasteryStatus.MASTERED:
            return by_id[prerequisite_id], True
    return target, False


def plan_adaptive_lesson(
    *,
    learner: LearnerProfile,
    target_objective_id: str,
    curriculum: CurriculumGraph,
) -> AdaptiveLessonPlan:
    target = curriculum.by_id().get(target_objective_id)
    if target is None:
        raise ValueError("teaching_target_objective_unknown")
    effective, remediation = _effective_objective(
        target=target,
        curriculum=curriculum,
        profile=learner,
    )
    state = learner.mastery_by_id().get(effective.objective_id)

    moves: list[tuple[TeachingMove, str]] = []
    if state is None or state.status is MasteryStatus.NOT_ASSESSED:
        moves.append((TeachingMove.DIAGNOSTIC, "measure prior knowledge before instruction"))
    elif state.next_review_at is not None:
        moves.append((TeachingMove.SPACED_REVIEW, "retrieve previously learned material before adding complexity"))

    moves.extend(
        [
            (TeachingMove.EXPLAIN, "connect the concept to prior knowledge with a concise sourced explanation"),
            (TeachingMove.WORKED_EXAMPLE, "show one complete worked example and the governing principle"),
            (TeachingMove.CONTRASTIVE_EXAMPLE, "separate the concept from a plausible near-miss or misconception"),
            (TeachingMove.RETRIEVAL_PRACTICE, "require recall without copying the explanation"),
            (TeachingMove.TEACH_BACK, "ask the learner to explain the concept in their own words"),
            (TeachingMove.TRANSFER_CHALLENGE, "apply the concept to a new context rather than repeat the example"),
            (TeachingMove.FEEDBACK, "give specific corrective feedback and identify the next knowledge gap"),
        ]
    )
    steps = tuple(
        LessonStep(
            order=index,
            move=move,
            objective_id=effective.objective_id,
            purpose=purpose,
            source_refs=effective.source_refs,
        )
        for index, (move, purpose) in enumerate(moves, start=1)
    )
    return AdaptiveLessonPlan(
        learner_ref=learner.learner_ref,
        target_objective_id=target.objective_id,
        effective_objective_id=effective.objective_id,
        prerequisite_remediation=remediation,
        steps=steps,
    )


def evaluate_teaching_outcome(outcome: TeachingOutcome) -> TeachingEffectiveness:
    blockers: list[str] = []
    gain = outcome.posttest_score - outcome.pretest_score
    if outcome.delayed_score is None:
        blockers.append("teaching_delayed_outcome_missing")
    if outcome.transfer_score is None:
        blockers.append("teaching_transfer_outcome_missing")
    delayed = outcome.delayed_score
    transfer = outcome.transfer_score
    candidate = (
        gain >= 0.15
        and delayed is not None
        and delayed >= 0.80
        and transfer is not None
        and transfer >= 0.75
    )
    if not candidate:
        blockers.append("teaching_strategy_effectiveness_threshold_not_met")
    return TeachingEffectiveness(
        objective_id=outcome.objective_id,
        immediate_gain=round(gain, 6),
        delayed_retention=delayed,
        transfer_score=transfer,
        strategy_ref=outcome.strategy_ref,
        promotion_candidate=candidate,
        automatic_strategy_promotion_allowed=False,
        blockers=tuple(dict.fromkeys(blockers)),
    )
