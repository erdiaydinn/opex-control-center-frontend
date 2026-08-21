from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.modules.customer_promise.models import (
    CauseAssertion,
    CauseAssertionType,
    CustomerPromiseVersion,
    DeliveryActualSnapshot,
    DeliveryOutcomeStatus,
    InstructionCompliance,
    Money,
    PromiseOutcome,
    PromiseWindow,
    RecoveryDecision,
    RecoveryDecisionType,
    RecoveryKind,
    RecoveryRequest,
)
from app.modules.customer_promise.service import (
    CustomerPromiseError,
    authorize_recovery_execution,
    build_order_experience_snapshot,
    cause_is_verified,
    evaluate_promise,
    validate_next_promise_version,
)


BASE = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)
SHA_A = "a" * 64
SHA_B = "b" * 64


def promise(**overrides) -> CustomerPromiseVersion:
    values = {
        "tenant_id": "tenant-a",
        "promise_id": "promise-order-1",
        "external_order_ref": "order-1",
        "version": 1,
        "source_system": "oms",
        "source_record_ref": "oms-order-1-v1",
        "committed_at": BASE,
        "delivery_window": PromiseWindow(
            starts_at=BASE + timedelta(minutes=30),
            ends_at=BASE + timedelta(minutes=45),
        ),
        "service_level": "standard",
        "customer_fee": Money(minor_units=499, currency="TRY"),
        "instruction_reference": "oms://instructions/order-1",
        "instruction_fingerprint": SHA_A,
    }
    values.update(overrides)
    return CustomerPromiseVersion(**values)


def actual(**overrides) -> DeliveryActualSnapshot:
    values = {
        "tenant_id": "tenant-a",
        "external_order_ref": "order-1",
        "source_system": "delivery-platform",
        "source_record_ref": "delivery-order-1-final",
        "observed_at": BASE + timedelta(hours=1),
        "status": DeliveryOutcomeStatus.DELIVERED,
        "delivered_at": BASE + timedelta(minutes=40),
        "actual_fee": Money(minor_units=499, currency="TRY"),
        "instruction_compliance": InstructionCompliance.MET,
    }
    values.update(overrides)
    return DeliveryActualSnapshot(**values)


def test_promise_revision_is_append_only_and_linear() -> None:
    first = promise()
    second = promise(
        version=2,
        supersedes_version=1,
        source_record_ref="oms-order-1-v2",
        committed_at=BASE + timedelta(minutes=5),
        delivery_window=PromiseWindow(
            starts_at=BASE + timedelta(minutes=35),
            ends_at=BASE + timedelta(minutes=50),
        ),
    )
    assert validate_next_promise_version(first, second) == second

    skipped = promise(
        version=3,
        supersedes_version=2,
        source_record_ref="oms-order-1-v3",
        committed_at=BASE + timedelta(minutes=6),
    )
    with pytest.raises(CustomerPromiseError, match="advance exactly one"):
        validate_next_promise_version(first, skipped)


def test_promise_model_refuses_partial_instruction_reference() -> None:
    with pytest.raises(ValidationError, match="instruction reference and fingerprint"):
        promise(instruction_fingerprint=None)


def test_promise_contract_rejects_raw_customer_pii_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        promise(
            customer_name="Example Customer",
            phone="+900000000000",
            address="raw-address-must-stay-in-authoritative-system",
        )


def test_on_time_delivery_has_no_timing_breach() -> None:
    result = evaluate_promise(promise(), actual(), evaluated_at=BASE + timedelta(hours=2))
    assert result.outcome is PromiseOutcome.ON_TIME
    assert result.timing_delta_minutes == 0
    assert result.breach_types == ()
    assert result.instruction_breach is False
    assert result.fingerprint


def test_late_fee_and_instruction_breaches_are_deterministic() -> None:
    result = evaluate_promise(
        promise(),
        actual(
            delivered_at=BASE + timedelta(minutes=51, seconds=1),
            actual_fee=Money(minor_units=599, currency="TRY"),
            instruction_compliance=InstructionCompliance.BREACHED,
        ),
        evaluated_at=BASE + timedelta(hours=2),
    )
    assert result.outcome is PromiseOutcome.LATE
    assert result.timing_delta_minutes == 7
    assert result.fee_delta_minor_units == 100
    assert result.instruction_breach is True
    assert set(result.breach_types) == {"late_delivery", "fee_mismatch", "instruction_breach"}


def test_early_delivery_is_not_silently_treated_as_on_time() -> None:
    result = evaluate_promise(
        promise(),
        actual(delivered_at=BASE + timedelta(minutes=24, seconds=30)),
    )
    assert result.outcome is PromiseOutcome.EARLY
    assert result.timing_delta_minutes == -6
    assert "early_delivery" in result.breach_types


def test_failed_and_in_progress_orders_do_not_invent_delivery_timestamp() -> None:
    failed = evaluate_promise(
        promise(),
        actual(status=DeliveryOutcomeStatus.FAILED, delivered_at=None),
    )
    assert failed.outcome is PromiseOutcome.FAILED
    assert failed.timing_delta_minutes is None
    assert "delivery_failed" in failed.breach_types

    in_progress = evaluate_promise(
        promise(),
        actual(status=DeliveryOutcomeStatus.IN_PROGRESS, delivered_at=None),
    )
    assert in_progress.outcome is PromiseOutcome.IN_PROGRESS
    assert in_progress.timing_delta_minutes is None


