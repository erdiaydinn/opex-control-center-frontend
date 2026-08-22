from datetime import datetime, timedelta, timezone

import pytest

from app.outcome_learning import (
    AttributionStrength,
    DecisionLearningRecord,
    ExpectedMetricOutcome,
    GovernedActionReceipt,
    ObservedMetricOutcome,
    assess_decision_outcome,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 4, 30, tzinfo=UTC)


def _decision():
    return DecisionLearningRecord(
        decision_id="decision:rain-demand",
        tenant_id="warehouse:fulya",
        decided_at=NOW,
        decision_type="capacity_preparation",
        recommendation_ref="decision://prepare-capacity",
        expected_outcomes=(
            ExpectedMetricOutcome(
                metric_key="orders",
                baseline_value=1000,
                expected_value=1180,
                unit="orders",
                confidence=0.80,
                evidence_refs=("evidence://forecast",),
            ),
        ),
        decision_evidence_refs=("evidence://weather",),
    )


def _outcome(value=1110):
    return ObservedMetricOutcome(
        metric_key="orders",
        observed_value=value,
        unit="orders",
        observed_at=NOW + timedelta(hours=8),
        governed_truth_ref="ops://orders-live",
        evidence_refs=("evidence://orders-live",),
    )


def _action(effect_verified=True):
    return GovernedActionReceipt(
        action_id="action:capacity",
        decision_id="decision:rain-demand",
        tenant_id="warehouse:fulya",
        executed_at=NOW + timedelta(minutes=10),
        capability_ref="capability://capacity.prepare",
        effect_verified=effect_verified,
        approval_ref="approval://ops",
        evidence_refs=("evidence://action",),
    )


def test_learning_records_forecast_error_without_self_modifying_production():
    assessment = assess_decision_outcome(
        decision=_decision(),
        outcomes=[_outcome()],
        action=_action(),
        counterfactual_evidence_ref="counterfactual://matched-control",
    )

    result = assessment.metric_results[0]
    assert result.expected_delta == 180
    assert result.observed_delta == 110
    assert result.absolute_error == 70
    assert result.direction_correct is True
    assert assessment.attribution_strength is AttributionStrength.COUNTERFACTUAL_SUPPORTED
    assert assessment.automatic_model_weight_update_allowed is False
    assert assessment.automatic_policy_update_allowed is False
    assert assessment.causal_claim_allowed is False


def test_action_without_counterfactual_is_association_not_causal_attribution():
    assessment = assess_decision_outcome(
        decision=_decision(),
        outcomes=[_outcome()],
        action=_action(),
    )

    assert assessment.attribution_strength is AttributionStrength.ASSOCIATION
    assert "outcome_learning_counterfactual_missing_for_attribution" in assessment.blockers
    assert assessment.causal_claim_allowed is False


def test_unverified_action_cannot_receive_counterfactual_supported_attribution():
    assessment = assess_decision_outcome(
        decision=_decision(),
        outcomes=[_outcome()],
        action=_action(effect_verified=False),
        counterfactual_evidence_ref="counterfactual://matched-control",
    )

    assert assessment.attribution_strength is AttributionStrength.NONE
    assert assessment.counterfactual_evidence_ref is None
    assert "outcome_learning_action_effect_unverified" in assessment.blockers
    assert "outcome_learning_counterfactual_ignored_until_action_effect_verified" in assessment.blockers


def test_wrong_direction_reduces_suggested_confidence_multiplier():
    assessment = assess_decision_outcome(
        decision=_decision(),
        outcomes=[_outcome(value=900)],
    )

    assert assessment.metric_results[0].direction_correct is False
    assert assessment.direction_accuracy == 0.0
    assert assessment.suggested_confidence_multiplier <= 0.70


def test_missing_metric_is_explicit_blocker_not_silent_learning():
    assessment = assess_decision_outcome(
        decision=_decision(),
        outcomes=[],
    )

    assert assessment.metric_results == ()
    assert "outcome_learning_metric_missing:orders" in assessment.blockers


def test_cross_tenant_or_wrong_decision_action_is_rejected():
    with pytest.raises(ValueError, match="outcome_learning_action_identity_mismatch"):
        assess_decision_outcome(
            decision=_decision(),
            outcomes=[_outcome()],
            action=_action().model_copy(update={"tenant_id": "warehouse:besiktas"}),
        )
