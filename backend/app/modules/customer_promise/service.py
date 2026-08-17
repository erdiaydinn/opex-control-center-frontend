from __future__ import annotations

import hashlib
import json
import math
from datetime import UTC, datetime

from .models import (
    CauseAssertion,
    CauseAssertionType,
    CustomerPromiseVersion,
    DeliveryActualSnapshot,
    DeliveryOutcomeStatus,
    FINANCIAL_RECOVERY_KINDS,
    InstructionCompliance,
    OrderExperienceSnapshot,
    PromiseDeviation,
    PromiseOutcome,
    RecoveryDecision,
    RecoveryDecisionType,
    RecoveryRequest,
)


class CustomerPromiseError(ValueError):
    pass


def _canonical_fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def validate_next_promise_version(
    previous: CustomerPromiseVersion,
    current: CustomerPromiseVersion,
) -> CustomerPromiseVersion:
    """Validate append-only promise evolution without mutating prior customer truth."""
    if previous.tenant_id != current.tenant_id:
        raise CustomerPromiseError("promise revision cannot cross tenant boundary")
    if previous.promise_id != current.promise_id:
        raise CustomerPromiseError("promise revision must preserve promise identity")
    if previous.external_order_ref != current.external_order_ref:
        raise CustomerPromiseError("promise revision must preserve external order reference")
    if current.version != previous.version + 1 or current.supersedes_version != previous.version:
        raise CustomerPromiseError("promise revision must advance exactly one immutable version")
    if current.committed_at < previous.committed_at:
        raise CustomerPromiseError("promise revision committed_at cannot move backwards")
    return current


def evaluate_promise(
    promise: CustomerPromiseVersion,
    actual: DeliveryActualSnapshot,
    *,
    evaluated_at: datetime | None = None,
) -> PromiseDeviation:
    """Compare customer-visible commitment to observed truth deterministically.

    The evaluator does not infer root cause and does not execute remediation.
    Positive timing delta means late minutes; negative means early minutes.
    """
    if promise.tenant_id != actual.tenant_id:
        raise CustomerPromiseError("promise evaluation cannot cross tenant boundary")
    if promise.external_order_ref != actual.external_order_ref:
        raise CustomerPromiseError("promise and actual outcome must reference the same order")
    if actual.observed_at < promise.committed_at:
        raise CustomerPromiseError("actual observation predates the selected promise version")
    if actual.delivered_at is not None and actual.delivered_at < promise.committed_at:
        raise CustomerPromiseError("delivery predates the selected promise version")

    breach_types: list[str] = []
    timing_delta: int | None = None

    if actual.status is DeliveryOutcomeStatus.DELIVERED:
        delivered_at = actual.delivered_at
        assert delivered_at is not None
        if delivered_at < promise.delivery_window.starts_at:
            timing_delta = -math.ceil(
                (promise.delivery_window.starts_at - delivered_at).total_seconds() / 60
            )
            outcome = PromiseOutcome.EARLY
            breach_types.append("early_delivery")
        elif delivered_at <= promise.delivery_window.ends_at:
            timing_delta = 0
            outcome = PromiseOutcome.ON_TIME
        else:
            timing_delta = math.ceil(
                (delivered_at - promise.delivery_window.ends_at).total_seconds() / 60
            )
            outcome = PromiseOutcome.LATE
            breach_types.append("late_delivery")
    elif actual.status is DeliveryOutcomeStatus.FAILED:
        outcome = PromiseOutcome.FAILED
        breach_types.append("delivery_failed")
    elif actual.status is DeliveryOutcomeStatus.CANCELLED:
        outcome = PromiseOutcome.CANCELLED
        breach_types.append("delivery_cancelled")
    else:
        outcome = PromiseOutcome.IN_PROGRESS

    fee_delta: int | None = None
    if promise.customer_fee is not None and actual.actual_fee is not None:
        if promise.customer_fee.currency != actual.actual_fee.currency:
            raise CustomerPromiseError("promise and actual fee currencies must match before comparison")
        fee_delta = actual.actual_fee.minor_units - promise.customer_fee.minor_units
        if fee_delta != 0:
            breach_types.append("fee_mismatch")

    if promise.instruction_reference is None:
        if actual.instruction_compliance is InstructionCompliance.BREACHED:
            raise CustomerPromiseError("instruction breach cannot be asserted when no instruction was promised")
        instruction_breach: bool | None = False if actual.instruction_compliance is InstructionCompliance.NOT_APPLICABLE else None
    else:
        if actual.instruction_compliance is InstructionCompliance.NOT_APPLICABLE:
            raise CustomerPromiseError("promised delivery instruction cannot be marked not applicable")
        if actual.instruction_compliance is InstructionCompliance.BREACHED:
            instruction_breach = True
            breach_types.append("instruction_breach")
        elif actual.instruction_compliance is InstructionCompliance.MET:
            instruction_breach = False
        else:
            instruction_breach = None

    evaluation_time = evaluated_at or datetime.now(UTC)
    fingerprint_payload: dict[str, object] = {
        "tenant_id": promise.tenant_id,
        "promise_id": promise.promise_id,
        "promise_version": promise.version,
        "external_order_ref": promise.external_order_ref,
        "outcome": outcome.value,
        "timing_delta_minutes": timing_delta,
        "fee_delta_minor_units": fee_delta,
        "instruction_breach": instruction_breach,
        "breach_types": sorted(set(breach_types)),
        "source_system": actual.source_system,
        "source_record_ref": actual.source_record_ref,
    }

    return PromiseDeviation(
        tenant_id=promise.tenant_id,
        promise_id=promise.promise_id,
        promise_version=promise.version,
        external_order_ref=promise.external_order_ref,
        outcome=outcome,
        timing_delta_minutes=timing_delta,
        fee_delta_minor_units=fee_delta,
        instruction_breach=instruction_breach,
        breach_types=tuple(sorted(set(breach_types))),
        evaluated_at=evaluation_time,
        fingerprint=_canonical_fingerprint(fingerprint_payload),
    )


