from datetime import datetime, timedelta, timezone

import pytest

from app.teaching_intelligence import (
    AdaptiveLessonPlan,
    ConceptMastery,
    CurriculumGraph,
    LearnerProfile,
    LearningObjective,
    LearningObservation,
    MasteryStatus,
    TeachingMove,
    TeachingOutcome,
    assess_mastery,
    evaluate_teaching_outcome,
    plan_adaptive_lesson,
)

NOW = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)


def _objective(objective_id="advanced", prerequisites=("foundation",), transfer=True):
    return LearningObjective(
        objective_id=objective_id,
        domain="operations",
        title=objective_id,
        prerequisite_ids=prerequisites,
        source_refs=(f"source://{objective_id}",),
        required_mastery_score=0.85,
        transfer_required=transfer,
    )


def _curriculum():
    return CurriculumGraph(
        objectives=(
            _objective("foundation", prerequisites=(), transfer=True),
            _objective("advanced", prerequisites=("foundation",), transfer=True),
        )
    )


def _profile(mastery=()):
    return LearnerProfile(
        learner_ref="user:42",
        preferred_language="tr",
        goal_refs=("goal://expert",),
        mastery=mastery,
    )


def _obs(objective_id, when, retrieval, explanation, transfer):
    return LearningObservation(
        objective_id=objective_id,
        observed_at=when,
        retrieval_score=retrieval,
        explanation_score=explanation,
        transfer_score=transfer,
        evidence_refs=(f"assessment://{objective_id}/{int(when.timestamp())}",),
    )


def test_single_high_score_cannot_claim_mastery_without_delayed_retrieval():
    objective = _objective("foundation", prerequisites=())
    result = assess_mastery(
        objective=objective,
        observations=[_obs("foundation", NOW, 1.0, 1.0, 1.0)],
        now=NOW,
    )
    assert result.status is MasteryStatus.PROVISIONAL
    assert "teaching_delayed_retrieval_missing" in result.blockers
    assert "teaching_repeated_evidence_missing" in result.blockers


def test_repeated_delayed_retrieval_explanation_and_transfer_can_reach_mastery():
    objective = _objective("foundation", prerequisites=())
    result = assess_mastery(
        objective=objective,
        observations=[
            _obs("foundation", NOW - timedelta(days=2), 0.90, 0.85, 0.82),
            _obs("foundation", NOW, 0.94, 0.90, 0.88),
        ],
        now=NOW,
    )
    assert result.status is MasteryStatus.MASTERED
    assert result.delayed_retrieval_observed is True
    assert result.next_review_at == NOW + timedelta(days=30)
    assert result.blockers == ()


def test_transfer_is_required_when_objective_requires_it():
    objective = _objective("foundation", prerequisites=(), transfer=True)
    result = assess_mastery(
        objective=objective,
        observations=[
            _obs("foundation", NOW - timedelta(days=2), 0.95, 0.90, None),
            _obs("foundation", NOW, 0.95, 0.90, None),
        ],
        now=NOW,
    )
    assert result.status is not MasteryStatus.MASTERED
    assert "teaching_transfer_evidence_insufficient" in result.blockers


def test_unmastered_prerequisite_is_taught_before_advanced_target():
    plan = plan_adaptive_lesson(
        learner=_profile(),
        target_objective_id="advanced",
        curriculum=_curriculum(),
    )
    assert plan.prerequisite_remediation is True
    assert plan.effective_objective_id == "foundation"
    assert plan.steps[0].move is TeachingMove.DIAGNOSTIC
    assert TeachingMove.RETRIEVAL_PRACTICE in {step.move for step in plan.steps}
    assert TeachingMove.TEACH_BACK in {step.move for step in plan.steps}
    assert TeachingMove.TRANSFER_CHALLENGE in {step.move for step in plan.steps}


def test_mastered_prerequisite_allows_target_instruction():
    mastered = ConceptMastery(
        objective_id="foundation",
        status=MasteryStatus.MASTERED,
        mastery_score=0.92,
        retrieval_score=0.94,
        explanation_score=0.90,
        transfer_score=0.88,
        attempts=3,
        delayed_retrieval_observed=True,
        next_review_at=NOW + timedelta(days=20),
    )
    plan = plan_adaptive_lesson(
        learner=_profile((mastered,)),
        target_objective_id="advanced",
        curriculum=_curriculum(),
    )
    assert plan.prerequisite_remediation is False
    assert plan.effective_objective_id == "advanced"


def test_curriculum_cycle_fails_closed():
    with pytest.raises(ValueError, match="teaching_curriculum_cycle_detected"):
        CurriculumGraph(
            objectives=(
                _objective("a", prerequisites=("b",)),
                _objective("b", prerequisites=("a",)),
            )
        )


def test_raw_answers_and_hidden_reasoning_are_not_required_or_retained():
    with pytest.raises(ValueError, match="teaching_observation_should_retain_scores_not_raw_answer"):
        LearningObservation(
            objective_id="foundation",
            observed_at=NOW,
            retrieval_score=0.8,
            explanation_score=0.8,
            transfer_score=0.8,
            evidence_refs=("assessment://1",),
            answer_text_retained=True,
        )
    with pytest.raises(ValueError, match="teaching_cannot_require_hidden_reasoning"):
        LearningObservation(
            objective_id="foundation",
            observed_at=NOW,
            retrieval_score=0.8,
            explanation_score=0.8,
            transfer_score=0.8,
            evidence_refs=("assessment://1",),
            hidden_reasoning_requested=True,
        )


def test_effective_strategy_is_only_a_candidate_and_never_self_promotes():
    result = evaluate_teaching_outcome(
        TeachingOutcome(
            learner_ref="user:42",
            objective_id="foundation",
            pretest_score=0.40,
            posttest_score=0.90,
            delayed_score=0.86,
            transfer_score=0.82,
            strategy_ref="teacher-strategy://v1",
            evidence_refs=("eval://lesson-1",),
        )
    )
    assert result.promotion_candidate is True
    assert result.automatic_strategy_promotion_allowed is False
    assert result.blockers == ()


def test_plan_never_requests_hidden_reasoning_or_model_self_modification():
    plan: AdaptiveLessonPlan = plan_adaptive_lesson(
        learner=_profile(),
        target_objective_id="foundation",
        curriculum=_curriculum(),
    )
    assert plan.hidden_reasoning_required is False
    assert plan.automatic_model_weight_update_allowed is False