def test_evaluation_fails_closed_on_tenant_order_or_currency_mismatch() -> None:
    with pytest.raises(CustomerPromiseError, match="tenant"):
        evaluate_promise(promise(), actual(tenant_id="tenant-b"))
    with pytest.raises(CustomerPromiseError, match="same order"):
        evaluate_promise(promise(), actual(external_order_ref="order-2"))
    with pytest.raises(CustomerPromiseError, match="currencies"):
        evaluate_promise(promise(), actual(actual_fee=Money(minor_units=499, currency="EUR")))


def test_historical_promise_version_must_precede_observed_delivery_truth() -> None:
    late_promise = promise(committed_at=BASE + timedelta(hours=2))
    with pytest.raises(CustomerPromiseError, match="predates"):
        evaluate_promise(late_promise, actual())


def test_root_cause_fact_requires_evidence_and_hypothesis_stays_hypothesis() -> None:
    deviation = evaluate_promise(promise(), actual(delivered_at=BASE + timedelta(minutes=55)))
    hypothesis = CauseAssertion(
        tenant_id="tenant-a",
        assertion_id="cause-1",
        external_order_ref="order-1",
        deviation_fingerprint=deviation.fingerprint,
        cause_code="possible_capacity_pressure",
        assertion_type=CauseAssertionType.HYPOTHESIS,
        confidence=0.71,
        asserted_by="jarvis",
        asserted_at=BASE + timedelta(hours=2),
    )
    assert cause_is_verified(hypothesis) is False

    with pytest.raises(ValidationError, match="requires evidence"):
        CauseAssertion(
            tenant_id="tenant-a",
            assertion_id="cause-2",
            external_order_ref="order-1",
            deviation_fingerprint=deviation.fingerprint,
            cause_code="verified_capacity_pressure",
            assertion_type=CauseAssertionType.VERIFIED_EVIDENCE,
            asserted_by="operator",
            asserted_at=BASE + timedelta(hours=2),
        )

    verified = CauseAssertion(
        tenant_id="tenant-a",
        assertion_id="cause-3",
        external_order_ref="order-1",
        deviation_fingerprint=deviation.fingerprint,
        cause_code="verified_capacity_pressure",
        assertion_type=CauseAssertionType.VERIFIED_EVIDENCE,
        evidence_reference="field://mission/verified-42",
        asserted_by="operator",
        asserted_at=BASE + timedelta(hours=2),
    )
    assert cause_is_verified(verified) is True


def test_financial_recovery_cannot_bypass_human_approval() -> None:
    deviation = evaluate_promise(promise(), actual(delivered_at=BASE + timedelta(minutes=55)))
    with pytest.raises(ValidationError, match="cannot bypass human approval"):
        RecoveryRequest(
            tenant_id="tenant-a",
            recovery_id="recovery-1",
            external_order_ref="order-1",
            deviation_fingerprint=deviation.fingerprint,
            kind=RecoveryKind.FEE_REFUND,
            amount=Money(minor_units=499, currency="TRY"),
            reason_code="late_delivery",
            proposed_by="operator",
            proposed_at=BASE + timedelta(hours=2),
            requires_human_approval=False,
        )


def test_recovery_execution_requires_matching_approved_decision() -> None:
    deviation = evaluate_promise(promise(), actual(delivered_at=BASE + timedelta(minutes=55)))
    request = RecoveryRequest(
        tenant_id="tenant-a",
        recovery_id="recovery-1",
        external_order_ref="order-1",
        deviation_fingerprint=deviation.fingerprint,
        kind=RecoveryKind.FEE_REFUND,
        amount=Money(minor_units=499, currency="TRY"),
        reason_code="late_delivery",
        proposed_by="operator",
        proposed_at=BASE + timedelta(hours=2),
    )
    with pytest.raises(CustomerPromiseError, match="approval"):
        authorize_recovery_execution(request, None)

    rejected = RecoveryDecision(
        tenant_id="tenant-a",
        decision_id="decision-1",
        recovery_id="recovery-1",
        decision=RecoveryDecisionType.REJECTED,
        decided_by="manager",
        decided_at=BASE + timedelta(hours=3),
        reason="not eligible",
    )
    with pytest.raises(CustomerPromiseError, match="rejected"):
        authorize_recovery_execution(request, rejected)

    approved = RecoveryDecision(
        tenant_id="tenant-a",
        decision_id="decision-2",
        recovery_id="recovery-1",
        decision=RecoveryDecisionType.APPROVED,
        decided_by="manager",
        decided_at=BASE + timedelta(hours=3),
    )
    assert authorize_recovery_execution(request, approved) is True

    cross_tenant = approved.model_copy(update={"tenant_id": "tenant-b"})
    with pytest.raises(CustomerPromiseError, match="tenant"):
        authorize_recovery_execution(request, cross_tenant)


def test_order_experience_snapshot_rejects_cross_scope_evidence() -> None:
    p = promise()
    a = actual(delivered_at=BASE + timedelta(minutes=55))
    deviation = evaluate_promise(p, a)
    valid_cause = CauseAssertion(
        tenant_id="tenant-a",
        assertion_id="cause-1",
        external_order_ref="order-1",
        deviation_fingerprint=deviation.fingerprint,
        cause_code="verified_flow_delay",
        assertion_type=CauseAssertionType.VERIFIED_EVIDENCE,
        evidence_reference="field://mission/verified-1",
        asserted_by="manager",
        asserted_at=BASE + timedelta(hours=2),
    )
    snapshot = build_order_experience_snapshot(p, a, deviation, causes=(valid_cause,))
    assert snapshot.external_order_ref == "order-1"
    assert snapshot.causes == (valid_cause,)

    wrong_order = valid_cause.model_copy(update={"external_order_ref": "order-2"})
    with pytest.raises(CustomerPromiseError, match="scope mismatch"):
        build_order_experience_snapshot(p, a, deviation, causes=(wrong_order,))