def cause_is_verified(assertion: CauseAssertion) -> bool:
    """Only evidence-bound assertions may be presented as verified root-cause facts."""
    return assertion.assertion_type is CauseAssertionType.VERIFIED_EVIDENCE


def authorize_recovery_execution(
    request: RecoveryRequest,
    decision: RecoveryDecision | None,
) -> bool:
    """Fail closed before any downstream recovery executor is invoked.

    Item 6 records proposals and approvals only. Item 7 may later orchestrate policy,
    but it may not weaken this financial approval boundary.
    """
    if decision is None:
        if request.requires_human_approval or request.kind in FINANCIAL_RECOVERY_KINDS:
            raise CustomerPromiseError("recovery execution requires an approval decision")
        return True
    if request.tenant_id != decision.tenant_id:
        raise CustomerPromiseError("recovery decision cannot cross tenant boundary")
    if request.recovery_id != decision.recovery_id:
        raise CustomerPromiseError("recovery decision does not match request")
    if decision.decision is not RecoveryDecisionType.APPROVED:
        raise CustomerPromiseError("rejected recovery cannot execute")
    return True


def build_order_experience_snapshot(
    promise: CustomerPromiseVersion,
    actual: DeliveryActualSnapshot,
    deviation: PromiseDeviation,
    *,
    causes: tuple[CauseAssertion, ...] = (),
    recovery_requests: tuple[RecoveryRequest, ...] = (),
    recovery_decisions: tuple[RecoveryDecision, ...] = (),
) -> OrderExperienceSnapshot:
    """Build one-order customer-experience truth without creating a CRM customer profile."""
    tenant_id = promise.tenant_id
    order_ref = promise.external_order_ref
    if actual.tenant_id != tenant_id or actual.external_order_ref != order_ref:
        raise CustomerPromiseError("snapshot actual outcome scope mismatch")
    if deviation.tenant_id != tenant_id or deviation.external_order_ref != order_ref:
        raise CustomerPromiseError("snapshot deviation scope mismatch")
    if deviation.promise_id != promise.promise_id or deviation.promise_version != promise.version:
        raise CustomerPromiseError("snapshot deviation does not reference selected promise version")

    for assertion in causes:
        if assertion.tenant_id != tenant_id or assertion.external_order_ref != order_ref:
            raise CustomerPromiseError("snapshot cause assertion scope mismatch")
        if assertion.deviation_fingerprint != deviation.fingerprint:
            raise CustomerPromiseError("snapshot cause assertion references another deviation")
    for recovery in recovery_requests:
        if recovery.tenant_id != tenant_id or recovery.external_order_ref != order_ref:
            raise CustomerPromiseError("snapshot recovery scope mismatch")
        if recovery.deviation_fingerprint != deviation.fingerprint:
            raise CustomerPromiseError("snapshot recovery references another deviation")

    recovery_ids = {item.recovery_id for item in recovery_requests}
    for decision in recovery_decisions:
        if decision.tenant_id != tenant_id:
            raise CustomerPromiseError("snapshot recovery decision scope mismatch")
        if decision.recovery_id not in recovery_ids:
            raise CustomerPromiseError("snapshot decision references an unknown recovery request")

    return OrderExperienceSnapshot(
        tenant_id=tenant_id,
        external_order_ref=order_ref,
        promise=promise,
        actual=actual,
        deviation=deviation,
        causes=causes,
        recovery_requests=recovery_requests,
        recovery_decisions=recovery_decisions,
    )
