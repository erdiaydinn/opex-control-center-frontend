"""Decision-to-outcome learning ledger for Jarvis.

Jarvis should remember whether its recommendations and quantitative expectations
were borne out. This module links a decision, any governed action receipt, and
later measured outcomes. It computes forecast error and calibration evidence
but never self-modifies production weights, policy, tool permissions, or
causal claims. Counterfactual evidence may strengthen attribution only after
the governed action effect itself has been verified.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

OUTCOME_LEARNING_CONTRACT = "eay-decision-outcome-learning-v1"


class AttributionStrength(str, Enum):
    NONE = "none"
    ASSOCIATION = "association"
    COUNTERFACTUAL_SUPPORTED = "counterfactual_supported"


class ExpectedMetricOutcome(BaseModel):
    metric_key: str = Field(min_length=1)
    baseline_value: float
    expected_value: float
    unit: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)


class DecisionLearningRecord(BaseModel):
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    decided_at: datetime
    decision_type: str = Field(min_length=1)
    recommendation_ref: str = Field(min_length=1)
    expected_outcomes: tuple[ExpectedMetricOutcome, ...] = Field(min_length=1)
    decision_evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def decision_time_is_aware(self) -> "DecisionLearningRecord":
        if self.decided_at.tzinfo is None or self.decided_at.utcoffset() is None:
            raise ValueError("outcome_learning_decision_requires_timezone")
        return self


class GovernedActionReceipt(BaseModel):
    action_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    executed_at: datetime
    capability_ref: str = Field(min_length=1)
    effect_verified: bool
    approval_ref: str | None = None
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def action_time_is_aware(self) -> "GovernedActionReceipt":
        if self.executed_at.tzinfo is None or self.executed_at.utcoffset() is None:
            raise ValueError("outcome_learning_action_requires_timezone")
        return self


class ObservedMetricOutcome(BaseModel):
    metric_key: str = Field(min_length=1)
    observed_value: float
    unit: str = Field(min_length=1)
    observed_at: datetime
    governed_truth_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def outcome_time_is_aware(self) -> "ObservedMetricOutcome":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("outcome_learning_observation_requires_timezone")
        return self


class MetricLearningResult(BaseModel):
    metric_key: str
    baseline_value: float
    expected_value: float
    observed_value: float
    expected_delta: float
    observed_delta: float
    absolute_error: float
    relative_error_pct: float | None
    direction_correct: bool
    original_confidence: float


class DecisionOutcomeAssessment(BaseModel):
    contract: str = OUTCOME_LEARNING_CONTRACT
    decision_id: str
    tenant_id: str
    metric_results: tuple[MetricLearningResult, ...]
    mean_absolute_error: float | None
    direction_accuracy: float | None = Field(default=None, ge=0.0, le=1.0)
    attribution_strength: AttributionStrength
    counterfactual_evidence_ref: str | None = None
    learning_evidence_refs: tuple[str, ...]
    suggested_confidence_multiplier: float = Field(ge=0.25, le=1.25)
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    causal_claim_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def learning_never_self_promotes(self) -> "DecisionOutcomeAssessment":
        if self.automatic_model_weight_update_allowed or self.automatic_policy_update_allowed:
            raise ValueError("outcome_learning_cannot_self_modify_production")
        if self.causal_claim_allowed and self.attribution_strength is not AttributionStrength.COUNTERFACTUAL_SUPPORTED:
            raise ValueError("outcome_learning_causal_claim_requires_counterfactual_support")
        return self


def assess_decision_outcome(
    *,
    decision: DecisionLearningRecord,
    outcomes: list[ObservedMetricOutcome],
    action: GovernedActionReceipt | None = None,
    counterfactual_evidence_ref: str | None = None,
) -> DecisionOutcomeAssessment:
    blockers: list[str] = []
    if action is not None:
        if action.decision_id != decision.decision_id or action.tenant_id != decision.tenant_id:
            raise ValueError("outcome_learning_action_identity_mismatch")
        if action.executed_at < decision.decided_at:
            raise ValueError("outcome_learning_action_precedes_decision")
        if not action.effect_verified:
            blockers.append("outcome_learning_action_effect_unverified")

    observed_map = {item.metric_key: item for item in outcomes}
    if len(observed_map) != len(outcomes):
        raise ValueError("outcome_learning_duplicate_metric_observation")

    results: list[MetricLearningResult] = []
    evidence_refs: list[str] = list(decision.decision_evidence_refs)
    if action is not None:
        evidence_refs.extend(action.evidence_refs)

    for expected in decision.expected_outcomes:
        observed = observed_map.get(expected.metric_key)
        if observed is None:
            blockers.append(f"outcome_learning_metric_missing:{expected.metric_key}")
            continue
        if observed.observed_at < decision.decided_at:
            raise ValueError("outcome_learning_observation_precedes_decision")
        if observed.unit != expected.unit:
            blockers.append(f"outcome_learning_metric_unit_mismatch:{expected.metric_key}")
            continue
        expected_delta = expected.expected_value - expected.baseline_value
        observed_delta = observed.observed_value - expected.baseline_value
        absolute_error = abs(expected.expected_value - observed.observed_value)
        relative_error_pct = None
        if expected.expected_value != 0:
            relative_error_pct = absolute_error / abs(expected.expected_value) * 100.0
        direction_correct = (
            (expected_delta == 0 and observed_delta == 0)
            or (expected_delta > 0 and observed_delta > 0)
            or (expected_delta < 0 and observed_delta < 0)
        )
        results.append(
            MetricLearningResult(
                metric_key=expected.metric_key,
                baseline_value=expected.baseline_value,
                expected_value=expected.expected_value,
                observed_value=observed.observed_value,
                expected_delta=round(expected_delta, 6),
                observed_delta=round(observed_delta, 6),
                absolute_error=round(absolute_error, 6),
                relative_error_pct=round(relative_error_pct, 6) if relative_error_pct is not None else None,
                direction_correct=direction_correct,
                original_confidence=expected.confidence,
            )
        )
        evidence_refs.extend(expected.evidence_refs)
        evidence_refs.extend(observed.evidence_refs)
        evidence_refs.append(observed.governed_truth_ref)

    if action is None:
        attribution = AttributionStrength.NONE
    elif not action.effect_verified:
        attribution = AttributionStrength.NONE
        if counterfactual_evidence_ref:
            blockers.append("outcome_learning_counterfactual_ignored_until_action_effect_verified")
    elif counterfactual_evidence_ref:
        attribution = AttributionStrength.COUNTERFACTUAL_SUPPORTED
        evidence_refs.append(counterfactual_evidence_ref)
    else:
        attribution = AttributionStrength.ASSOCIATION
        blockers.append("outcome_learning_counterfactual_missing_for_attribution")

    mean_absolute_error = (
        round(sum(item.absolute_error for item in results) / len(results), 6) if results else None
    )
    direction_accuracy = (
        round(sum(1 for item in results if item.direction_correct) / len(results), 6) if results else None
    )

    if not results:
        multiplier = 0.50
    else:
        normalized_errors = [
            item.relative_error_pct / 100.0
            for item in results
            if item.relative_error_pct is not None
        ]
        mean_relative_error = sum(normalized_errors) / len(normalized_errors) if normalized_errors else 0.0
        multiplier = max(0.50, min(1.05, 1.0 - 0.50 * mean_relative_error))
        if direction_accuracy is not None and direction_accuracy < 0.5:
            multiplier = min(multiplier, 0.70)

    return DecisionOutcomeAssessment(
        decision_id=decision.decision_id,
        tenant_id=decision.tenant_id,
        metric_results=tuple(results),
        mean_absolute_error=mean_absolute_error,
        direction_accuracy=direction_accuracy,
        attribution_strength=attribution,
        counterfactual_evidence_ref=(
            counterfactual_evidence_ref
            if attribution is AttributionStrength.COUNTERFACTUAL_SUPPORTED
            else None
        ),
        learning_evidence_refs=tuple(dict.fromkeys(evidence_refs)),
        suggested_confidence_multiplier=round(multiplier, 6),
        blockers=tuple(dict.fromkeys(blockers)),
    )
