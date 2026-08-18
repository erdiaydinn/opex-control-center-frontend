"""Governed physical/device capability gateway for Jarvis.

Physical AI must never inherit authority from gaze, gesture, voice or model
confidence. Every action is exact-device, tenant, capability, risk, time and
idempotency bound. Medium/high/critical actions require explicit approval, and
robotic actuation is always critical. Successful execution requires an
adapter-issued transaction plus authoritative read-back evidence.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .device_world_model import (
    DeviceCapability,
    DeviceNode,
    DeviceTrust,
    DeviceWorldSnapshot,
    resolve_device,
)

PHYSICAL_CAPABILITY_GATEWAY_CONTRACT = "eay-physical-capability-gateway-v1"


class PhysicalAction(str, Enum):
    DISPLAY_ARTIFACT = "display_artifact"
    PRINT_DOCUMENT = "print_document"
    CAPTURE_CAMERA_OBSERVATION = "capture_camera_observation"
    IOT_SETPOINT = "iot_setpoint"
    ROBOTIC_ACTUATION = "robotic_actuation"


class PhysicalRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


_RISK_ORDER = {
    PhysicalRisk.LOW: 0,
    PhysicalRisk.MEDIUM: 1,
    PhysicalRisk.HIGH: 2,
    PhysicalRisk.CRITICAL: 3,
}


_ACTION_CAPABILITY = {
    PhysicalAction.DISPLAY_ARTIFACT: DeviceCapability.DISPLAY_ARTIFACT,
    PhysicalAction.PRINT_DOCUMENT: DeviceCapability.PRINT,
    PhysicalAction.CAPTURE_CAMERA_OBSERVATION: DeviceCapability.CAMERA_OBSERVATION,
    PhysicalAction.IOT_SETPOINT: DeviceCapability.IOT_SETPOINT,
    PhysicalAction.ROBOTIC_ACTUATION: DeviceCapability.ROBOTIC_ACTUATION,
}


_MINIMUM_RISK = {
    PhysicalAction.DISPLAY_ARTIFACT: PhysicalRisk.LOW,
    PhysicalAction.PRINT_DOCUMENT: PhysicalRisk.MEDIUM,
    PhysicalAction.CAPTURE_CAMERA_OBSERVATION: PhysicalRisk.MEDIUM,
    PhysicalAction.IOT_SETPOINT: PhysicalRisk.HIGH,
    PhysicalAction.ROBOTIC_ACTUATION: PhysicalRisk.CRITICAL,
}


class PhysicalActionPolicy(BaseModel):
    policy_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    allowed_device_refs: frozenset[str] = Field(min_length=1)
    allowed_actions: frozenset[PhysicalAction] = Field(min_length=1)
    maximum_risk: PhysicalRisk
    valid_from: datetime
    valid_until: datetime
    maximum_value: float | None = Field(default=None, ge=0.0)
    automatic_high_risk_approval_allowed: bool = False

    @model_validator(mode="after")
    def policy_is_bounded(self) -> "PhysicalActionPolicy":
        for value in (self.valid_from, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("physical_policy_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("physical_policy_expiry_invalid")
        if self.valid_until - self.valid_from > timedelta(hours=12):
            raise ValueError("physical_policy_too_long")
        if self.automatic_high_risk_approval_allowed:
            raise ValueError("physical_policy_cannot_auto_approve_high_risk")
        return self


class PhysicalApproval(BaseModel):
    approval_ref: str = Field(min_length=1)
    request_ref: str = Field(min_length=1)
    approved_by_principal_ref: str = Field(min_length=1)
    approval_identity_evidence_ref: str = Field(min_length=1)
    approved_at: datetime
    expires_at: datetime
    exact_device_ref: str = Field(min_length=1)
    exact_action: PhysicalAction
    maximum_value: float | None = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def approval_is_short_lived(self) -> "PhysicalApproval":
        for value in (self.approved_at, self.expires_at):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("physical_approval_requires_timezone")
        if self.expires_at <= self.approved_at:
            raise ValueError("physical_approval_expiry_invalid")
        if self.expires_at - self.approved_at > timedelta(minutes=30):
            raise ValueError("physical_approval_too_long")
        return self


class PhysicalActionRequest(BaseModel):
    contract: str = PHYSICAL_CAPABILITY_GATEWAY_CONTRACT
    request_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    device_ref: str = Field(min_length=1)
    action: PhysicalAction
    risk: PhysicalRisk
    requested_at: datetime
    value: float | None = Field(default=None, ge=0.0)
    payload_ref: str | None = None
    payload_digest: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=16)
    raw_payload_retained: bool = False
    credential_material_retained: bool = False
    sensor_or_gesture_authority: bool = False

    @model_validator(mode="after")
    def request_preserves_authority_boundary(self) -> "PhysicalActionRequest":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("physical_request_requires_timezone")
        if _RISK_ORDER[self.risk] < _RISK_ORDER[_MINIMUM_RISK[self.action]]:
            raise ValueError("physical_request_risk_understated")
        if self.raw_payload_retained or self.credential_material_retained:
            raise ValueError("physical_request_cannot_retain_sensitive_payload")
        if self.sensor_or_gesture_authority:
            raise ValueError("physical_request_cannot_derive_authority_from_sensor_input")
        return self


class PhysicalPreflight(BaseModel):
    contract: str = PHYSICAL_CAPABILITY_GATEWAY_CONTRACT
    request_ref: str
    device: DeviceNode | None = None
    permitted: bool = False
    approval_required: bool = False
    approval_ref: str | None = None
    blockers: tuple[str, ...] = ()
    execution_authorized_by_model: bool = False

    @model_validator(mode="after")
    def preflight_is_consistent(self) -> "PhysicalPreflight":
        if self.execution_authorized_by_model:
            raise ValueError("physical_gateway_model_never_authorizes_execution")
        if self.permitted and (self.device is None or self.blockers):
            raise ValueError("physical_preflight_invalid_permit")
        if self.approval_required and self.permitted and not self.approval_ref:
            raise ValueError("physical_preflight_required_approval_missing")
        return self


class PhysicalExecutionEvidence(BaseModel):
    transaction_ref: str = Field(min_length=1)
    device_ref: str = Field(min_length=1)
    action: PhysicalAction
    idempotency_key: str = Field(min_length=16)
    accepted: bool
    authoritative_readback_ref: str | None = None
    effect_verified: bool = False
    observed_at: datetime


class PhysicalExecutionReceipt(BaseModel):
    contract: str = PHYSICAL_CAPABILITY_GATEWAY_CONTRACT
    request_ref: str
    transaction_ref: str
    device_ref: str
    action: PhysicalAction
    completed: bool
    effect_verified: bool
    authoritative_readback_ref: str
    idempotency_key: str
    business_effect_claim_allowed: bool = False
    raw_payload_retained: bool = False
    credential_material_retained: bool = False

    @model_validator(mode="after")
    def receipt_requires_readback(self) -> "PhysicalExecutionReceipt":
        if self.completed and not self.effect_verified:
            raise ValueError("physical_completion_requires_effect_verification")
        if not self.authoritative_readback_ref:
            raise ValueError("physical_receipt_requires_authoritative_readback")
        if self.business_effect_claim_allowed:
            raise ValueError("physical_gateway_receipt_is_device_effect_only")
        if self.raw_payload_retained or self.credential_material_retained:
            raise ValueError("physical_receipt_cannot_retain_sensitive_payload")
        return self


class PhysicalCapabilityAdapter(Protocol):
    def execute(self, request: PhysicalActionRequest) -> PhysicalExecutionEvidence: ...


def make_physical_request(
    *,
    request_ref: str,
    tenant_ref: str,
    principal_ref: str,
    identity_evidence_ref: str,
    device_ref: str,
    action: PhysicalAction,
    risk: PhysicalRisk,
    requested_at: datetime,
    value: float | None = None,
    payload_ref: str | None = None,
    payload_digest: str | None = None,
) -> PhysicalActionRequest:
    key = hashlib.sha256(
        f"{tenant_ref}|{principal_ref}|{device_ref}|{action.value}|{value}|{payload_ref}|{payload_digest}".encode("utf-8")
    ).hexdigest()
    return PhysicalActionRequest(
        request_ref=request_ref,
        tenant_ref=tenant_ref,
        principal_ref=principal_ref,
        identity_evidence_ref=identity_evidence_ref,
        device_ref=device_ref,
        action=action,
        risk=risk,
        requested_at=requested_at,
        value=value,
        payload_ref=payload_ref,
        payload_digest=payload_digest,
        idempotency_key=key,
    )


def preflight_physical_action(
    *,
    request: PhysicalActionRequest,
    policy: PhysicalActionPolicy,
    world: DeviceWorldSnapshot,
    now: datetime,
    approval: PhysicalApproval | None = None,
) -> PhysicalPreflight:
    blockers: list[str] = []
    if request.tenant_ref != policy.tenant_ref or world.tenant_ref != policy.tenant_ref:
        blockers.append("physical_tenant_mismatch")
    if request.principal_ref != policy.principal_ref or request.identity_evidence_ref != policy.identity_evidence_ref:
        blockers.append("physical_identity_mismatch")
    if request.device_ref not in policy.allowed_device_refs:
        blockers.append("physical_device_not_allowed")
    if request.action not in policy.allowed_actions:
        blockers.append("physical_action_not_allowed")
    if _RISK_ORDER[request.risk] > _RISK_ORDER[policy.maximum_risk]:
        blockers.append("physical_risk_exceeds_policy")
    if not (policy.valid_from <= request.requested_at <= policy.valid_until):
        blockers.append("physical_request_outside_policy_window")
    if policy.maximum_value is not None and request.value is not None and request.value > policy.maximum_value:
        blockers.append("physical_value_exceeds_policy")

    minimum_trust = DeviceTrust.MANAGED
    if request.risk in {PhysicalRisk.HIGH, PhysicalRisk.CRITICAL}:
        minimum_trust = DeviceTrust.ATTESTED
    resolution = resolve_device(
        snapshot=world,
        now=now,
        device_ref=request.device_ref,
        capability=_ACTION_CAPABILITY[request.action],
        minimum_trust=minimum_trust,
    )
    blockers.extend(resolution.blockers)

    approval_required = request.risk is not PhysicalRisk.LOW
    approval_ref: str | None = None
    if approval_required:
        if approval is None:
            blockers.append("physical_explicit_approval_required")
        else:
            if approval.request_ref != request.request_ref:
                blockers.append("physical_approval_request_mismatch")
            if approval.exact_device_ref != request.device_ref or approval.exact_action is not request.action:
                blockers.append("physical_approval_scope_mismatch")
            if not (approval.approved_at <= request.requested_at <= approval.expires_at):
                blockers.append("physical_approval_outside_window")
            if approval.maximum_value is not None and request.value is not None and request.value > approval.maximum_value:
                blockers.append("physical_value_exceeds_approval")
            if not blockers:
                approval_ref = approval.approval_ref

    if blockers or resolution.device is None:
        return PhysicalPreflight(
            request_ref=request.request_ref,
            approval_required=approval_required,
            blockers=tuple(dict.fromkeys(blockers)),
        )
    return PhysicalPreflight(
        request_ref=request.request_ref,
        device=resolution.device,
        permitted=True,
        approval_required=approval_required,
        approval_ref=approval_ref,
    )


def execute_physical_action(
    *,
    request: PhysicalActionRequest,
    preflight: PhysicalPreflight,
    adapter: PhysicalCapabilityAdapter,
) -> PhysicalExecutionReceipt:
    if not preflight.permitted or preflight.device is None:
        raise ValueError("physical_preflight_not_permitted")
    if preflight.request_ref != request.request_ref or preflight.device.device_ref != request.device_ref:
        raise ValueError("physical_preflight_request_or_device_mismatch")
    evidence = adapter.execute(request)
    verified = (
        evidence.accepted
        and evidence.device_ref == request.device_ref
        and evidence.action is request.action
        and evidence.idempotency_key == request.idempotency_key
        and evidence.effect_verified
        and bool(evidence.authoritative_readback_ref)
    )
    if not verified:
        raise RuntimeError("physical_authoritative_effect_verification_failed")
    return PhysicalExecutionReceipt(
        request_ref=request.request_ref,
        transaction_ref=evidence.transaction_ref,
        device_ref=request.device_ref,
        action=request.action,
        completed=True,
        effect_verified=True,
        authoritative_readback_ref=evidence.authoritative_readback_ref or "",
        idempotency_key=request.idempotency_key,
    )
