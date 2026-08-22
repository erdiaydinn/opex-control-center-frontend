"""Exact-version execution pinning for governed Jarvis robots.

A compiled robot plan is not execution authority. Production-shaped execution
must pin the immutable robot version + registry generation into a durable lease,
validate that pin before capability dispatch, and carry the same identity into
the final commit fence for mutating actions.

Canary health can recommend a rollback to an explicit immutable baseline, but
this module never mutates the registry and never grants side-effect authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

if TYPE_CHECKING:
    from .robot_registry_intelligence import CompiledRobotPlan

ROBOT_EXECUTION_PINNING_CONTRACT = "eay-jarvis-robot-execution-pinning-v1"


def _aware(value: datetime, code: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(code)


def _canonical(value: dict[str, Any]) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _sha(value: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


class RobotPinDisposition(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    EXPIRED = "expired"
    REVOKED = "revoked"
    HOLD = "hold"


class RobotExecutionPin(BaseModel):
    """Durable lease identity for one exact approved robot version."""

    model_config = ConfigDict(frozen=True)

    contract: str = ROBOT_EXECUTION_PINNING_CONTRACT
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    robot_version: int = Field(ge=1)
    registry_generation: int = Field(ge=1)
    version_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_evidence_ref: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    lease_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    lease_generation: int = Field(default=1, ge=1)
    issued_at: datetime
    expires_at: datetime
    canary: bool = False
    baseline_version: int | None = Field(default=None, ge=1)
    baseline_version_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    pin_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def pin_is_integral(self) -> RobotExecutionPin:
        _aware(self.issued_at, "robot_execution_pin_issued_at_requires_timezone")
        _aware(self.expires_at, "robot_execution_pin_expires_at_requires_timezone")
        if self.expires_at <= self.issued_at:
            raise ValueError("robot_execution_pin_expiry_must_follow_issue")
        baseline_paired = (self.baseline_version is None) == (
            self.baseline_version_fingerprint is None
        )
        if not baseline_paired:
            raise ValueError("robot_execution_pin_baseline_fields_must_be_paired")
        if self.canary:
            if self.baseline_version is None or self.baseline_version_fingerprint is None:
                raise ValueError("robot_execution_canary_requires_baseline")
            if self.baseline_version >= self.robot_version:
                raise ValueError("robot_execution_canary_baseline_must_be_older")
        elif self.baseline_version is not None:
            raise ValueError("robot_execution_non_canary_cannot_claim_baseline")
        if calculate_pin_fingerprint(self) != self.pin_fingerprint:
            raise ValueError("robot_execution_pin_fingerprint_mismatch")
        return self

    @property
    def evidence_ref(self) -> str:
        return (
            "robot-execution-pin://"
            + self.tenant_id
            + "/"
            + self.robot_id
            + "/v"
            + str(self.robot_version)
            + "/g"
            + str(self.registry_generation)
            + "/"
            + self.pin_fingerprint
        )


class RobotRegistryRuntimeView(BaseModel):
    model_config = ConfigDict(frozen=True)

    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    objective_id: str = Field(min_length=1)
    robot_id: str = Field(min_length=1)
    state: str = Field(min_length=1)
    active_version: int | None = Field(default=None, ge=1)
    active_version_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    generation: int = Field(ge=0)


class RobotExecutionGuardDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    disposition: RobotPinDisposition
    phase: str = Field(min_length=1)
    checked_at: datetime
    evidence_ref: str = Field(min_length=1)
    reason_code: str | None = None
    observed_registry_generation: int = Field(ge=0)
    observed_robot_version: int | None = Field(default=None, ge=1)
    observed_version_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_is_non_authoritative(self) -> RobotExecutionGuardDecision:
        _aware(self.checked_at, "robot_execution_guard_checked_at_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("robot_execution_guard_never_grants_execution_authority")
        if self.disposition is RobotPinDisposition.CURRENT and self.reason_code is not None:
            raise ValueError("robot_execution_current_guard_cannot_have_reason")
        if self.disposition is not RobotPinDisposition.CURRENT and not self.reason_code:
            raise ValueError("robot_execution_noncurrent_guard_requires_reason")
        return self

    @property
    def allowed(self) -> bool:
        return self.disposition is RobotPinDisposition.CURRENT


class RobotCanaryHealthSample(BaseModel):
    model_config = ConfigDict(frozen=True)

    attempts: int = Field(ge=1)
    verified_successes: int = Field(ge=0)
    incorrect_side_effects: int = Field(ge=0)
    unknown_effects: int = Field(ge=0)
    holds: int = Field(ge=0)
    sampled_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def sample_is_consistent(self) -> RobotCanaryHealthSample:
        _aware(self.sampled_at, "robot_canary_sample_requires_timezone")
        if self.verified_successes > self.attempts:
            raise ValueError("robot_canary_successes_exceed_attempts")
        if self.unknown_effects > self.attempts or self.holds > self.attempts:
            raise ValueError("robot_canary_counts_exceed_attempts")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("robot_canary_evidence_refs_must_be_unique")
        return self

    @property
    def success_rate(self) -> float:
        return self.verified_successes / self.attempts


class RobotCanaryDisposition(str, Enum):
    CONTINUE = "continue"
    PROMOTION_ELIGIBLE = "promotion_eligible"
    ROLLBACK_REQUIRED = "rollback_required"


class RobotCanaryDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    disposition: RobotCanaryDisposition
    pin_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_registry_generation: int = Field(ge=1)
    rollback_target_version: int | None = Field(default=None, ge=1)
    rollback_target_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    rollback_evidence_ref: str | None = None
    reason_codes: tuple[str, ...] = ()
    automatic_registry_mutation_authorized: bool = False

    @model_validator(mode="after")
    def canary_decision_never_mutates_registry(self) -> RobotCanaryDecision:
        if self.automatic_registry_mutation_authorized:
            raise ValueError("robot_canary_decision_cannot_mutate_registry")
        rollback = self.disposition is RobotCanaryDisposition.ROLLBACK_REQUIRED
        if rollback:
            if (
                self.rollback_target_version is None
                or self.rollback_target_fingerprint is None
                or not self.rollback_evidence_ref
                or not self.reason_codes
            ):
                raise ValueError("robot_canary_rollback_decision_incomplete")
        elif any(
            value is not None
            for value in (
                self.rollback_target_version,
                self.rollback_target_fingerprint,
                self.rollback_evidence_ref,
            )
        ):
            raise ValueError("robot_canary_nonrollback_cannot_claim_rollback_target")
        return self


def calculate_pin_fingerprint(pin: RobotExecutionPin) -> str:
    return _sha(
        pin.model_dump(
            mode="json",
            exclude={"pin_fingerprint"},
        )
    )


def build_execution_pin(
    *,
    plan: CompiledRobotPlan,
    mission_id: str,
    lease_id: str,
    lease_generation: int,
    issued_at: datetime,
    expires_at: datetime,
    canary: bool = False,
    baseline_version: int | None = None,
    baseline_version_fingerprint: str | None = None,
) -> RobotExecutionPin:
    """Bind a durable lease issued by the persistence authority to a compiled plan."""

    payload = {
        "tenant_id": plan.tenant_id,
        "company_id": plan.company_id,
        "objective_id": plan.objective_id,
        "robot_id": plan.robot_id,
        "robot_version": plan.robot_version,
        "registry_generation": plan.generation,
        "version_fingerprint": plan.version_fingerprint,
        "approval_evidence_ref": plan.approval_evidence_ref,
        "mission_id": mission_id,
        "lease_id": lease_id,
        "lease_generation": lease_generation,
        "issued_at": issued_at,
        "expires_at": expires_at,
        "canary": canary,
        "baseline_version": baseline_version,
        "baseline_version_fingerprint": baseline_version_fingerprint,
    }
    provisional = RobotExecutionPin.model_construct(
        **payload,
        pin_fingerprint="0" * 64,
    )
    return RobotExecutionPin(
        **payload,
        pin_fingerprint=calculate_pin_fingerprint(provisional),
    )


def validate_execution_pin(
    *,
    pin: RobotExecutionPin,
    runtime: RobotRegistryRuntimeView,
    phase: str,
    checked_at: datetime,
) -> RobotExecutionGuardDecision:
    """Fail closed when the registry moved, the lease expired, or scope drifted."""

    pin = RobotExecutionPin.model_validate(pin.model_dump(mode="json"))
    _aware(checked_at, "robot_execution_guard_checked_at_requires_timezone")
    reason: str | None = None
    disposition = RobotPinDisposition.CURRENT

    exact_scope = (
        runtime.tenant_id == pin.tenant_id
        and runtime.company_id == pin.company_id
        and runtime.objective_id == pin.objective_id
        and runtime.robot_id == pin.robot_id
    )
    if not exact_scope:
        disposition = RobotPinDisposition.HOLD
        reason = "robot_execution_scope_mismatch"
    elif checked_at >= pin.expires_at:
        disposition = RobotPinDisposition.EXPIRED
        reason = "robot_execution_lease_expired"
    elif runtime.state != "active":
        disposition = RobotPinDisposition.REVOKED
        reason = "robot_execution_registry_not_active"
    elif (
        runtime.generation != pin.registry_generation
        or runtime.active_version != pin.robot_version
        or runtime.active_version_fingerprint != pin.version_fingerprint
    ):
        disposition = RobotPinDisposition.STALE
        reason = "robot_execution_registry_generation_or_version_changed"

    evidence_payload = {
        "pin_fingerprint": pin.pin_fingerprint,
        "phase": phase,
        "checked_at": checked_at.isoformat(),
        "disposition": disposition.value,
        "reason_code": reason,
        "observed_registry_generation": runtime.generation,
        "observed_robot_version": runtime.active_version,
        "observed_version_fingerprint": runtime.active_version_fingerprint,
    }
    return RobotExecutionGuardDecision(
        disposition=disposition,
        phase=phase,
        checked_at=checked_at,
        evidence_ref="robot-pin-validation://" + _sha(evidence_payload),
        reason_code=reason,
        observed_registry_generation=runtime.generation,
        observed_robot_version=runtime.active_version,
        observed_version_fingerprint=runtime.active_version_fingerprint,
    )


def evaluate_canary_health(
    *,
    pin: RobotExecutionPin,
    sample: RobotCanaryHealthSample,
    minimum_attempts: int = 20,
    minimum_verified_success_rate: float = 0.95,
    maximum_hold_rate: float = 0.20,
) -> RobotCanaryDecision:
    """Produce a rollback request, never a registry mutation."""

    if not pin.canary:
        raise ValueError("robot_canary_health_requires_canary_pin")
    if minimum_attempts < 1:
        raise ValueError("robot_canary_minimum_attempts_must_be_positive")
    if not 0.0 <= minimum_verified_success_rate <= 1.0:
        raise ValueError("robot_canary_success_threshold_out_of_range")
    if not 0.0 <= maximum_hold_rate <= 1.0:
        raise ValueError("robot_canary_hold_threshold_out_of_range")

    reasons: list[str] = []
    if sample.incorrect_side_effects > 0:
        reasons.append("robot_canary_incorrect_side_effect_observed")
    if sample.unknown_effects > 0:
        reasons.append("robot_canary_unknown_effect_observed")
    if sample.attempts >= minimum_attempts:
        if sample.success_rate < minimum_verified_success_rate:
            reasons.append("robot_canary_verified_success_rate_below_threshold")
        if sample.holds / sample.attempts > maximum_hold_rate:
            reasons.append("robot_canary_hold_rate_above_threshold")

    if reasons:
        evidence = _sha(
            {
                "pin_fingerprint": pin.pin_fingerprint,
                "sample": sample.model_dump(mode="json"),
                "reason_codes": reasons,
            }
        )
        return RobotCanaryDecision(
            disposition=RobotCanaryDisposition.ROLLBACK_REQUIRED,
            pin_fingerprint=pin.pin_fingerprint,
            expected_registry_generation=pin.registry_generation,
            rollback_target_version=pin.baseline_version,
            rollback_target_fingerprint=pin.baseline_version_fingerprint,
            rollback_evidence_ref="robot-canary-rollback://" + evidence,
            reason_codes=tuple(reasons),
        )

    if sample.attempts < minimum_attempts:
        return RobotCanaryDecision(
            disposition=RobotCanaryDisposition.CONTINUE,
            pin_fingerprint=pin.pin_fingerprint,
            expected_registry_generation=pin.registry_generation,
        )
    return RobotCanaryDecision(
        disposition=RobotCanaryDisposition.PROMOTION_ELIGIBLE,
        pin_fingerprint=pin.pin_fingerprint,
        expected_registry_generation=pin.registry_generation,
    )
