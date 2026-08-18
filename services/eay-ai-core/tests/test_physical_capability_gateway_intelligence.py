import hashlib
from datetime import datetime, timedelta, timezone

import pytest

from app.device_world_model import (
    DeviceCapability,
    DeviceClass,
    DeviceNode,
    DeviceTrust,
    DeviceWorldSnapshot,
)
from app.physical_capability_gateway import (
    PhysicalAction,
    PhysicalActionPolicy,
    PhysicalApproval,
    PhysicalExecutionEvidence,
    PhysicalRisk,
    execute_physical_action,
    make_physical_request,
    preflight_physical_action,
)

NOW = datetime(2026, 8, 18, 12, 20, tzinfo=timezone.utc)


def _device(*, action="display", trust=DeviceTrust.MANAGED):
    capabilities = {
        "display": frozenset({DeviceCapability.DISPLAY_ARTIFACT}),
        "print": frozenset({DeviceCapability.PRINT}),
        "iot": frozenset({DeviceCapability.IOT_SETPOINT}),
        "robot": frozenset({DeviceCapability.ROBOTIC_ACTUATION}),
    }[action]
    device_class = {
        "display": DeviceClass.MEETING_DISPLAY,
        "print": DeviceClass.PRINTER,
        "iot": DeviceClass.IOT,
        "robot": DeviceClass.ROBOT,
    }[action]
    return DeviceNode(
        device_ref=f"device:{action}",
        tenant_ref="tenant:a",
        device_class=device_class,
        trust=trust,
        identity_evidence_ref=f"identity://device/{action}",
        capabilities=capabilities,
        transport_refs=(f"transport://{action}/1",),
        online=True,
        observed_at=NOW,
        attestation_expires_at=(NOW + timedelta(hours=1)) if trust is DeviceTrust.ATTESTED else None,
    )


def _world(device):
    return DeviceWorldSnapshot(
        tenant_ref="tenant:a",
        observed_at=NOW,
        devices=(device,),
        source_evidence_refs=("evidence://device-world/physical",),
    )


def _policy(device, action, maximum_risk, **updates):
    payload = dict(
        policy_ref="policy:physical-1",
        tenant_ref="tenant:a",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        allowed_device_refs=frozenset({device.device_ref}),
        allowed_actions=frozenset({action}),
        maximum_risk=maximum_risk,
        valid_from=NOW - timedelta(minutes=1),
        valid_until=NOW + timedelta(hours=1),
        maximum_value=100.0,
    )
    payload.update(updates)
    return PhysicalActionPolicy(**payload)


def _request(device, action, risk, **updates):
    payload = dict(
        request_ref=f"physical:{action.value}",
        tenant_ref="tenant:a",
        principal_ref="principal:erdi",
        identity_evidence_ref="identity://erdi/1",
        device_ref=device.device_ref,
        action=action,
        risk=risk,
        requested_at=NOW,
        value=10.0,
        payload_ref="artifact://opaque/1",
        payload_digest=hashlib.sha256(b"opaque").hexdigest(),
    )
    payload.update(updates)
    return make_physical_request(**payload)


def _approval(request):
    return PhysicalApproval(
        approval_ref="approval://physical/1",
        request_ref=request.request_ref,
        approved_by_principal_ref="principal:erdi",
        approval_identity_evidence_ref="identity://erdi/approval",
        approved_at=NOW - timedelta(seconds=10),
        expires_at=NOW + timedelta(minutes=10),
        exact_device_ref=request.device_ref,
        exact_action=request.action,
        maximum_value=25.0,
    )


class _Adapter:
    def __init__(self, *, effect_verified=True, device_ref=None):
        self.effect_verified = effect_verified
        self.device_ref = device_ref
        self.calls = 0

    def execute(self, request):
        self.calls += 1
        return PhysicalExecutionEvidence(
            transaction_ref="transaction://physical/1",
            device_ref=self.device_ref or request.device_ref,
            action=request.action,
            idempotency_key=request.idempotency_key,
            accepted=True,
            authoritative_readback_ref="readback://physical/1" if self.effect_verified else None,
            effect_verified=self.effect_verified,
            observed_at=NOW,
        )


