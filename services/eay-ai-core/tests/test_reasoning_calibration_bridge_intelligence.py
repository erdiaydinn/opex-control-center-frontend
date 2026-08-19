from datetime import datetime, timedelta, timezone

import pytest

from app.decision_calibration_ledger import (
    CalibrationEvidenceClass,
    append_calibration_approval,
    append_calibration_candidate,
    build_active_calibration_snapshot,
    build_calibration_approval_record,
    build_calibration_candidate_record,
    new_decision_calibration_ledger,
)
from app.decision_intelligence import DecisionReadiness, ExecutiveDecisionPacket
from app.intelligence_supremacy import (
    InformationGainPlan,
    LearningCalibrationApproval,
    ReasoningMode,
    ReasoningRisk,
    build_learning_calibration_candidate,
)
from app.outcome_learning import AttributionStrength, DecisionOutcomeAssessment
from app.reasoning_calibration_bridge import (
    build_reasoning_calibration_binding,
    select_reasoning_strength_with_calibration,
)

T0 = datetime(2026, 8, 19, 14, 0, tzinfo=timezone.utc)
TENANT = "tenant://ys-tr"
DECISION_TYPE = "ops.demand"
TASK_FAMILY = "task-family://ops-demand"


def _candidate(index: int, multiplier: float):
    assessment = DecisionOutcomeAssessment(
        decision_id=f"decision://{index}",
        tenant_id=TENANT,
        metric_results=(),
        mean_absolute_error=None,
        direction_accuracy=None,
        attribution_strength=AttributionStrength.NONE,
        learning_evidence_refs=(f"evidence://outcome-{index}",),
        suggested_confidence_multiplier=multiplier,
        blockers=("outcome_learning_metric_missing:orders",),
    )
    return build_learning_calibration_candidate(
        assessment=assessment,
        decision_type=DECISION_TYPE,
        recorded_at=T0,
    )


def _field_record(index: int, multiplier: float):
    candidate = _candidate(index, multiplier)
    return build_calibration_candidate_record(
        record_id=f"record://{index}",
        candidate=candidate,
        task_family=TASK_FAMILY,
        evidence_class=CalibrationEvidenceClass.REAL_COMPANY_OUTCOME,
        attribution_strength=AttributionStrength.NONE,
        observed_at=T0,
        recorded_at=T0,
        evidence_refs=(f"evidence://field-{index}",),
    )


def _approved_snapshot(multipliers, *, maximum_spread=0.30):
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    records = tuple(_field_record(index + 1, value) for index, value in enumerate(multipliers))
    for record in records:
        ledger = append_calibration_candidate(ledger=ledger, record=record)
    for index, record in enumerate(records):
        approval = LearningCalibrationApproval(
            candidate_fingerprint=record.candidate.fingerprint,
            reviewer_ref="reviewer://evidence-colony",
            approval_evidence_ref=f"evidence://approval-{index}",
            approved_at=T0 + timedelta(minutes=1),
        )
        approval_record = build_calibration_approval_record(
            approval_id=f"approval://{index}",
            tenant_id=TENANT,
            approval=approval,
            recorded_at=T0 + timedelta(minutes=1),
        )
        ledger = append_calibration_approval(ledger=ledger, record=approval_record)
    return build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
        maximum_multiplier_spread=maximum_spread,
    )


def _decision(*, blockers=(), readiness=DecisionReadiness.PREPARE):
    return ExecutiveDecisionPacket(
        decision_id="decision://current",
        readiness=readiness,
        confidence_cap=0.85,
        top_signal_ids=("signal://demand",),
        safe_prepare_action_ids=(),
        approval_gated_action_ids=(),
        automatic_external_execution_allowed=False,
        human_review_required=False,
        blockers=tuple(blockers),
        warnings=(),
        decision_truth_status=None,
        truth_requirement_id=None,
        firm_company_claim_authorized=True,
    )


def _info(unresolved=()):
    return InformationGainPlan(
        gap_ids=tuple(unresolved),
        ranked=(),
        selected_investigation_ids=(),
        total_selected_cost_units=0.0,
        unresolved_gap_ids=tuple(unresolved),
    )


