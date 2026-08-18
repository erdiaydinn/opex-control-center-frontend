import pytest

from app.trajectory_improvement import (
    EvaluationEnvironment,
    ImprovementStatus,
    ImprovementTarget,
    ImprovementValidationEvidence,
    OfflineTrajectoryEvaluation,
    propose_offline_improvement,
    qualify_improvement_for_canary,
)


TRACE_A = "a" * 64
TRACE_B = "b" * 64
TENANT = "tenant://YS_TR"


def _evaluation(
    evaluation_id="eval://1",
    trace_id=TRACE_A,
    *,
    ambiguous=False,
    score=0.61,
    failures=("wrong_tool_choice",),
    tenant=TENANT,
):
    return OfflineTrajectoryEvaluation(
        evaluation_id=evaluation_id,
        trace_id=trace_id,
        tenant_id=tenant,
        environment=EvaluationEnvironment.REDACTED_PRODUCTION_EVIDENCE,
        evaluator_ref="evaluator://jarvis-offline-v1",
        outcome_score=score,
        failure_classes=failures,
        evidence_refs=(f"evidence://trajectory/{evaluation_id}",),
        ambiguous_side_effect_observed=ambiguous,
    )


def test_failed_trajectory_creates_reviewable_candidate_but_never_activates_itself():
    candidate = propose_offline_improvement(
        evaluations=(_evaluation(),),
        target=ImprovementTarget.TOOL_SELECTION,
        revision_artifact_ref="revision://jarvis/tool-policy/v2",
    )

    assert candidate.status is ImprovementStatus.CANDIDATE
    assert candidate.jarvisbench_required is True
    assert candidate.independent_review_required is True
    assert candidate.human_approval_required is True
    assert candidate.automatic_self_modification_allowed is False
    assert candidate.production_activation_allowed is False
    assert candidate.canary_activation_allowed is False


def test_ambiguous_side_effect_can_only_propose_verifier_or_workflow_change():
    evidence = (_evaluation(ambiguous=True, failures=("ambiguous_side_effect",)),)

    with pytest.raises(ValueError, match="ambiguous_side_effect_improvement_must_target_verifier_or_workflow"):
        propose_offline_improvement(
            evaluations=evidence,
            target=ImprovementTarget.PROMPT_POLICY,
            revision_artifact_ref="revision://unsafe-prompt-change",
        )

    verifier = propose_offline_improvement(
        evaluations=evidence,
        target=ImprovementTarget.EFFECT_VERIFIER,
        revision_artifact_ref="revision://inventory/readback-verifier/v2",
    )
    assert verifier.target is ImprovementTarget.EFFECT_VERIFIER


def test_cross_tenant_trajectory_learning_is_forbidden():
    with pytest.raises(ValueError, match="trajectory_improvement_cross_tenant_evidence_forbidden"):
        propose_offline_improvement(
            evaluations=(
                _evaluation(evaluation_id="eval://a", trace_id=TRACE_A),
                _evaluation(
                    evaluation_id="eval://b",
                    trace_id=TRACE_B,
                    tenant="tenant://OTHER",
                ),
            ),
            target=ImprovementTarget.WORKFLOW_GRAPH,
            revision_artifact_ref="revision://workflow/v2",
        )


def test_perfect_trajectory_without_failure_signal_does_not_create_fake_learning_work():
    with pytest.raises(ValueError, match="trajectory_evaluation_has_no_improvement_signal"):
        _evaluation(score=1.0, failures=())


def test_candidate_needs_benchmark_safety_review_human_approval_and_canary_env():
    candidate = propose_offline_improvement(
        evaluations=(_evaluation(),),
        target=ImprovementTarget.TOOL_SELECTION,
        revision_artifact_ref="revision://jarvis/tool-policy/v2",
    )

    blocked = qualify_improvement_for_canary(
        candidate=candidate,
        validation=ImprovementValidationEvidence(candidate_id=candidate.candidate_id),
    )
    assert blocked.status is ImprovementStatus.BLOCKED
    assert blocked.canary_activation_allowed is False
    assert blocked.production_activation_allowed is False
    assert "trajectory_improvement_jarvisbench_not_passed" in blocked.blockers
    assert "trajectory_improvement_human_approval_missing" in blocked.blockers

    approved = qualify_improvement_for_canary(
        candidate=candidate,
        validation=ImprovementValidationEvidence(
            candidate_id=candidate.candidate_id,
            jarvisbench_evidence_ref="benchmark://jarvis/tool-policy-v2",
            jarvisbench_passed=True,
            minimum_sample_count=30,
            no_safety_regression=True,
            independent_review_ref="review://independent/provider-council/1",
            human_approval_ref="approval://jarvis-release/1",
            canary_environment_ref="canary://eay-ai-core/staging",
        ),
    )
    assert approved.status is ImprovementStatus.APPROVED_FOR_CANARY
    assert approved.canary_activation_allowed is True
    assert approved.production_activation_allowed is False
    assert approved.automatic_self_modification_allowed is False


def test_raw_or_secret_trajectory_content_is_rejected():
    with pytest.raises(ValueError, match="trajectory_evaluation_cannot_retain_raw_or_secret_content"):
        OfflineTrajectoryEvaluation(
            evaluation_id="eval://unsafe",
            trace_id=TRACE_A,
            tenant_id=TENANT,
            environment=EvaluationEnvironment.STAGING,
            evaluator_ref="evaluator://offline",
            outcome_score=0.5,
            failure_classes=("failure",),
            evidence_refs=("evidence://safe-ref",),
            raw_trace_content_retained=True,
        )
