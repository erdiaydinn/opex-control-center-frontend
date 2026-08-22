from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.mobile_device_trust import (
    MobileDeviceRegistryRecord,
    MobileDeviceState,
    ServerVerifiedMobileEvidence,
    derive_verified_mobile_device_context,
)
from app.core.mobile_policy import (
    MobileDeviceTrust,
    MobileIntegrityVerdict,
    MobilePolicyDenied,
    MobileRuntimeProfile,
)
from app.core.security import Principal

TENANT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def principal(tenant_id: UUID = TENANT) -> Principal:
    return Principal(
        subject="actor-a",
        tenant_id=tenant_id,
        roles=("field_worker",),
        permissions=(),
        permission_assignments=(),
        auth_mode="oidc",
    )


def registry(**changes) -> MobileDeviceRegistryRecord:
    values = {
        "tenant_id": TENANT,
        "device_id": "device-1",
        "installation_id": "install-1",
        "assigned_actor_id": "actor-a",
        "runtime_profile": MobileRuntimeProfile.EAY_TERMINAL,
        "trust_level": MobileDeviceTrust.HARDWARE_BOUND,
        "allowed_location_ids": frozenset({"store-1"}),
        "public_key_thumbprint": "a" * 64,
        "state": MobileDeviceState.ACTIVE,
    }
    values.update(changes)
    return MobileDeviceRegistryRecord(**values)


def evidence(**changes) -> ServerVerifiedMobileEvidence:
    values = {
        "tenant_id": TENANT,
        "actor_id": "actor-a",
        "device_id": "device-1",
        "installation_id": "install-1",
        "location_id": "store-1",
        "auth_binding_id": "auth-1",
        "runtime_profile": MobileRuntimeProfile.EAY_TERMINAL,
        "request_proof_verified": True,
        "request_proof_verified_at": NOW,
        "integrity_verdict": MobileIntegrityVerdict.PASS,
        "integrity_verified_at": NOW,
        "active_shift_id": "shift-1",
    }
    values.update(changes)
    return ServerVerifiedMobileEvidence(**values)


def test_active_exactly_bound_device_derives_verified_context() -> None:
    context = derive_verified_mobile_device_context(
        principal(),
        registry(),
        evidence(),
        now=NOW,
    )
    assert context.device_id == "device-1"
    assert context.installation_id == "install-1"
    assert context.integrity_verdict == MobileIntegrityVerdict.PASS


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (MobileDeviceState.REVOKED, "DENY_DEVICE_NOT_ACTIVE"),
        (MobileDeviceState.LOST, "DENY_DEVICE_NOT_ACTIVE"),
        (MobileDeviceState.REPLACED, "DENY_DEVICE_NOT_ACTIVE"),
    ],
)
def test_revoked_lost_or_replaced_device_fails_closed(state, code) -> None:
    with pytest.raises(MobilePolicyDenied, match=code):
        derive_verified_mobile_device_context(
            principal(),
            registry(state=state),
            evidence(),
            now=NOW,
        )


def test_cross_tenant_or_actor_replay_fails_closed() -> None:
    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_TENANT_BINDING"):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(tenant_id=OTHER_TENANT),
            now=NOW,
        )

    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_ACTOR_BINDING"):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(actor_id="actor-b"),
            now=NOW,
        )


def test_reinstalled_or_wrong_location_device_fails_closed() -> None:
    with pytest.raises(
        MobilePolicyDenied,
        match="DENY_DEVICE_INSTALLATION_BINDING",
    ):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(installation_id="install-2"),
            now=NOW,
        )

    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_LOCATION_BINDING"):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(location_id="store-2"),
            now=NOW,
        )


def test_unverified_or_stale_request_proof_fails_closed() -> None:
    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_REQUEST_PROOF"):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(request_proof_verified=False),
            now=NOW,
        )

    with pytest.raises(
        MobilePolicyDenied,
        match="DENY_DEVICE_REQUEST_PROOF_STALE",
    ):
        derive_verified_mobile_device_context(
            principal(),
            registry(),
            evidence(request_proof_verified_at=NOW - timedelta(seconds=61)),
            now=NOW,
        )


def test_stale_integrity_is_downgraded_not_reused_as_pass() -> None:
    context = derive_verified_mobile_device_context(
        principal(),
        registry(),
        evidence(integrity_verified_at=NOW - timedelta(seconds=301)),
        now=NOW,
    )
    assert context.integrity_verdict == MobileIntegrityVerdict.UNKNOWN