def test_reviewed_field_calibration_can_strengthen_low_risk_reasoning_to_local_council():
    snapshot = _approved_snapshot((0.75, 0.80, 0.82))
    binding = build_reasoning_calibration_binding(
        snapshot=snapshot,
        tenant_id=TENANT,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=2),
    )
    plan = select_reasoning_strength_with_calibration(
        risk=ReasoningRisk.LOW,
        decision=_decision(),
        information_gain=_info(),
        binding=binding,
    )

    assert binding.effective_confidence_multiplier == 0.80
    assert binding.model_weights_mutated is False
    assert plan.mode is ReasoningMode.LOCAL_COUNCIL
    assert plan.frontier_escalation_candidate is True
    assert plan.paid_frontier_authority_granted is False
    assert plan.execution_authority_granted is False


def test_insufficient_history_is_neutral_and_does_not_force_extra_model_spend():
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    snapshot = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
    )
    binding = build_reasoning_calibration_binding(
        snapshot=snapshot,
        tenant_id=TENANT,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=2),
    )
    plan = select_reasoning_strength_with_calibration(
        risk=ReasoningRisk.LOW,
        decision=_decision(),
        information_gain=_info(),
        binding=binding,
    )

    assert binding.effective_confidence_multiplier == 1.0
    assert "reasoning_calibration_insufficient_history_neutral" in binding.blockers
    assert plan.mode is ReasoningMode.LOCAL_SINGLE
    assert plan.frontier_escalation_candidate is False


def test_conflicting_reviewed_field_history_strengthens_reasoning_instead_of_averaging():
    snapshot = _approved_snapshot((0.55, 0.80, 1.05), maximum_spread=0.30)
    binding = build_reasoning_calibration_binding(
        snapshot=snapshot,
        tenant_id=TENANT,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=2),
    )
    plan = select_reasoning_strength_with_calibration(
        risk=ReasoningRisk.MEDIUM,
        decision=_decision(),
        information_gain=_info(),
        binding=binding,
    )

    assert binding.effective_confidence_multiplier == 0.84
    assert "reasoning_calibration_conflict_requires_stronger_reasoning" in binding.blockers
    assert plan.mode is ReasoningMode.LOCAL_COUNCIL
    assert "active_calibration_field_evidence_conflict" in plan.blockers


def test_missing_live_company_truth_still_beats_calibration_and_forces_investigation_first():
    snapshot = _approved_snapshot((0.70, 0.75, 0.80))
    binding = build_reasoning_calibration_binding(
        snapshot=snapshot,
        tenant_id=TENANT,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=2),
    )
    decision = _decision(
        blockers=("live_company_truth_receipt_missing",),
        readiness=DecisionReadiness.HOLD,
    )
    plan = select_reasoning_strength_with_calibration(
        risk=ReasoningRisk.CRITICAL,
        decision=decision,
        information_gain=_info(("decision:live_company_truth_receipt_missing",)),
        binding=binding,
    )

    assert plan.mode is ReasoningMode.INVESTIGATE_FIRST
    assert plan.frontier_escalation_candidate is False
    assert "reasoning_cannot_substitute_for_missing_live_company_truth" in plan.blockers


def test_cross_tenant_and_future_snapshot_binding_fail_closed():
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    snapshot = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
    )

    with pytest.raises(ValueError, match="reasoning_calibration_cross_tenant_snapshot"):
        build_reasoning_calibration_binding(
            snapshot=snapshot,
            tenant_id="tenant://other",
            decision_type=DECISION_TYPE,
            task_family=TASK_FAMILY,
            as_of=T0 + timedelta(hours=2),
        )

    with pytest.raises(ValueError, match="reasoning_calibration_future_snapshot_forbidden"):
        build_reasoning_calibration_binding(
            snapshot=snapshot,
            tenant_id=TENANT,
            decision_type=DECISION_TYPE,
            task_family=TASK_FAMILY,
            as_of=T0 + timedelta(minutes=30),
        )