def test_low_risk_display_can_execute_with_policy_and_authoritative_readback():
    device = _device()
    request = _request(device, PhysicalAction.DISPLAY_ARTIFACT, PhysicalRisk.LOW)
    preflight = preflight_physical_action(
        request=request,
        policy=_policy(device, PhysicalAction.DISPLAY_ARTIFACT, PhysicalRisk.LOW),
        world=_world(device),
        now=NOW,
    )
    assert preflight.permitted is True
    assert preflight.approval_required is False
    assert preflight.execution_authorized_by_model is False
    adapter = _Adapter()
    receipt = execute_physical_action(request=request, preflight=preflight, adapter=adapter)
    assert receipt.completed is True
    assert receipt.effect_verified is True
    assert receipt.business_effect_claim_allowed is False
    assert adapter.calls == 1


def test_medium_print_requires_explicit_approval():
    device = _device(action="print")
    request = _request(device, PhysicalAction.PRINT_DOCUMENT, PhysicalRisk.MEDIUM)
    blocked = preflight_physical_action(
        request=request,
        policy=_policy(device, PhysicalAction.PRINT_DOCUMENT, PhysicalRisk.MEDIUM),
        world=_world(device),
        now=NOW,
    )
    assert blocked.permitted is False
    assert "physical_explicit_approval_required" in blocked.blockers

    allowed = preflight_physical_action(
        request=request,
        policy=_policy(device, PhysicalAction.PRINT_DOCUMENT, PhysicalRisk.MEDIUM),
        world=_world(device),
        now=NOW,
        approval=_approval(request),
    )
    assert allowed.permitted is True
    assert allowed.approval_ref == "approval://physical/1"


def test_iot_setpoint_requires_distinct_iot_capability_attestation_and_approval():
    device = _device(action="iot", trust=DeviceTrust.ATTESTED)
    request = _request(device, PhysicalAction.IOT_SETPOINT, PhysicalRisk.HIGH)
    allowed = preflight_physical_action(
        request=request,
        policy=_policy(device, PhysicalAction.IOT_SETPOINT, PhysicalRisk.HIGH),
        world=_world(device),
        now=NOW,
        approval=_approval(request),
    )
    assert allowed.permitted is True


def test_robotic_actuation_cannot_understate_risk_or_derive_authority_from_gesture():
    device = _device(action="robot", trust=DeviceTrust.ATTESTED)
    with pytest.raises(ValueError, match="risk_understated"):
        _request(device, PhysicalAction.ROBOTIC_ACTUATION, PhysicalRisk.HIGH)

    base = _request(device, PhysicalAction.ROBOTIC_ACTUATION, PhysicalRisk.CRITICAL)
    with pytest.raises(ValueError, match="cannot_derive_authority_from_sensor_input"):
        base.model_copy(update={"sensor_or_gesture_authority": True}).model_validate(
            base.model_copy(update={"sensor_or_gesture_authority": True}).model_dump()
        )


def test_wrong_device_readback_or_missing_effect_verification_fails_completion():
    device = _device()
    request = _request(device, PhysicalAction.DISPLAY_ARTIFACT, PhysicalRisk.LOW)
    preflight = preflight_physical_action(
        request=request,
        policy=_policy(device, PhysicalAction.DISPLAY_ARTIFACT, PhysicalRisk.LOW),
        world=_world(device),
        now=NOW,
    )
    with pytest.raises(RuntimeError, match="effect_verification_failed"):
        execute_physical_action(
            request=request,
            preflight=preflight,
            adapter=_Adapter(device_ref="device:other"),
        )
    with pytest.raises(RuntimeError, match="effect_verification_failed"):
        execute_physical_action(
            request=request,
            preflight=preflight,
            adapter=_Adapter(effect_verified=False),
        )
