"""Governed Device World Model for EAY Jarvis.

This is an evidence-bound inventory of devices Jarvis may reason about. It does
not discover credentials, grant authority or execute device commands. Exact
tenant, trust, freshness and capability must be proven before a device can be
selected for a later governed operation.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field, model_validator

DEVICE_WORLD_MODEL_CONTRACT = "eay-device-world-model-v1"


class DeviceClass(str, Enum):
    DESKTOP = "desktop"
    LAPTOP = "laptop"
    TABLET = "tablet"
    PHONE = "phone"
    MEETING_DISPLAY = "meeting_display"
    ZEBRA_TERMINAL = "zebra_terminal"
    TV = "tv"
    PRINTER = "printer"
    CAMERA = "camera"
    IOT = "iot"
    ROBOT = "robot"


class DeviceTrust(str, Enum):
    UNTRUSTED = "untrusted"
    REGISTERED = "registered"
    MANAGED = "managed"
    ATTESTED = "attested"


class DeviceCapability(str, Enum):
    DISPLAY_ARTIFACT = "display_artifact"
    RECEIVE_DOCUMENT = "receive_document"
    RECEIVE_LINK = "receive_link"
    RECEIVE_PLANOGRAM = "receive_planogram"
    PRESENT_DASHBOARD = "present_dashboard"
    BARCODE_SCAN = "barcode_scan"
    CAMERA_OBSERVATION = "camera_observation"
    PRINT = "print"
    POINTER_INPUT = "pointer_input"
    IOT_SETPOINT = "iot_setpoint"
    ROBOTIC_ACTUATION = "robotic_actuation"


_TRUST_ORDER = {
    DeviceTrust.UNTRUSTED: 0,
    DeviceTrust.REGISTERED: 1,
    DeviceTrust.MANAGED: 2,
    DeviceTrust.ATTESTED: 3,
}


class DeviceNode(BaseModel):
    device_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    device_class: DeviceClass
    trust: DeviceTrust
    identity_evidence_ref: str | None = None
    capabilities: frozenset[DeviceCapability] = frozenset()
    transport_refs: tuple[str, ...] = ()
    room_ref: str | None = None
    online: bool = False
    observed_at: datetime
    attestation_expires_at: datetime | None = None
    raw_network_data_retained: bool = False
    credential_material_retained: bool = False

    @model_validator(mode="after")
    def device_evidence_is_safe(self) -> "DeviceNode":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("device_world_node_requires_timezone")
        if self.attestation_expires_at is not None:
            if self.attestation_expires_at.tzinfo is None or self.attestation_expires_at.utcoffset() is None:
                raise ValueError("device_world_attestation_requires_timezone")
        if self.trust in {DeviceTrust.MANAGED, DeviceTrust.ATTESTED} and not self.identity_evidence_ref:
            raise ValueError("device_world_managed_device_requires_identity_evidence")
        if self.raw_network_data_retained or self.credential_material_retained:
            raise ValueError("device_world_model_cannot_retain_sensitive_transport_material")
        return self


class DeviceWorldSnapshot(BaseModel):
    contract: str = DEVICE_WORLD_MODEL_CONTRACT
    tenant_ref: str = Field(min_length=1)
    observed_at: datetime
    devices: tuple[DeviceNode, ...]
    source_evidence_refs: tuple[str, ...] = Field(min_length=1)
    business_side_effects_authorized: bool = False

    @model_validator(mode="after")
    def snapshot_is_tenant_bound(self) -> "DeviceWorldSnapshot":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("device_world_snapshot_requires_timezone")
        refs = [item.device_ref for item in self.devices]
        if len(refs) != len(set(refs)):
            raise ValueError("device_world_duplicate_device_ref")
        if any(item.tenant_ref != self.tenant_ref for item in self.devices):
            raise ValueError("device_world_cross_tenant_device_forbidden")
        if self.business_side_effects_authorized:
            raise ValueError("device_world_model_never_authorizes_business_side_effects")
        return self


class DeviceResolution(BaseModel):
    contract: str = DEVICE_WORLD_MODEL_CONTRACT
    device: DeviceNode | None = None
    blockers: tuple[str, ...] = ()
    execution_authorized: bool = False

    @model_validator(mode="after")
    def resolution_is_observation_only(self) -> "DeviceResolution":
        if self.execution_authorized:
            raise ValueError("device_world_resolution_never_authorizes_execution")
        if self.device is not None and self.blockers:
            raise ValueError("device_world_resolution_cannot_return_device_with_blockers")
        return self


def resolve_device(
    *,
    snapshot: DeviceWorldSnapshot,
    now: datetime,
    device_ref: str | None = None,
    room_ref: str | None = None,
    capability: DeviceCapability,
    minimum_trust: DeviceTrust = DeviceTrust.MANAGED,
    maximum_observation_age: timedelta = timedelta(minutes=5),
) -> DeviceResolution:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("device_world_resolution_requires_timezone")
    candidates = list(snapshot.devices)
    if device_ref is not None:
        candidates = [item for item in candidates if item.device_ref == device_ref]
    if room_ref is not None:
        candidates = [item for item in candidates if item.room_ref == room_ref]
    candidates = [item for item in candidates if capability in item.capabilities]

    blockers: list[str] = []
    if len(candidates) == 0:
        blockers.append("device_world_matching_device_missing")
    elif len(candidates) > 1:
        blockers.append("device_world_target_ambiguous")
    else:
        device = candidates[0]
        if not device.online:
            blockers.append("device_world_target_offline")
        if _TRUST_ORDER[device.trust] < _TRUST_ORDER[minimum_trust]:
            blockers.append("device_world_target_trust_insufficient")
        if now - device.observed_at > maximum_observation_age:
            blockers.append("device_world_observation_stale")
        if device.trust is DeviceTrust.ATTESTED and (
            device.attestation_expires_at is None or now > device.attestation_expires_at
        ):
            blockers.append("device_world_attestation_expired")
        if not device.transport_refs:
            blockers.append("device_world_verified_transport_missing")
        if not blockers:
            return DeviceResolution(device=device)
    return DeviceResolution(blockers=tuple(dict.fromkeys(blockers)))
