from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.core.mobile_policy import (
    MobileDeviceTrust,
    MobileIntegrityVerdict,
    MobilePolicyDenied,
    MobileRisk,
    MobileRuntimeProfile,
    VerifiedMobileDeviceContext,
    build_mobile_policy_snapshot,
)
from app.core.permission_catalog import action_permission, feature_permission, module_permission
from app.core.security import PermissionAssignment, Principal

TENANT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=UTC)


def permission(key: str, scope: dict[str, object] | None = None) -> PermissionAssignment:
    return PermissionAssignment(
        key=key,
        role_key="field_worker",
        scope=scope or {"warehouses": ["store-1"]},
    )


def principal(*assignments: PermissionAssignment) -> Principal:
    return Principal(
        subject="actor-a",
        tenant_id=TENANT,
        roles=("field_worker",),
        permissions=tuple(sorted({item.key for item in assignments})),
        permission_assignments=tuple(assignments),
        auth_mode="oidc",
    )


def device(
    *,
    tenant_id: UUID = TENANT,
    location_id: str = "store-1",
    trust: MobileDeviceTrust = MobileDeviceTrust.HARDWARE_BOUND,
    integrity: MobileIntegrityVerdict = MobileIntegrityVerdict.PASS,
    profile: MobileRuntimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
    active_shift_id: str | None = "shift-1",
    verified_at: datetime = NOW,
    auth_binding_id: str = "auth-1",
) -> VerifiedMobileDeviceContext:
    return VerifiedMobileDeviceContext(
        tenant_id=tenant_id,
        device_id="device-1",
        installation_id="installation-1",
        location_id=location_id,
        auth_binding_id=auth_binding_id,
        runtime_profile=profile,
        trust_level=trust,
        integrity_verdict=integrity,
        active_shift_id=active_shift_id,
        verified_at=verified_at,
    )


def test_cross_tenant_device_binding_fails_closed() -> None:
    actor = principal(permission(module_permission("inventory")))
    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_TENANT_BINDING"):
        build_mobile_policy_snapshot(actor, device(tenant_id=OTHER_TENANT), now=NOW)


def test_stale_or_future_device_context_fails_closed() -> None:
    actor = principal(permission(module_permission("inventory")))
    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_CONTEXT_STALE"):
        build_mobile_policy_snapshot(
            actor,
            device(verified_at=NOW - timedelta(seconds=61)),
            now=NOW,
        )
    with pytest.raises(MobilePolicyDenied, match="DENY_DEVICE_CONTEXT_FUTURE"):
        build_mobile_policy_snapshot(
            actor,
            device(verified_at=NOW + timedelta(seconds=6)),
            now=NOW,
        )


def test_location_scope_is_not_reinterpreted_permissively() -> None:
    actor = principal(
        permission(module_permission("inventory"), {"warehouses": ["store-2"]})
    )
    snapshot = build_mobile_policy_snapshot(actor, device(location_id="store-1"), now=NOW)
    assert "inventory.count.capture" not in snapshot.operation_policies

    indirect = principal(
        permission(module_permission("inventory"), {"regions": ["TR-34"]})
    )
    indirect_snapshot = build_mobile_policy_snapshot(indirect, device(), now=NOW)
    assert "inventory.count.capture" not in indirect_snapshot.operation_policies


def test_server_rule_owns_risk_and_device_requirement() -> None:
    actor = principal(permission(module_permission("inventory")))
    registered = build_mobile_policy_snapshot(
        actor,
        device(trust=MobileDeviceTrust.REGISTERED),
        now=NOW,
    )
    assert "inventory.count.capture" not in registered.operation_policies

    managed = build_mobile_policy_snapshot(
        actor,
        device(trust=MobileDeviceTrust.MANAGED),
        now=NOW,
    )
    assert managed.operation_policies["inventory.count.capture"].risk == MobileRisk.MEDIUM
    assert "inventory.count.submit" not in managed.operation_policies

    hardware = build_mobile_policy_snapshot(actor, device(), now=NOW)
    assert hardware.operation_policies["inventory.count.submit"].risk == MobileRisk.HIGH


def test_high_risk_requires_integrity_pass() -> None:
    actor = principal(permission(feature_permission("workforce", "attendance")))
    snapshot = build_mobile_policy_snapshot(
        actor,
        device(integrity=MobileIntegrityVerdict.UNKNOWN),
        now=NOW,
    )
    assert "workforce.shift.start" not in snapshot.operation_policies


def test_shift_requirement_is_per_operation_not_global() -> None:
    actor = principal(
        permission(feature_permission("workforce", "attendance")),
        permission(action_permission("jarvis", "ask"), {"type": "all"}),
    )
    snapshot = build_mobile_policy_snapshot(
        actor,
        device(profile=MobileRuntimeProfile.EAY_ONE, active_shift_id=None),
        now=NOW,
    )
    assert "workforce.shift.start" in snapshot.operation_policies
    assert "workforce.shift.end" not in snapshot.operation_policies
    assert "jarvis.ask" in snapshot.operation_policies


def test_offline_allowlist_is_server_owned_and_critical_is_never_offline() -> None:
    actor = principal(
        permission(module_permission("inventory")),
        permission(action_permission("inventory", "acceptFieldEvidence")),
    )
    snapshot = build_mobile_policy_snapshot(actor, device(), now=NOW)
    assert snapshot.operation_policies["inventory.count.capture"].offline_allowed is True
    assert snapshot.operation_policies["inventory.count.submit"].offline_allowed is False
    assert snapshot.operation_policies["inventory.count.approve"].offline_allowed is False


def test_policy_fingerprint_binds_auth_session_and_is_deterministic() -> None:
    actor = principal(permission(module_permission("inventory")))
    first = build_mobile_policy_snapshot(actor, device(), now=NOW)
    same = build_mobile_policy_snapshot(actor, device(), now=NOW)
    rotated = build_mobile_policy_snapshot(
        actor,
        device(auth_binding_id="auth-2"),
        now=NOW,
    )
    assert first.policy_fingerprint == same.policy_fingerprint
    assert first.policy_fingerprint != rotated.policy_fingerprint


def test_policy_ttl_is_bounded() -> None:
    actor = principal(permission(module_permission("inventory")))
    with pytest.raises(MobilePolicyDenied, match="DENY_POLICY_TTL"):
        build_mobile_policy_snapshot(actor, device(), now=NOW, ttl_seconds=301)
