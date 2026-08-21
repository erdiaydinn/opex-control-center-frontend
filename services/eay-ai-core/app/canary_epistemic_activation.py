"""Fail-closed canary rollout for Jarvis epistemic strategy candidates.

The contract changes only epistemic strategy selection. It never grants model
provider, tool, business-action, execution, or side-effect authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .shadow_epistemic_acceptance import ShadowAcceptanceEvidence, ShadowPerformance

FP = r"^[0-9a-f]{64}$"


def _canonical(value: object) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
        default=str,
    )


def _fingerprint(value: object) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _utc(value: datetime, name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name}_must_be_timezone_aware")
    return value.astimezone(UTC)


class SealedModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


T = TypeVar("T", bound=SealedModel)


def _payload(item: SealedModel, fingerprint_field: str) -> dict[str, object]:
    return item.model_dump(mode="json", exclude={fingerprint_field})


def _seal(model: type[T], fingerprint_field: str, values: dict[str, object]) -> T:
    draft = model.model_construct(**values, **{fingerprint_field: "0" * 64})
    return model(
        **values,
        **{fingerprint_field: _fingerprint(_payload(draft, fingerprint_field))},
    )


def _assert_seal(item: SealedModel, fingerprint_field: str, error: str) -> None:
    expected = _fingerprint(_payload(item, fingerprint_field))
    if getattr(item, fingerprint_field) != expected:
        raise ValueError(error)


class RolloutState(str, Enum):
    ACTIVE = "active"
    ROLLED_BACK = "rolled_back"


class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DRIFTED = "drifted"
    UNKNOWN = "unknown"


class CanaryIdentity(SealedModel):
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    rollout_id: str = Field(min_length=1)


class NonExecutionAuthority(SealedModel):
    provider_authority_granted: bool = False
    tool_authority_granted: bool = False
    business_action_authority_granted: bool = False
    execution_authority_granted: bool = False
    side_effect_authority_granted: bool = False

    @model_validator(mode="after")
    def none_granted(self) -> "NonExecutionAuthority":
        if any(
            (
                self.provider_authority_granted,
                self.tool_authority_granted,
                self.business_action_authority_granted,
                self.execution_authority_granted,
                self.side_effect_authority_granted,
            )
        ):
            raise ValueError("canary_never_grants_execution_authority")
        return self


class ApprovedBaseline(SealedModel):
    contract: str = "eay-epistemic-canary-baseline-v1"
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    profile_ref: str = Field(min_length=1)
    profile_fingerprint: str = Field(pattern=FP)
    approved_at: datetime
    expires_at: datetime
    approval_evidence_ref: str = Field(min_length=1)
    baseline_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "ApprovedBaseline":
        if _utc(self.expires_at, "expires_at") <= _utc(self.approved_at, "approved_at"):
            raise ValueError("canary_baseline_expiry_must_follow_approval")
        _assert_seal(self, "baseline_fingerprint", "canary_baseline_fingerprint_mismatch")
        return self


class ActivationApproval(SealedModel):
    contract: str = "eay-epistemic-canary-approval-v1"
    identity: CanaryIdentity
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    baseline_profile_fingerprint: str = Field(pattern=FP)
    shadow_acceptance_fingerprint: str = Field(pattern=FP)
    maximum_exposure_fraction: float = Field(gt=0.0, le=0.25)
    approved_by_ref: str = Field(min_length=1)
    approval_authority_ref: str = Field(min_length=1)
    approval_authority_verified: bool
    approval_evidence_ref: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime
    approval_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "ActivationApproval":
        if _utc(self.expires_at, "expires_at") <= _utc(self.approved_at, "approved_at"):
            raise ValueError("canary_approval_expiry_must_follow_approval")
        if not self.approval_authority_verified:
            raise ValueError("canary_activation_requires_verified_review_authority")
        _assert_seal(self, "approval_fingerprint", "canary_approval_fingerprint_mismatch")
        return self


class ActivationReceipt(SealedModel):
    contract: str = "eay-epistemic-canary-activation-v1"
    identity: CanaryIdentity
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    baseline_profile_fingerprint: str = Field(pattern=FP)
    shadow_acceptance_fingerprint: str = Field(pattern=FP)
    approval_fingerprint: str = Field(pattern=FP)
    maximum_exposure_fraction: float = Field(gt=0.0, le=0.25)
    activated_at: datetime
    epistemic_selection_state_changed: bool = True
    authority: NonExecutionAuthority = Field(default_factory=NonExecutionAuthority)
    activation_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "ActivationReceipt":
        _utc(self.activated_at, "activated_at")
        if not self.epistemic_selection_state_changed:
            raise ValueError("canary_activation_must_change_selection_state")
        NonExecutionAuthority.model_validate(self.authority.model_dump())
        _assert_seal(
            self,
            "activation_fingerprint",
            "canary_activation_fingerprint_mismatch",
        )
        return self


class RolloutSnapshot(SealedModel):
    contract: str = "eay-epistemic-canary-snapshot-v1"
    identity: CanaryIdentity
    generation: int = Field(ge=1)
    state: RolloutState
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    baseline_profile_fingerprint: str = Field(pattern=FP)
    selected_profile_fingerprint: str = Field(pattern=FP)
    activation_fingerprint: str = Field(pattern=FP)
    rollback_fingerprint: str | None = Field(default=None, pattern=FP)
    updated_at: datetime
    snapshot_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "RolloutSnapshot":
        _utc(self.updated_at, "updated_at")
        selected = (
            self.candidate_fingerprint
            if self.state is RolloutState.ACTIVE
            else self.baseline_profile_fingerprint
        )
        if self.selected_profile_fingerprint != selected:
            raise ValueError("canary_snapshot_selected_profile_mismatch")
        if self.state is RolloutState.ACTIVE and self.rollback_fingerprint:
            raise ValueError("canary_active_snapshot_cannot_have_rollback")
        if self.state is RolloutState.ROLLED_BACK and not self.rollback_fingerprint:
            raise ValueError("canary_rolled_back_snapshot_requires_receipt")
        _assert_seal(self, "snapshot_fingerprint", "canary_snapshot_fingerprint_mismatch")
        return self


class HealthPolicy(SealedModel):
    minimum_sample_count: int = Field(default=30, ge=1)
    maximum_telemetry_age_seconds: int = Field(default=900, ge=30, le=86400)
    minimum_grounding_integrity_rate: float = Field(default=0.995, ge=0.0, le=1.0)
    minimum_authority_integrity_rate: float = Field(default=1.0, ge=0.0, le=1.0)
    minimum_safe_failure_rate: float = Field(default=0.99, ge=0.0, le=1.0)
    maximum_quality_regression: float = Field(default=0.02, ge=0.0, le=0.25)
    maximum_brier_regression: float = Field(default=0.02, ge=0.0, le=0.25)
    maximum_error_rate_delta: float = Field(default=0.02, ge=0.0, le=0.50)
    fail_closed_on_unknown: bool = True

    @model_validator(mode="after")
    def fail_closed(self) -> "HealthPolicy":
        if not self.fail_closed_on_unknown:
            raise ValueError("canary_health_unknown_must_fail_closed")
        return self


class HealthObservation(SealedModel):
    contract: str = "eay-epistemic-canary-health-v1"
    observation_id: str = Field(min_length=1)
    identity: CanaryIdentity
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    window_started_at: datetime
    window_ended_at: datetime
    sample_count: int = Field(ge=0)
    baseline: ShadowPerformance
    candidate: ShadowPerformance
    grounding_integrity_rate: float = Field(ge=0.0, le=1.0)
    authority_integrity_rate: float = Field(ge=0.0, le=1.0)
    safe_failure_rate: float = Field(ge=0.0, le=1.0)
    baseline_error_rate: float = Field(ge=0.0, le=1.0)
    candidate_error_rate: float = Field(ge=0.0, le=1.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    observation_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "HealthObservation":
        if _utc(self.window_ended_at, "window_ended_at") <= _utc(
            self.window_started_at,
            "window_started_at",
        ):
            raise ValueError("canary_health_window_must_advance")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("canary_health_evidence_refs_must_be_unique")
        _assert_seal(
            self,
            "observation_fingerprint",
            "canary_health_fingerprint_mismatch",
        )
        return self


class HealthVerdict(SealedModel):
    contract: str = "eay-epistemic-canary-health-verdict-v1"
    identity: CanaryIdentity
    generation: int = Field(ge=1)
    observation_fingerprint: str = Field(pattern=FP)
    status: HealthStatus
    rollback_required: bool
    blockers: tuple[str, ...] = ()
    evaluated_at: datetime
    verdict_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "HealthVerdict":
        _utc(self.evaluated_at, "evaluated_at")
        if self.status is HealthStatus.HEALTHY:
            if self.rollback_required or self.blockers:
                raise ValueError("healthy_canary_cannot_require_rollback")
        elif not self.rollback_required:
            raise ValueError("unhealthy_canary_must_require_rollback")
        _assert_seal(self, "verdict_fingerprint", "canary_health_verdict_mismatch")
        return self


class RollbackReceipt(SealedModel):
    contract: str = "eay-epistemic-canary-rollback-v1"
    identity: CanaryIdentity
    source_generation: int = Field(ge=1)
    resulting_generation: int = Field(ge=2)
    approved_baseline_fingerprint: str = Field(pattern=FP)
    restored_baseline_profile_fingerprint: str = Field(pattern=FP)
    activation_fingerprint: str = Field(pattern=FP)
    health_verdict_fingerprint: str = Field(pattern=FP)
    idempotency_key: str = Field(min_length=8, max_length=200)
    rolled_back_at: datetime
    epistemic_selection_state_changed: bool = True
    authority: NonExecutionAuthority = Field(default_factory=NonExecutionAuthority)
    rollback_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "RollbackReceipt":
        _utc(self.rolled_back_at, "rolled_back_at")
        if self.resulting_generation != self.source_generation + 1:
            raise ValueError("canary_rollback_generation_must_increment_once")
        if not self.epistemic_selection_state_changed:
            raise ValueError("canary_rollback_must_change_selection_state")
        NonExecutionAuthority.model_validate(self.authority.model_dump())
        _assert_seal(self, "rollback_fingerprint", "canary_rollback_fingerprint_mismatch")
        return self


def seal_baseline(
    *,
    tenant_id: str,
    company_id: str,
    problem_class: str,
    profile_ref: str,
    profile_fingerprint: str,
    approved_at: datetime,
    expires_at: datetime,
    approval_evidence_ref: str,
) -> ApprovedBaseline:
    return _seal(
        ApprovedBaseline,
        "baseline_fingerprint",
        locals() | {"contract": "eay-epistemic-canary-baseline-v1"},
    )


def seal_activation_approval(
    *,
    identity: CanaryIdentity,
    generation: int,
    candidate_fingerprint: str,
    baseline: ApprovedBaseline,
    shadow_acceptance_fingerprint: str,
    maximum_exposure_fraction: float,
    approved_by_ref: str,
    approval_authority_ref: str,
    approval_authority_verified: bool,
    approval_evidence_ref: str,
    approved_at: datetime,
    expires_at: datetime,
) -> ActivationApproval:
    values = {
        "contract": "eay-epistemic-canary-approval-v1",
        "identity": identity,
        "generation": generation,
        "candidate_fingerprint": candidate_fingerprint,
        "baseline_fingerprint": baseline.baseline_fingerprint,
        "baseline_profile_fingerprint": baseline.profile_fingerprint,
        "shadow_acceptance_fingerprint": shadow_acceptance_fingerprint,
        "maximum_exposure_fraction": maximum_exposure_fraction,
        "approved_by_ref": approved_by_ref,
        "approval_authority_ref": approval_authority_ref,
        "approval_authority_verified": approval_authority_verified,
        "approval_evidence_ref": approval_evidence_ref,
        "approved_at": approved_at,
        "expires_at": expires_at,
    }
    return _seal(ActivationApproval, "approval_fingerprint", values)


def activate_canary(
    *,
    shadow: ShadowAcceptanceEvidence,
    baseline: ApprovedBaseline,
    approval: ActivationApproval,
    activated_at: datetime,
    current_snapshot: RolloutSnapshot | None = None,
) -> tuple[RolloutSnapshot, ActivationReceipt]:
    shadow = ShadowAcceptanceEvidence.model_validate(shadow.model_dump(mode="json"))
    baseline = ApprovedBaseline.model_validate(baseline.model_dump(mode="json"))
    approval = ActivationApproval.model_validate(approval.model_dump(mode="json"))
    now = _utc(activated_at, "activated_at")
    if current_snapshot is not None:
        RolloutSnapshot.model_validate(current_snapshot.model_dump(mode="json"))
        raise ValueError("canary_activation_rollout_already_exists")
    if not shadow.production_shaped_acceptance_passed:
        raise ValueError("canary_activation_shadow_not_passed")
    if not shadow.controlled_activation_review_ready:
        raise ValueError("canary_activation_review_not_ready")
    if any(
        (
            shadow.automatic_activation_allowed,
            shadow.execution_authority_granted,
            shadow.side_effect_authority_granted,
        )
    ):
        raise ValueError("canary_activation_shadow_authority_boundary_violated")
    if now > _utc(baseline.expires_at, "expires_at"):
        raise ValueError("canary_activation_baseline_expired")
    if now > _utc(approval.expires_at, "expires_at"):
        raise ValueError("canary_activation_approval_expired")
    expected = (shadow.tenant_id, shadow.company_id, shadow.problem_class)
    baseline_identity = (baseline.tenant_id, baseline.company_id, baseline.problem_class)
    approval_identity = (
        approval.identity.tenant_id,
        approval.identity.company_id,
        approval.identity.problem_class,
    )
    if baseline_identity != expected:
        raise ValueError("canary_activation_baseline_identity_mismatch")
    if approval_identity != expected:
        raise ValueError("canary_activation_approval_identity_mismatch")
    if approval.generation != 1:
        raise ValueError("canary_activation_initial_generation_must_be_one")
    if approval.candidate_fingerprint != shadow.candidate_fingerprint:
        raise ValueError("canary_activation_candidate_mismatch")
    if approval.baseline_fingerprint != baseline.baseline_fingerprint:
        raise ValueError("canary_activation_baseline_mismatch")
    if approval.baseline_profile_fingerprint != baseline.profile_fingerprint:
        raise ValueError("canary_activation_baseline_profile_mismatch")
    if approval.shadow_acceptance_fingerprint != shadow.acceptance_fingerprint:
        raise ValueError("canary_activation_shadow_fingerprint_mismatch")

    receipt = _seal(
        ActivationReceipt,
        "activation_fingerprint",
        {
            "identity": approval.identity,
            "generation": 1,
            "candidate_fingerprint": shadow.candidate_fingerprint,
            "baseline_fingerprint": baseline.baseline_fingerprint,
            "baseline_profile_fingerprint": baseline.profile_fingerprint,
            "shadow_acceptance_fingerprint": shadow.acceptance_fingerprint,
            "approval_fingerprint": approval.approval_fingerprint,
            "maximum_exposure_fraction": approval.maximum_exposure_fraction,
            "activated_at": now,
        },
    )
    snapshot = _seal(
        RolloutSnapshot,
        "snapshot_fingerprint",
        {
            "identity": approval.identity,
            "generation": 1,
            "state": RolloutState.ACTIVE,
            "candidate_fingerprint": shadow.candidate_fingerprint,
            "baseline_fingerprint": baseline.baseline_fingerprint,
            "baseline_profile_fingerprint": baseline.profile_fingerprint,
            "selected_profile_fingerprint": shadow.candidate_fingerprint,
            "activation_fingerprint": receipt.activation_fingerprint,
            "rollback_fingerprint": None,
            "updated_at": now,
        },
    )
    return snapshot, receipt


def seal_health_observation(
    *,
    snapshot: RolloutSnapshot,
    observation_id: str,
    window_started_at: datetime,
    window_ended_at: datetime,
    sample_count: int,
    baseline: ShadowPerformance,
    candidate: ShadowPerformance,
    grounding_integrity_rate: float,
    authority_integrity_rate: float,
    safe_failure_rate: float,
    baseline_error_rate: float,
    candidate_error_rate: float,
    evidence_refs: tuple[str, ...],
) -> HealthObservation:
    snapshot = RolloutSnapshot.model_validate(snapshot.model_dump(mode="json"))
    return _seal(
        HealthObservation,
        "observation_fingerprint",
        {
            "observation_id": observation_id,
            "identity": snapshot.identity,
            "generation": snapshot.generation,
            "candidate_fingerprint": snapshot.candidate_fingerprint,
            "baseline_fingerprint": snapshot.baseline_fingerprint,
            "window_started_at": window_started_at,
            "window_ended_at": window_ended_at,
            "sample_count": sample_count,
            "baseline": baseline,
            "candidate": candidate,
            "grounding_integrity_rate": grounding_integrity_rate,
            "authority_integrity_rate": authority_integrity_rate,
            "safe_failure_rate": safe_failure_rate,
            "baseline_error_rate": baseline_error_rate,
            "candidate_error_rate": candidate_error_rate,
            "evidence_refs": evidence_refs,
        },
    )


def assess_health(
    *,
    snapshot: RolloutSnapshot,
    observation: HealthObservation,
    evaluated_at: datetime,
    policy: HealthPolicy | None = None,
) -> HealthVerdict:
    snapshot = RolloutSnapshot.model_validate(snapshot.model_dump(mode="json"))
    observation = HealthObservation.model_validate(observation.model_dump(mode="json"))
    rules = policy or HealthPolicy()
    now = _utc(evaluated_at, "evaluated_at")
    if snapshot.state is not RolloutState.ACTIVE:
        raise ValueError("canary_health_requires_active_rollout")
    if observation.identity != snapshot.identity:
        raise ValueError("canary_health_identity_mismatch")
    if observation.generation != snapshot.generation:
        raise ValueError("canary_health_stale_generation")
    if observation.candidate_fingerprint != snapshot.candidate_fingerprint:
        raise ValueError("canary_health_candidate_mismatch")
    if observation.baseline_fingerprint != snapshot.baseline_fingerprint:
        raise ValueError("canary_health_baseline_mismatch")

    blockers: list[str] = []
    age = (now - _utc(observation.window_ended_at, "window_ended_at")).total_seconds()
    unknown = False
    if age < 0:
        blockers.append("canary_health_future_telemetry_forbidden")
        unknown = True
    if age > rules.maximum_telemetry_age_seconds:
        blockers.append("canary_health_telemetry_stale")
        unknown = True
    if observation.sample_count < rules.minimum_sample_count:
        blockers.append("canary_health_sample_count_insufficient")
        unknown = True
    if observation.grounding_integrity_rate < rules.minimum_grounding_integrity_rate:
        blockers.append("canary_health_grounding_integrity_regression")
    if observation.authority_integrity_rate < rules.minimum_authority_integrity_rate:
        blockers.append("canary_health_authority_integrity_regression")
    if observation.safe_failure_rate < rules.minimum_safe_failure_rate:
        blockers.append("canary_health_safe_failure_regression")
    if (
        observation.candidate.quality_score + rules.maximum_quality_regression
        < observation.baseline.quality_score
    ):
        blockers.append("canary_health_quality_regression")
    if (
        observation.candidate.brier_score
        > observation.baseline.brier_score + rules.maximum_brier_regression
    ):
        blockers.append("canary_health_calibration_regression")
    if (
        observation.candidate_error_rate
        > observation.baseline_error_rate + rules.maximum_error_rate_delta
    ):
        blockers.append("canary_health_error_rate_regression")

    unique = tuple(dict.fromkeys(blockers))
    if unknown:
        status = HealthStatus.UNKNOWN
    elif unique:
        status = HealthStatus.DRIFTED
    else:
        status = HealthStatus.HEALTHY
    return _seal(
        HealthVerdict,
        "verdict_fingerprint",
        {
            "identity": snapshot.identity,
            "generation": snapshot.generation,
            "observation_fingerprint": observation.observation_fingerprint,
            "status": status,
            "rollback_required": status is not HealthStatus.HEALTHY,
            "blockers": unique,
            "evaluated_at": now,
        },
    )


def automatic_rollback(
    *,
    snapshot: RolloutSnapshot,
    activation: ActivationReceipt,
    baseline: ApprovedBaseline,
    verdict: HealthVerdict,
    idempotency_key: str,
    rolled_back_at: datetime,
    previous_receipt: RollbackReceipt | None = None,
) -> tuple[RolloutSnapshot, RollbackReceipt]:
    snapshot = RolloutSnapshot.model_validate(snapshot.model_dump(mode="json"))
    activation = ActivationReceipt.model_validate(activation.model_dump(mode="json"))
    baseline = ApprovedBaseline.model_validate(baseline.model_dump(mode="json"))
    verdict = HealthVerdict.model_validate(verdict.model_dump(mode="json"))
    now = _utc(rolled_back_at, "rolled_back_at")

    if previous_receipt is not None:
        old = RollbackReceipt.model_validate(previous_receipt.model_dump(mode="json"))
        if snapshot.state is not RolloutState.ROLLED_BACK:
            raise ValueError("canary_rollback_replay_requires_rolled_back_snapshot")
        if old.idempotency_key != idempotency_key:
            raise ValueError("canary_rollback_previous_receipt_key_mismatch")
        replay_ok = all(
            (
                old.identity == snapshot.identity,
                old.resulting_generation == snapshot.generation,
                old.rollback_fingerprint == snapshot.rollback_fingerprint,
                old.activation_fingerprint == activation.activation_fingerprint,
                old.health_verdict_fingerprint == verdict.verdict_fingerprint,
                old.approved_baseline_fingerprint == baseline.baseline_fingerprint,
                old.restored_baseline_profile_fingerprint == baseline.profile_fingerprint,
                activation.generation == old.source_generation,
                verdict.generation == old.source_generation,
            )
        )
        if not replay_ok:
            raise ValueError("canary_rollback_idempotency_conflict")
        return snapshot, old

    if snapshot.state is not RolloutState.ACTIVE:
        raise ValueError("canary_rollback_requires_active_rollout")
    if not verdict.rollback_required:
        raise ValueError("canary_rollback_requires_unhealthy_verdict")
    if activation.identity != snapshot.identity or verdict.identity != snapshot.identity:
        raise ValueError("canary_rollback_identity_mismatch")
    if activation.generation != snapshot.generation or verdict.generation != snapshot.generation:
        raise ValueError("canary_rollback_generation_mismatch")
    if activation.activation_fingerprint != snapshot.activation_fingerprint:
        raise ValueError("canary_rollback_activation_fingerprint_mismatch")
    if baseline.baseline_fingerprint != snapshot.baseline_fingerprint:
        raise ValueError("canary_rollback_exact_baseline_required")
    if baseline.profile_fingerprint != snapshot.baseline_profile_fingerprint:
        raise ValueError("canary_rollback_exact_baseline_profile_required")

    receipt = _seal(
        RollbackReceipt,
        "rollback_fingerprint",
        {
            "identity": snapshot.identity,
            "source_generation": snapshot.generation,
            "resulting_generation": snapshot.generation + 1,
            "approved_baseline_fingerprint": baseline.baseline_fingerprint,
            "restored_baseline_profile_fingerprint": baseline.profile_fingerprint,
            "activation_fingerprint": activation.activation_fingerprint,
            "health_verdict_fingerprint": verdict.verdict_fingerprint,
            "idempotency_key": idempotency_key,
            "rolled_back_at": now,
        },
    )
    rolled_back = _seal(
        RolloutSnapshot,
        "snapshot_fingerprint",
        {
            "identity": snapshot.identity,
            "generation": receipt.resulting_generation,
            "state": RolloutState.ROLLED_BACK,
            "candidate_fingerprint": snapshot.candidate_fingerprint,
            "baseline_fingerprint": snapshot.baseline_fingerprint,
            "baseline_profile_fingerprint": snapshot.baseline_profile_fingerprint,
            "selected_profile_fingerprint": snapshot.baseline_profile_fingerprint,
            "activation_fingerprint": snapshot.activation_fingerprint,
            "rollback_fingerprint": receipt.rollback_fingerprint,
            "updated_at": now,
        },
    )
    return rolled_back, receipt
