from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictFrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Money(StrictFrozenModel):
    minor_units: int = Field(ge=0)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class PromiseWindow(StrictFrozenModel):
    starts_at: datetime
    ends_at: datetime

    @model_validator(mode="after")
    def validate_window(self) -> "PromiseWindow":
        if self.ends_at <= self.starts_at:
            raise ValueError("promise window end must be after start")
        return self


class CustomerPromiseVersion(StrictFrozenModel):
    """Immutable customer-visible commitment, not an OMS order record.

    Raw address, phone, customer name and free-text delivery instructions are
    intentionally absent. Sensitive instructions stay in their authoritative
    system and are referenced by opaque id + fingerprint only.
    """

    tenant_id: str = Field(min_length=1, max_length=120)
    promise_id: str = Field(min_length=3, max_length=160)
    external_order_ref: str = Field(min_length=1, max_length=200)
    version: int = Field(ge=1)
    supersedes_version: int | None = Field(default=None, ge=1)
    source_system: str = Field(min_length=1, max_length=120)
    source_record_ref: str = Field(min_length=1, max_length=240)
    committed_at: datetime
    delivery_window: PromiseWindow
    service_level: str = Field(min_length=1, max_length=120)
    customer_fee: Money | None = None
    instruction_reference: str | None = Field(default=None, max_length=240)
    instruction_fingerprint: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def validate_version_and_instruction_reference(self) -> "CustomerPromiseVersion":
        if self.version == 1 and self.supersedes_version is not None:
            raise ValueError("first promise version cannot supersede another version")
        if self.version > 1 and self.supersedes_version != self.version - 1:
            raise ValueError("promise versions must explicitly supersede the immediately prior version")
        if (self.instruction_reference is None) != (self.instruction_fingerprint is None):
            raise ValueError("instruction reference and fingerprint must be supplied together")
        return self


class DeliveryEventType(StrEnum):
    ORDER_ACCEPTED = "order_accepted"
    COURIER_ASSIGNED = "courier_assigned"
    PICKED_UP = "picked_up"
    ARRIVED = "arrived"
    DELIVERED = "delivered"
    FAILED_ATTEMPT = "failed_attempt"
    CANCELLED = "cancelled"
    CUSTOMER_CONTACTED = "customer_contacted"


class DeliveryEvent(StrictFrozenModel):
    """Append-only provenance event imported from an authoritative fulfillment source."""

    tenant_id: str = Field(min_length=1, max_length=120)
    event_id: str = Field(min_length=3, max_length=160)
    external_order_ref: str = Field(min_length=1, max_length=200)
    event_type: DeliveryEventType
    source_system: str = Field(min_length=1, max_length=120)
    source_event_ref: str = Field(min_length=1, max_length=240)
    occurred_at: datetime
    idempotency_key: str = Field(min_length=8, max_length=240)
    payload_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class DeliveryOutcomeStatus(StrEnum):
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"
    IN_PROGRESS = "in_progress"


class InstructionCompliance(StrEnum):
    UNKNOWN = "unknown"
    MET = "met"
    BREACHED = "breached"
    NOT_APPLICABLE = "not_applicable"


class DeliveryActualSnapshot(StrictFrozenModel):
    """Authoritative outcome observation referenced from OMS/delivery truth."""

    tenant_id: str = Field(min_length=1, max_length=120)
    external_order_ref: str = Field(min_length=1, max_length=200)
    source_system: str = Field(min_length=1, max_length=120)
    source_record_ref: str = Field(min_length=1, max_length=240)
    observed_at: datetime
    status: DeliveryOutcomeStatus
    delivered_at: datetime | None = None
    actual_fee: Money | None = None
    instruction_compliance: InstructionCompliance = InstructionCompliance.UNKNOWN

    @model_validator(mode="after")
    def validate_delivery_timestamp(self) -> "DeliveryActualSnapshot":
        if self.status is DeliveryOutcomeStatus.DELIVERED and self.delivered_at is None:
            raise ValueError("delivered outcome requires delivered_at")
        if self.status is not DeliveryOutcomeStatus.DELIVERED and self.delivered_at is not None:
            raise ValueError("non-delivered outcome cannot carry delivered_at")
        return self


