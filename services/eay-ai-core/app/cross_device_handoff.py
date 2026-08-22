"""Governed cross-device artifact handoff for Jarvis.

A handoff transfers an opaque artifact reference through an approved transport;
it does not move arbitrary process memory, cookies, credentials or a native OS
window between incompatible devices. The target must come from the Device World
Model, match the tenant, be fresh/trusted/online and support the requested
artifact class. Transport acknowledgement is verified before completion.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .device_world_model import DeviceCapability, DeviceNode, DeviceTrust, DeviceWorldSnapshot, resolve_device

CROSS_DEVICE_HANDOFF_CONTRACT = "eay-cross-device-handoff-v1"


class ArtifactClass(str, Enum):
    DOCUMENT = "document"
    DASHBOARD_VIEW = "dashboard_view"
    PLANOGRAM_VIEW = "planogram_view"
    LINK = "link"
    IMAGE = "image"
    REPORT = "report"


class ArtifactSensitivity(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class HandoffPolicy(BaseModel):
    policy_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    source_device_ref: str = Field(min_length=1)
    allowed_artifact_classes: frozenset[ArtifactClass] = Field(min_length=1)
    valid_from: datetime
    valid_until: datetime
    maximum_sensitivity: ArtifactSensitivity = ArtifactSensitivity.INTERNAL
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def policy_is_bounded(self) -> "HandoffPolicy":
        for value in (self.valid_from, self.valid_until):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError("cross_device_policy_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("cross_device_policy_expiry_invalid")
        if self.valid_until - self.valid_from > timedelta(hours=12):
            raise ValueError("cross_device_policy_too_long")
        if self.business_side_effects_authorized:
            raise ValueError("cross_device_policy_never_authorizes_business_side_effects")
        return self


class HandoffRequest(BaseModel):
    contract: str = CROSS_DEVICE_HANDOFF_CONTRACT
    request_ref: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    source_device_ref: str = Field(min_length=1)
    target_device_ref: str = Field(min_length=1)
    artifact_ref: str = Field(min_length=1)
    artifact_class: ArtifactClass
    sensitivity: ArtifactSensitivity
    requested_at: datetime
    artifact_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    idempotency_key: str = Field(min_length=16)
    raw_artifact_retained: bool = False
    credentials_retained: bool = False

    @model_validator(mode="after")
    def request_is_reference_only(self) -> "HandoffRequest":
        if self.requested_at.tzinfo is None or self.requested_at.utcoffset() is None:
            raise ValueError("cross_device_request_requires_timezone")
        if self.raw_artifact_retained or self.credentials_retained:
            raise ValueError("cross_device_request_cannot_retain_sensitive_payload")
        return self


class HandoffPreflight(BaseModel):
    contract: str = CROSS_DEVICE_HANDOFF_CONTRACT
    request_ref: str
    target_device: DeviceNode | None = None
    transport_ref: str | None = None
    permitted: bool = False
    blockers: tuple[str, ...] = ()
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def preflight_is_consistent(self) -> "HandoffPreflight":
        if self.permitted and (self.blockers or self.target_device is None or self.transport_ref is None):
            raise ValueError("cross_device_preflight_invalid_permit")
        if self.business_side_effects_authorized:
            raise ValueError("cross_device_handoff_never_authorizes_business_side_effects")
        return self


class TransportAck(BaseModel):
    transport_ref: str
    transaction_ref: str = Field(min_length=1)
    target_device_ref: str
    artifact_digest: str
    accepted: bool
    observed_at: datetime


class HandoffReceipt(BaseModel):
    contract: str = CROSS_DEVICE_HANDOFF_CONTRACT
    request_ref: str
    target_device_ref: str
    transport_ref: str
    transaction_ref: str
    artifact_digest: str
    authoritative_ack_verified: bool
    completed: bool
    raw_artifact_retained: bool = False
    credential_material_retained: bool = False
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def receipt_requires_verified_ack(self) -> "HandoffReceipt":
        if self.completed and not self.authoritative_ack_verified:
            raise ValueError("cross_device_completion_requires_verified_ack")
        if self.raw_artifact_retained or self.credential_material_retained:
            raise ValueError("cross_device_receipt_cannot_retain_sensitive_payload")
        if self.business_side_effects_authorized:
            raise ValueError("cross_device_receipt_never_authorizes_business_side_effects")
        return self


class HandoffTransport(Protocol):
    def send_reference(self, request: HandoffRequest, *, transport_ref: str) -> TransportAck: ...


_SENSITIVITY = {
    ArtifactSensitivity.PUBLIC: 0,
    ArtifactSensitivity.INTERNAL: 1,
    ArtifactSensitivity.CONFIDENTIAL: 2,
    ArtifactSensitivity.RESTRICTED: 3,
}


def _required_capability(artifact_class: ArtifactClass) -> DeviceCapability:
    if artifact_class is ArtifactClass.PLANOGRAM_VIEW:
        return DeviceCapability.RECEIVE_PLANOGRAM
    if artifact_class is ArtifactClass.DASHBOARD_VIEW:
        return DeviceCapability.PRESENT_DASHBOARD
    if artifact_class is ArtifactClass.DOCUMENT:
        return DeviceCapability.RECEIVE_DOCUMENT
    return DeviceCapability.DISPLAY_ARTIFACT


def preflight_handoff(
    *,
    request: HandoffRequest,
    policy: HandoffPolicy,
    world: DeviceWorldSnapshot,
    now: datetime,
) -> HandoffPreflight:
    blockers: list[str] = []
    if request.principal_ref != policy.principal_ref or request.identity_evidence_ref != policy.identity_evidence_ref:
        blockers.append("cross_device_identity_mismatch")
    if request.tenant_ref != policy.tenant_ref or world.tenant_ref != policy.tenant_ref:
        blockers.append("cross_device_tenant_mismatch")
    if request.source_device_ref != policy.source_device_ref:
        blockers.append("cross_device_source_device_mismatch")
    if not (policy.valid_from <= request.requested_at <= policy.valid_until):
        blockers.append("cross_device_request_outside_policy_window")
    if request.artifact_class not in policy.allowed_artifact_classes:
        blockers.append("cross_device_artifact_class_not_allowed")
    if _SENSITIVITY[request.sensitivity] > _SENSITIVITY[policy.maximum_sensitivity]:
        blockers.append("cross_device_artifact_sensitivity_exceeds_policy")

    minimum_trust = (
        DeviceTrust.ATTESTED
        if request.sensitivity in {ArtifactSensitivity.CONFIDENTIAL, ArtifactSensitivity.RESTRICTED}
        else DeviceTrust.MANAGED
    )
    resolution = resolve_device(
        snapshot=world,
        now=now,
        device_ref=request.target_device_ref,
        capability=_required_capability(request.artifact_class),
        minimum_trust=minimum_trust,
    )
    blockers.extend(resolution.blockers)
    if blockers or resolution.device is None:
        return HandoffPreflight(request_ref=request.request_ref, blockers=tuple(dict.fromkeys(blockers)))
    device = resolution.device
    return HandoffPreflight(
        request_ref=request.request_ref,
        target_device=device,
        transport_ref=device.transport_refs[0],
        permitted=True,
    )


def execute_handoff(
    *,
    request: HandoffRequest,
    preflight: HandoffPreflight,
    transport: HandoffTransport,
) -> HandoffReceipt:
    if not preflight.permitted or preflight.target_device is None or preflight.transport_ref is None:
        raise ValueError("cross_device_handoff_preflight_not_permitted")
    if preflight.request_ref != request.request_ref:
        raise ValueError("cross_device_handoff_preflight_request_mismatch")
    ack = transport.send_reference(request, transport_ref=preflight.transport_ref)
    verified = (
        ack.accepted
        and ack.transport_ref == preflight.transport_ref
        and ack.target_device_ref == request.target_device_ref
        and ack.artifact_digest == request.artifact_digest
    )
    if not verified:
        raise RuntimeError("cross_device_handoff_authoritative_ack_mismatch")
    return HandoffReceipt(
        request_ref=request.request_ref,
        target_device_ref=request.target_device_ref,
        transport_ref=ack.transport_ref,
        transaction_ref=ack.transaction_ref,
        artifact_digest=request.artifact_digest,
        authoritative_ack_verified=True,
        completed=True,
    )


def make_handoff_request(
    *,
    request_ref: str,
    principal_ref: str,
    identity_evidence_ref: str,
    tenant_ref: str,
    source_device_ref: str,
    target_device_ref: str,
    artifact_ref: str,
    artifact_class: ArtifactClass,
    sensitivity: ArtifactSensitivity,
    requested_at: datetime,
    artifact_digest: str,
) -> HandoffRequest:
    key = hashlib.sha256(
        f"{tenant_ref}|{source_device_ref}|{target_device_ref}|{artifact_ref}|{artifact_digest}".encode("utf-8")
    ).hexdigest()
    return HandoffRequest(
        request_ref=request_ref,
        principal_ref=principal_ref,
        identity_evidence_ref=identity_evidence_ref,
        tenant_ref=tenant_ref,
        source_device_ref=source_device_ref,
        target_device_ref=target_device_ref,
        artifact_ref=artifact_ref,
        artifact_class=artifact_class,
        sensitivity=sensitivity,
        requested_at=requested_at,
        artifact_digest=artifact_digest,
        idempotency_key=key,
    )
