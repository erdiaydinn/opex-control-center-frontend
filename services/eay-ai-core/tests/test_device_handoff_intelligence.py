import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.cross_device_handoff import (
    ArtifactClass,
    ArtifactSensitivity,
    HandoffPolicy,
    TransportAck,
    execute_handoff,
    make_handoff_request,
    preflight_handoff,
)
from app.device_world_model import (
    DeviceCapability,
    DeviceClass,
    DeviceNode,
    DeviceTrust,
    DeviceWorldSnapshot,
    resolve_device,
)

NOW = datetime(2026, 8, 18, 11, 50, tzinfo=timezone.utc)
DIGEST = hashlib.sha256(b"opaque-artifact-fixture").hexdigest()


def _device(**updates):
    payload = dict(
        device_ref="device:meeting-room-a",
        tenant_ref="tenant:a",
        device_class=DeviceClass.MEETING_DISPLAY,
        trust=DeviceTrust.MANAGED,
        identity_evidence_ref="identity://device/meeting-a",
        capabilities=frozenset({DeviceCapability.DISPLAY_ARTIFACT, DeviceCapability.PRESENT_DASHBOARD}),
        transport_refs=("transport://managed-cast/a",),
        room_ref="room:a",
        online=True,
        observed_at=NOW,
    )
    payload.update(updates)
    return DeviceNode(**payload)


def _world(*devices):
    return DeviceWorldSnapshot(
        tenant_ref="tenant:a",
        observed_at=NOW,
        devices=devices or (_device(),),
        source_evidence_refs=("evidence://mdm/device-world/1",),
    )


def _policy(**updates):
    payload = dict(
        policy_ref="policy:handoff-1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        tenant_ref="tenant:a",
        source_device_ref="device:laptop-erdi",
        allowed_artifact_classes=frozenset({ArtifactClass.DASHBOARD_VIEW, ArtifactClass.PLANOGRAM_VIEW}),
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=1),
        maximum_sensitivity=ArtifactSensitivity.INTERNAL,
    )
    payload.update(updates)
    return HandoffPolicy(**payload)


def _request(**updates):
    payload = dict(
        request_ref="handoff:1",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        tenant_ref="tenant:a",
        source_device_ref="device:laptop-erdi",
        target_device_ref="device:meeting-room-a",
        artifact_ref="artifact://dashboard/ops-1",
        artifact_class=ArtifactClass.DASHBOARD_VIEW,
        sensitivity=ArtifactSensitivity.INTERNAL,
        requested_at=NOW,
        artifact_digest=DIGEST,
    )
    payload.update(updates)
    return make_handoff_request(**payload)


class _Transport:
    def __init__(self, *, digest=DIGEST, target="device:meeting-room-a", accepted=True):
        self.digest = digest
        self.target = target
        self.accepted = accepted
        self.calls = 0

    def send_reference(self, request, *, transport_ref):
        self.calls += 1
        return TransportAck(
            transport_ref=transport_ref,
            transaction_ref="transaction:cast-1",
            target_device_ref=self.target,
            artifact_digest=self.digest,
            accepted=self.accepted,
            observed_at=NOW,
        )


def test_managed_device_world_resolves_exact_fresh_target_without_execution_authority():
    resolution = resolve_device(
        snapshot=_world(),
        now=NOW,
        device_ref="device:meeting-room-a",
        capability=DeviceCapability.PRESENT_DASHBOARD,
    )
    assert resolution.device is not None
    assert resolution.execution_authorized is False
    assert resolution.blockers == ()


def test_stale_offline_and_ambiguous_device_world_fails_closed():
    stale = _device(observed_at=NOW - timedelta(minutes=10))
    resolution = resolve_device(
        snapshot=_world(stale),
        now=NOW,
        device_ref=stale.device_ref,
        capability=DeviceCapability.PRESENT_DASHBOARD,
    )
    assert "device_world_observation_stale" in resolution.blockers

    offline = _device(online=False)
    resolution = resolve_device(
        snapshot=_world(offline),
        now=NOW,
        device_ref=offline.device_ref,
        capability=DeviceCapability.PRESENT_DASHBOARD,
    )
    assert "device_world_target_offline" in resolution.blockers

    second = _device(device_ref="device:meeting-room-b", identity_evidence_ref="identity://device/meeting-b")
    resolution = resolve_device(
        snapshot=_world(_device(), second),
        now=NOW,
        room_ref="room:a",
        capability=DeviceCapability.PRESENT_DASHBOARD,
    )
    assert resolution.device is None
    assert "device_world_target_ambiguous" in resolution.blockers


def test_internal_dashboard_handoff_requires_device_world_and_verified_ack():
    request = _request()
    preflight = preflight_handoff(request=request, policy=_policy(), world=_world(), now=NOW)
    assert preflight.permitted is True
    transport = _Transport()
    receipt = execute_handoff(request=request, preflight=preflight, transport=transport)
    assert receipt.completed is True
    assert receipt.authoritative_ack_verified is True
    assert receipt.raw_artifact_retained is False
    assert receipt.credential_material_retained is False
    assert receipt.business_side_effects_authorized is False
    assert transport.calls == 1


def test_confidential_handoff_requires_attested_target_and_explicit_policy_ceiling():
    request = _request(sensitivity=ArtifactSensitivity.CONFIDENTIAL)
    policy = _policy(maximum_sensitivity=ArtifactSensitivity.CONFIDENTIAL)
    preflight = preflight_handoff(request=request, policy=policy, world=_world(), now=NOW)
    assert preflight.permitted is False
    assert "device_world_target_trust_insufficient" in preflight.blockers

    attested = _device(
        trust=DeviceTrust.ATTESTED,
        attestation_expires_at=NOW + timedelta(hours=1),
    )
    preflight = preflight_handoff(request=request, policy=policy, world=_world(attested), now=NOW)
    assert preflight.permitted is True


def test_forged_transport_ack_never_completes_handoff():
    request = _request()
    preflight = preflight_handoff(request=request, policy=_policy(), world=_world(), now=NOW)
    with pytest.raises(RuntimeError, match="authoritative_ack_mismatch"):
        execute_handoff(
            request=request,
            preflight=preflight,
            transport=_Transport(digest=hashlib.sha256(b"wrong").hexdigest()),
        )


def test_cross_tenant_world_is_rejected_at_model_boundary():
    with pytest.raises(ValueError, match="cross_tenant_device_forbidden"):
        DeviceWorldSnapshot(
            tenant_ref="tenant:a",
            observed_at=NOW,
            devices=(_device(tenant_ref="tenant:b"),),
            source_evidence_refs=("evidence://mdm/1",),
        )
