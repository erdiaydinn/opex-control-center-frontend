"""Sustained-health promotion evidence for Jarvis epistemic canaries.

This module does not activate a provider, tool, business action, model weight, or
business policy. It only seals evidence that a canary is eligible for a separate
verified promotion review after repeated healthy telemetry windows.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import Enum
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .canary_epistemic_activation import (
    ActivationReceipt,
    HealthStatus,
    HealthVerdict,
    NonExecutionAuthority,
    RolloutSnapshot,
    RolloutState,
)

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
    if getattr(item, fingerprint_field) != _fingerprint(_payload(item, fingerprint_field)):
        raise ValueError(error)


class PromotionDisposition(str, Enum):
    HOLD = "hold"
    REVIEW_READY = "review_ready"


class PromotionPolicy(SealedModel):
    minimum_healthy_windows: int = Field(default=3, ge=2, le=20)
    minimum_observation_span_seconds: int = Field(default=1800, ge=60, le=604800)
    maximum_last_verdict_age_seconds: int = Field(default=900, ge=30, le=86400)
    require_distinct_observations: bool = True
    automatic_promotion_allowed: bool = False

    @model_validator(mode="after")
    def safe(self) -> "PromotionPolicy":
        if not self.require_distinct_observations:
            raise ValueError("canary_promotion_requires_distinct_observations")
        if self.automatic_promotion_allowed:
            raise ValueError("canary_promotion_cannot_be_automatic")
        return self


class PromotionEvidence(SealedModel):
    contract: str = "eay-epistemic-canary-promotion-evidence-v1"
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    rollout_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    baseline_profile_fingerprint: str = Field(pattern=FP)
    activation_fingerprint: str = Field(pattern=FP)
    verdict_fingerprints: tuple[str, ...]
    observation_fingerprints: tuple[str, ...]
    first_evaluated_at: datetime | None
    last_evaluated_at: datetime | None
    disposition: PromotionDisposition
    blockers: tuple[str, ...] = ()
    automatic_promotion_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    automatic_model_weight_update_allowed: bool = False
    authority: NonExecutionAuthority = Field(default_factory=NonExecutionAuthority)
    evaluated_at: datetime
    evidence_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "PromotionEvidence":
        _utc(self.evaluated_at, "evaluated_at")
        if self.first_evaluated_at is not None:
            _utc(self.first_evaluated_at, "first_evaluated_at")
        if self.last_evaluated_at is not None:
            _utc(self.last_evaluated_at, "last_evaluated_at")
        if len(self.verdict_fingerprints) != len(set(self.verdict_fingerprints)):
            raise ValueError("canary_promotion_verdicts_must_be_unique")
        if len(self.observation_fingerprints) != len(set(self.observation_fingerprints)):
            raise ValueError("canary_promotion_observations_must_be_unique")
        if any(
            (
                self.automatic_promotion_allowed,
                self.automatic_policy_update_allowed,
                self.automatic_model_weight_update_allowed,
            )
        ):
            raise ValueError("canary_promotion_never_auto_activates")
        NonExecutionAuthority.model_validate(self.authority.model_dump())
        if self.disposition is PromotionDisposition.REVIEW_READY:
            if self.blockers:
                raise ValueError("review_ready_promotion_cannot_have_blockers")
            if not self.verdict_fingerprints:
                raise ValueError("review_ready_promotion_requires_health_evidence")
        elif not self.blockers:
            raise ValueError("held_promotion_requires_blocker")
        _assert_seal(
            self,
            "evidence_fingerprint",
            "canary_promotion_evidence_fingerprint_mismatch",
        )
        return self


class PromotionApproval(SealedModel):
    contract: str = "eay-epistemic-canary-promotion-approval-v1"
    evidence_fingerprint: str = Field(pattern=FP)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    rollout_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    approved_by_ref: str = Field(min_length=1)
    review_authority_ref: str = Field(min_length=1)
    review_authority_verified: bool
    approval_evidence_ref: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime
    approval_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "PromotionApproval":
        if _utc(self.expires_at, "expires_at") <= _utc(self.approved_at, "approved_at"):
            raise ValueError("canary_promotion_approval_expiry_must_follow_approval")
        if not self.review_authority_verified:
            raise ValueError("canary_promotion_requires_verified_review_authority")
        _assert_seal(
            self,
            "approval_fingerprint",
            "canary_promotion_approval_fingerprint_mismatch",
        )
        return self


class PromotionReviewReceipt(SealedModel):
    contract: str = "eay-epistemic-canary-promotion-review-v1"
    evidence_fingerprint: str = Field(pattern=FP)
    approval_fingerprint: str = Field(pattern=FP)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    problem_class: str = Field(min_length=1)
    rollout_id: str = Field(min_length=1)
    generation: int = Field(ge=1)
    candidate_fingerprint: str = Field(pattern=FP)
    baseline_fingerprint: str = Field(pattern=FP)
    promotion_review_passed: bool = True
    production_activation_performed: bool = False
    authority: NonExecutionAuthority = Field(default_factory=NonExecutionAuthority)
    reviewed_at: datetime
    receipt_fingerprint: str = Field(pattern=FP)

    @model_validator(mode="after")
    def valid(self) -> "PromotionReviewReceipt":
        _utc(self.reviewed_at, "reviewed_at")
        if not self.promotion_review_passed:
            raise ValueError("promotion_review_receipt_requires_pass")
        if self.production_activation_performed:
            raise ValueError("promotion_review_does_not_perform_activation")
        NonExecutionAuthority.model_validate(self.authority.model_dump())
        _assert_seal(
            self,
            "receipt_fingerprint",
            "canary_promotion_review_receipt_mismatch",
        )
        return self


def assess_promotion_readiness(
    *,
    snapshot: RolloutSnapshot,
    activation: ActivationReceipt,
    verdicts: tuple[HealthVerdict, ...],
    evaluated_at: datetime,
    policy: PromotionPolicy | None = None,
) -> PromotionEvidence:
    snapshot = RolloutSnapshot.model_validate(snapshot.model_dump(mode="json"))
    activation = ActivationReceipt.model_validate(activation.model_dump(mode="json"))
    clean = tuple(
        HealthVerdict.model_validate(item.model_dump(mode="json"))
        for item in verdicts
    )
    rules = policy or PromotionPolicy()
    now = _utc(evaluated_at, "evaluated_at")

    if snapshot.state is not RolloutState.ACTIVE:
        raise ValueError("canary_promotion_requires_active_rollout")
    if activation.identity != snapshot.identity:
        raise ValueError("canary_promotion_activation_identity_mismatch")
    if activation.generation != snapshot.generation:
        raise ValueError("canary_promotion_activation_generation_mismatch")
    if activation.activation_fingerprint != snapshot.activation_fingerprint:
        raise ValueError("canary_promotion_activation_fingerprint_mismatch")

    blockers: list[str] = []
    valid: list[HealthVerdict] = []
    for verdict in clean:
        if verdict.identity != snapshot.identity:
            raise ValueError("canary_promotion_health_identity_mismatch")
        if verdict.generation != snapshot.generation:
            raise ValueError("canary_promotion_health_generation_mismatch")
        if verdict.status is not HealthStatus.HEALTHY or verdict.rollback_required:
            blockers.append("canary_promotion_requires_only_healthy_windows")
            continue
        valid.append(verdict)

    ordered = sorted(valid, key=lambda item: _utc(item.evaluated_at, "evaluated_at"))
    verdict_fps = tuple(item.verdict_fingerprint for item in ordered)
    observation_fps = tuple(item.observation_fingerprint for item in ordered)

    if len(valid) < rules.minimum_healthy_windows:
        blockers.append("canary_promotion_healthy_window_count_insufficient")
    if len(verdict_fps) != len(set(verdict_fps)):
        blockers.append("canary_promotion_duplicate_health_verdict")
    if len(observation_fps) != len(set(observation_fps)):
        blockers.append("canary_promotion_duplicate_health_observation")

    first = _utc(ordered[0].evaluated_at, "evaluated_at") if ordered else None
    last = _utc(ordered[-1].evaluated_at, "evaluated_at") if ordered else None
    if first is not None and last is not None:
        if (last - first).total_seconds() < rules.minimum_observation_span_seconds:
            blockers.append("canary_promotion_observation_span_insufficient")
        age = (now - last).total_seconds()
        if age < 0:
            blockers.append("canary_promotion_future_health_evidence_forbidden")
        elif age > rules.maximum_last_verdict_age_seconds:
            blockers.append("canary_promotion_latest_health_evidence_stale")

    unique = tuple(dict.fromkeys(blockers))
    disposition = (
        PromotionDisposition.REVIEW_READY
        if not unique
        else PromotionDisposition.HOLD
    )
    return _seal(
        PromotionEvidence,
        "evidence_fingerprint",
        {
            "tenant_id": snapshot.identity.tenant_id,
            "company_id": snapshot.identity.company_id,
            "problem_class": snapshot.identity.problem_class,
            "rollout_id": snapshot.identity.rollout_id,
            "generation": snapshot.generation,
            "candidate_fingerprint": snapshot.candidate_fingerprint,
            "baseline_fingerprint": snapshot.baseline_fingerprint,
            "baseline_profile_fingerprint": snapshot.baseline_profile_fingerprint,
            "activation_fingerprint": snapshot.activation_fingerprint,
            "verdict_fingerprints": verdict_fps,
            "observation_fingerprints": observation_fps,
            "first_evaluated_at": first,
            "last_evaluated_at": last,
            "disposition": disposition,
            "blockers": unique,
            "evaluated_at": now,
        },
    )


def seal_promotion_approval(
    *,
    evidence: PromotionEvidence,
    approved_by_ref: str,
    review_authority_ref: str,
    review_authority_verified: bool,
    approval_evidence_ref: str,
    approved_at: datetime,
    expires_at: datetime,
) -> PromotionApproval:
    evidence = PromotionEvidence.model_validate(evidence.model_dump(mode="json"))
    if evidence.disposition is not PromotionDisposition.REVIEW_READY:
        raise ValueError("canary_promotion_evidence_not_review_ready")
    return _seal(
        PromotionApproval,
        "approval_fingerprint",
        {
            "evidence_fingerprint": evidence.evidence_fingerprint,
            "tenant_id": evidence.tenant_id,
            "company_id": evidence.company_id,
            "problem_class": evidence.problem_class,
            "rollout_id": evidence.rollout_id,
            "generation": evidence.generation,
            "candidate_fingerprint": evidence.candidate_fingerprint,
            "baseline_fingerprint": evidence.baseline_fingerprint,
            "approved_by_ref": approved_by_ref,
            "review_authority_ref": review_authority_ref,
            "review_authority_verified": review_authority_verified,
            "approval_evidence_ref": approval_evidence_ref,
            "approved_at": approved_at,
            "expires_at": expires_at,
        },
    )


def review_promotion(
    *,
    snapshot: RolloutSnapshot,
    evidence: PromotionEvidence,
    approval: PromotionApproval,
    reviewed_at: datetime,
) -> PromotionReviewReceipt:
    snapshot = RolloutSnapshot.model_validate(snapshot.model_dump(mode="json"))
    evidence = PromotionEvidence.model_validate(evidence.model_dump(mode="json"))
    approval = PromotionApproval.model_validate(approval.model_dump(mode="json"))
    now = _utc(reviewed_at, "reviewed_at")

    if snapshot.state is not RolloutState.ACTIVE:
        raise ValueError("canary_promotion_review_requires_active_rollout")
    if evidence.disposition is not PromotionDisposition.REVIEW_READY:
        raise ValueError("canary_promotion_review_evidence_not_ready")
    if now > _utc(approval.expires_at, "expires_at"):
        raise ValueError("canary_promotion_review_approval_expired")

    expected = (
        snapshot.identity.tenant_id,
        snapshot.identity.company_id,
        snapshot.identity.problem_class,
        snapshot.identity.rollout_id,
        snapshot.generation,
        snapshot.candidate_fingerprint,
        snapshot.baseline_fingerprint,
    )
    evidence_identity = (
        evidence.tenant_id,
        evidence.company_id,
        evidence.problem_class,
        evidence.rollout_id,
        evidence.generation,
        evidence.candidate_fingerprint,
        evidence.baseline_fingerprint,
    )
    approval_identity = (
        approval.tenant_id,
        approval.company_id,
        approval.problem_class,
        approval.rollout_id,
        approval.generation,
        approval.candidate_fingerprint,
        approval.baseline_fingerprint,
    )
    if evidence_identity != expected:
        raise ValueError("canary_promotion_review_evidence_identity_mismatch")
    if approval_identity != expected:
        raise ValueError("canary_promotion_review_approval_identity_mismatch")
    if approval.evidence_fingerprint != evidence.evidence_fingerprint:
        raise ValueError("canary_promotion_review_evidence_fingerprint_mismatch")

    return _seal(
        PromotionReviewReceipt,
        "receipt_fingerprint",
        {
            "evidence_fingerprint": evidence.evidence_fingerprint,
            "approval_fingerprint": approval.approval_fingerprint,
            "tenant_id": evidence.tenant_id,
            "company_id": evidence.company_id,
            "problem_class": evidence.problem_class,
            "rollout_id": evidence.rollout_id,
            "generation": evidence.generation,
            "candidate_fingerprint": evidence.candidate_fingerprint,
            "baseline_fingerprint": evidence.baseline_fingerprint,
            "reviewed_at": now,
        },
    )