class PromiseOutcome(StrEnum):
    ON_TIME = "on_time"
    EARLY = "early"
    LATE = "late"
    FAILED = "failed"
    CANCELLED = "cancelled"
    IN_PROGRESS = "in_progress"


class PromiseDeviation(StrictFrozenModel):
    """Deterministic comparison of promise facts with observed delivery facts."""

    tenant_id: str
    promise_id: str
    promise_version: int = Field(ge=1)
    external_order_ref: str
    evaluator_version: str = "customer-promise-v1"
    outcome: PromiseOutcome
    timing_delta_minutes: int | None = None
    fee_delta_minor_units: int | None = None
    instruction_breach: bool | None = None
    breach_types: tuple[str, ...] = ()
    evaluated_at: datetime
    fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class CauseAssertionType(StrEnum):
    VERIFIED_EVIDENCE = "verified_evidence"
    HYPOTHESIS = "hypothesis"


class CauseAssertion(StrictFrozenModel):
    """A root-cause statement that preserves whether it is proven or only hypothesized."""

    tenant_id: str = Field(min_length=1, max_length=120)
    assertion_id: str = Field(min_length=3, max_length=160)
    external_order_ref: str = Field(min_length=1, max_length=200)
    deviation_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    cause_code: str = Field(min_length=1, max_length=120)
    assertion_type: CauseAssertionType
    evidence_reference: str | None = Field(default=None, max_length=300)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    asserted_by: str = Field(min_length=1, max_length=180)
    asserted_at: datetime

    @model_validator(mode="after")
    def preserve_fact_hypothesis_boundary(self) -> "CauseAssertion":
        if self.assertion_type is CauseAssertionType.VERIFIED_EVIDENCE:
            if not self.evidence_reference:
                raise ValueError("verified cause assertion requires evidence reference")
            if self.confidence is not None:
                raise ValueError("verified evidence must not be represented as model confidence")
        return self


class RecoveryKind(StrEnum):
    CUSTOMER_MESSAGE = "customer_message"
    FEE_REFUND = "fee_refund"
    CREDIT = "credit"
    REORDER = "reorder"
    MANUAL_REVIEW = "manual_review"


FINANCIAL_RECOVERY_KINDS = frozenset({RecoveryKind.FEE_REFUND, RecoveryKind.CREDIT})


class RecoveryRequest(StrictFrozenModel):
    """Proposal only. This domain never silently executes a customer compensation."""

    tenant_id: str = Field(min_length=1, max_length=120)
    recovery_id: str = Field(min_length=3, max_length=160)
    external_order_ref: str = Field(min_length=1, max_length=200)
    deviation_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    kind: RecoveryKind
    amount: Money | None = None
    reason_code: str = Field(min_length=1, max_length=120)
    proposed_by: str = Field(min_length=1, max_length=180)
    proposed_at: datetime
    requires_human_approval: bool = True

    @model_validator(mode="after")
    def validate_recovery(self) -> "RecoveryRequest":
        if self.kind in FINANCIAL_RECOVERY_KINDS:
            if self.amount is None:
                raise ValueError("financial recovery requires an amount")
            if not self.requires_human_approval:
                raise ValueError("financial recovery cannot bypass human approval")
        elif self.amount is not None:
            raise ValueError("non-financial recovery cannot carry a monetary amount")
        return self


class RecoveryDecisionType(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"


class RecoveryDecision(StrictFrozenModel):
    tenant_id: str = Field(min_length=1, max_length=120)
    decision_id: str = Field(min_length=3, max_length=160)
    recovery_id: str = Field(min_length=3, max_length=160)
    decision: RecoveryDecisionType
    decided_by: str = Field(min_length=1, max_length=180)
    decided_at: datetime
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "RecoveryDecision":
        if self.decision is RecoveryDecisionType.REJECTED and not (self.reason or "").strip():
            raise ValueError("rejected recovery requires a reason")
        return self


class OrderExperienceSnapshot(StrictFrozenModel):
    """PII-minimized one-order view used by operations/Jarvis without creating CRM truth."""

    tenant_id: str
    external_order_ref: str
    promise: CustomerPromiseVersion
    actual: DeliveryActualSnapshot
    deviation: PromiseDeviation
    causes: tuple[CauseAssertion, ...] = ()
    recovery_requests: tuple[RecoveryRequest, ...] = ()
    recovery_decisions: tuple[RecoveryDecision, ...] = ()
