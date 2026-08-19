from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from app.decision_calibration_ledger import (
    CalibrationEvidenceClass,
    CalibrationSnapshotStatus,
    append_calibration_approval,
    append_calibration_candidate,
    build_active_calibration_snapshot,
    build_calibration_approval_record,
    build_calibration_candidate_record,
    new_decision_calibration_ledger,
)
from app.intelligence_supremacy import (
    LearningCalibrationApproval,
    build_learning_calibration_candidate,
)
from app.outcome_learning import AttributionStrength, DecisionOutcomeAssessment

T0 = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
TENANT = "tenant://ys-tr"
DECISION_TYPE = "ops.demand"
TASK_FAMILY = "task-family://ops-demand"


def _candidate(index: int, multiplier: float, recorded_at=None, tenant=TENANT):
    assessment = DecisionOutcomeAssessment(
        decision_id=f"decision://{index}",
        tenant_id=tenant,
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
        recorded_at=recorded_at or T0,
    )


def _record(index, multiplier, evidence_class=CalibrationEvidenceClass.REAL_COMPANY_OUTCOME, observed_at=None, recorded_at=None):
    candidate = _candidate(index, multiplier, recorded_at=recorded_at or T0)
    return build_calibration_candidate_record(
        record_id=f"record://{index}",
        candidate=candidate,
        task_family=TASK_FAMILY,
        evidence_class=evidence_class,
        attribution_strength=AttributionStrength.NONE,
        observed_at=observed_at or T0,
        recorded_at=recorded_at or T0,
        evidence_refs=(f"evidence://field-{index}",),
    )


def _approve(ledger, record, *, approved_at=None, recorded_at=None):
    approved_at = approved_at or (T0 + timedelta(minutes=1))
    approval = LearningCalibrationApproval(
        candidate_fingerprint=record.candidate.fingerprint,
        reviewer_ref="reviewer://evidence-colony",
        approval_evidence_ref=f"evidence://approval-{record.record_id}",
        approved_at=approved_at,
    )
    approval_record = build_calibration_approval_record(
        approval_id=f"approval://{record.record_id}",
        tenant_id=TENANT,
        approval=approval,
        recorded_at=recorded_at or approved_at,
    )
    return append_calibration_approval(ledger=ledger, record=approval_record)


def _ledger_with_records(records):
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    for record in records:
        ledger = append_calibration_candidate(ledger=ledger, record=record)
    return ledger


def test_three_reviewed_field_samples_activate_robust_median_calibration():
    records = (_record(1, 0.70), _record(2, 0.80), _record(3, 0.90))
    ledger = _ledger_with_records(records)
    for record in records:
        ledger = _approve(ledger, record)

    snapshot = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
    )

    assert snapshot.status is CalibrationSnapshotStatus.ACTIVE
    assert snapshot.confidence_multiplier == 0.80
    assert snapshot.eligible_sample_count == 3
    assert len(snapshot.candidate_fingerprints) == 3
    assert snapshot.model_weights_mutated is False
    assert snapshot.business_policy_mutated is False
    assert snapshot.execution_authority_granted is False


def test_synthetic_repository_and_simulation_records_never_vote_in_production_snapshot():
    records = (
        _record(1, 0.60, CalibrationEvidenceClass.SYNTHETIC),
        _record(2, 0.70, CalibrationEvidenceClass.REPOSITORY),
        _record(3, 0.80, CalibrationEvidenceClass.SIMULATION),
    )
    ledger = _ledger_with_records(records)
    for record in records:
        ledger = _approve(ledger, record)

    snapshot = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
    )

    assert snapshot.status is CalibrationSnapshotStatus.INSUFFICIENT
    assert snapshot.confidence_multiplier == 1.0
    assert snapshot.eligible_sample_count == 0
    assert snapshot.candidate_fingerprints == ()


def test_future_recorded_approval_does_not_leak_into_historical_calibration():
    records = (_record(1, 0.75), _record(2, 0.80), _record(3, 0.85))
    ledger = _ledger_with_records(records)
    ledger = _approve(ledger, records[0])
    ledger = _approve(ledger, records[1])
    future = T0 + timedelta(hours=3)
    ledger = _approve(ledger, records[2], approved_at=future, recorded_at=future)

    historical = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
    )
    later = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=4),
    )

    assert historical.status is CalibrationSnapshotStatus.INSUFFICIENT
    assert historical.eligible_sample_count == 2
    assert later.status is CalibrationSnapshotStatus.ACTIVE
    assert later.eligible_sample_count == 3


def test_strongly_conflicting_field_calibrations_fail_closed_instead_of_averaging():
    records = (_record(1, 0.55), _record(2, 0.80), _record(3, 1.05))
    ledger = _ledger_with_records(records)
    for record in records:
        ledger = _approve(ledger, record)

    snapshot = build_active_calibration_snapshot(
        ledger=ledger,
        decision_type=DECISION_TYPE,
        task_family=TASK_FAMILY,
        as_of=T0 + timedelta(hours=1),
        maximum_multiplier_spread=0.30,
    )

    assert snapshot.status is CalibrationSnapshotStatus.CONFLICT
    assert snapshot.confidence_multiplier == 1.0
    assert "active_calibration_field_evidence_conflict" in snapshot.blockers


def test_cross_tenant_candidate_append_is_rejected():
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    candidate = _candidate(1, 0.8, tenant="tenant://other")
    record = build_calibration_candidate_record(
        record_id="record://other",
        candidate=candidate,
        task_family=TASK_FAMILY,
        evidence_class=CalibrationEvidenceClass.REAL_COMPANY_OUTCOME,
        attribution_strength=AttributionStrength.NONE,
        observed_at=T0,
        recorded_at=T0,
        evidence_refs=("evidence://other",),
    )
    with pytest.raises(ValueError, match="calibration_ledger_cross_tenant_candidate"):
        append_calibration_candidate(ledger=ledger, record=record)


def test_candidate_tamper_is_detected_before_append():
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    record = _record(1, 0.8)
    tampered_candidate = record.candidate.model_copy(
        update={"proposed_confidence_multiplier": 1.05}
    )
    tampered_record = record.model_copy(update={"candidate": tampered_candidate})

    with pytest.raises(ValidationError, match="learning_calibration_candidate_fingerprint_mismatch"):
        append_calibration_candidate(ledger=ledger, record=tampered_record)


def test_exact_duplicate_candidate_and_approval_append_are_idempotent():
    record = _record(1, 0.8)
    ledger = new_decision_calibration_ledger(tenant_id=TENANT)
    once = append_calibration_candidate(ledger=ledger, record=record)
    twice = append_calibration_candidate(ledger=once, record=record)
    assert twice.fingerprint == once.fingerprint

    approval = LearningCalibrationApproval(
        candidate_fingerprint=record.candidate.fingerprint,
        reviewer_ref="reviewer://evidence-colony",
        approval_evidence_ref="evidence://approval",
        approved_at=T0 + timedelta(minutes=1),
    )
    approval_record = build_calibration_approval_record(
        approval_id="approval://1",
        tenant_id=TENANT,
        approval=approval,
        recorded_at=T0 + timedelta(minutes=1),
    )
    approved_once = append_calibration_approval(ledger=once, record=approval_record)
    approved_twice = append_calibration_approval(ledger=approved_once, record=approval_record)
    assert approved_twice.fingerprint == approved_once.fingerprint
