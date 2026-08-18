"""Fail-closed EAY Mobile policy resolver built on Platform Core authority."""

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.authorization import ResolvedPermissionScope, resolve_permission_scope
from app.core.permission_catalog import action_permission, feature_permission, module_permission
from app.core.security import Principal

MAX_POLICY_TTL_SECONDS = 300
MAX_DEVICE_CONTEXT_AGE_SECONDS = 60
MAX_DEVICE_CONTEXT_FUTURE_SKEW_SECONDS = 5


class MobileRuntimeProfile(StrEnum):
    EAY_ONE = "EAY_ONE"
    EAY_TERMINAL = "EAY_TERMINAL"


class MobileRisk(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MobileDeviceTrust(StrEnum):
    REGISTERED = "REGISTERED"
    MANAGED = "MANAGED"
    HARDWARE_BOUND = "HARDWARE_BOUND"


class MobileIntegrityVerdict(StrEnum):
    UNKNOWN = "UNKNOWN"
    PASS = "PASS"
    FAIL = "FAIL"


class MobilePolicyDenied(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class VerifiedMobileDeviceContext(BaseModel):
    """Server-verified context; this model must never be built from raw client authority."""

    tenant_id: UUID
    device_id: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=128)
    auth_binding_id: str = Field(min_length=1, max_length=128)
    runtime_profile: MobileRuntimeProfile
    trust_level: MobileDeviceTrust
    integrity_verdict: MobileIntegrityVerdict
    active_shift_id: str | None = Field(default=None, max_length=128)
    verified_at: datetime


class MobileOperationPolicy(BaseModel):
    operation: str
    risk: MobileRisk
    offline_allowed: bool
    requires_active_shift: bool
    permission_key: str
    scope_fingerprint: str


class MobilePolicySnapshot(BaseModel):
    tenant_id: UUID
    actor_id: str
    device_id: str
    installation_id: str
    location_id: str
    auth_binding_id: str
    runtime_profile: MobileRuntimeProfile
    operation_policies: dict[str, MobileOperationPolicy]
    issued_at: datetime
    expires_at: datetime
    policy_fingerprint: str


@dataclass(frozen=True)
class MobileOperationRule:
    operation: str
    permission_key: str
    risk: MobileRisk
    profiles: frozenset[MobileRuntimeProfile]
    offline_allowed: bool
    requires_active_shift: bool


BOTH_PROFILES = frozenset(
    {MobileRuntimeProfile.EAY_ONE, MobileRuntimeProfile.EAY_TERMINAL}
)

MOBILE_OPERATION_RULES = (
    MobileOperationRule(
        operation="workforce.shift.start",
        permission_key=feature_permission("workforce", "attendance"),
        risk=MobileRisk.HIGH,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=False,
    ),
    MobileOperationRule(
        operation="workforce.shift.end",
        permission_key=feature_permission("workforce", "attendance"),
        risk=MobileRisk.HIGH,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="workforce.break.start",
        permission_key=feature_permission("workforce", "attendance"),
        risk=MobileRisk.MEDIUM,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="workforce.break.end",
        permission_key=feature_permission("workforce", "attendance"),
        risk=MobileRisk.MEDIUM,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="inventory.count.capture",
        permission_key=module_permission("inventory"),
        risk=MobileRisk.MEDIUM,
        profiles=frozenset({MobileRuntimeProfile.EAY_TERMINAL}),
        offline_allowed=True,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="inventory.count.submit",
        permission_key=module_permission("inventory"),
        risk=MobileRisk.HIGH,
        profiles=frozenset({MobileRuntimeProfile.EAY_TERMINAL}),
        offline_allowed=False,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="inventory.count.approve",
        permission_key=action_permission("inventory", "acceptFieldEvidence"),
        risk=MobileRisk.CRITICAL,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=False,
    ),
    MobileOperationRule(
        operation="picking.execute",
        permission_key=feature_permission("workforce", "pickerApp"),
        risk=MobileRisk.MEDIUM,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="field.mission.capture",
        permission_key=action_permission("field_intelligence", "submitEvidence"),
        risk=MobileRisk.MEDIUM,
        profiles=BOTH_PROFILES,
        offline_allowed=True,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="planogram.capture",
        permission_key=feature_permission("planogram", "layoutView"),
        risk=MobileRisk.MEDIUM,
        profiles=BOTH_PROFILES,
        offline_allowed=True,
        requires_active_shift=True,
    ),
    MobileOperationRule(
        operation="jarvis.ask",
        permission_key=action_permission("jarvis", "ask"),
        risk=MobileRisk.LOW,
        profiles=BOTH_PROFILES,
        offline_allowed=False,
        requires_active_shift=False,
    ),
)

_LOCATION_DIMENSIONS = frozenset(
    {
        "warehouse",
        "warehouses",
        "warehouse_ids",
        "location",
        "locations",
        "location_ids",
        "store",
        "stores",
        "store_ids",
    }
)

_TRUST_RANK = {
    MobileDeviceTrust.REGISTERED: 1,
    MobileDeviceTrust.MANAGED: 2,
    MobileDeviceTrust.HARDWARE_BOUND: 3,
}


def _risk_allowed(device: VerifiedMobileDeviceContext, risk: MobileRisk) -> bool:
    if risk == MobileRisk.LOW:
        return _TRUST_RANK[device.trust_level] >= 1
    if risk == MobileRisk.MEDIUM:
        return _TRUST_RANK[device.trust_level] >= 2
    return (
        _TRUST_RANK[device.trust_level] >= 3
        and device.integrity_verdict == MobileIntegrityVerdict.PASS
    )


def _scope_allows_location(scope: ResolvedPermissionScope, location_id: str) -> bool:
    if scope.unrestricted:
        return True

    for dimension, values in scope.dimensions.items():
        if dimension in _LOCATION_DIMENSIONS and location_id in values:
            return True

    # A region/cost-center/other indirect scope cannot be translated into location
    # authority here without a canonical server-side relation. Fail closed instead.
    return False


def _scope_fingerprint(scope: ResolvedPermissionScope) -> str:
    canonical = {
        "permission_key": scope.permission_key,
        "unrestricted": scope.unrestricted,
        "dimensions": {
            key: sorted(values)
            for key, values in sorted(scope.dimensions.items())
        },
        "role_keys": sorted(scope.role_keys),
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _policy_fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_device_context(
    principal: Principal,
    device: VerifiedMobileDeviceContext,
    now: datetime,
) -> None:
    if device.tenant_id != principal.tenant_id:
        raise MobilePolicyDenied("DENY_DEVICE_TENANT_BINDING")
    if device.verified_at.tzinfo is None:
        raise MobilePolicyDenied("DENY_DEVICE_CONTEXT_TIME")

    verified_at = device.verified_at.astimezone(UTC)
    age_seconds = (now - verified_at).total_seconds()
    if age_seconds > MAX_DEVICE_CONTEXT_AGE_SECONDS:
        raise MobilePolicyDenied("DENY_DEVICE_CONTEXT_STALE")
    if age_seconds < -MAX_DEVICE_CONTEXT_FUTURE_SKEW_SECONDS:
        raise MobilePolicyDenied("DENY_DEVICE_CONTEXT_FUTURE")


def build_mobile_policy_snapshot(
    principal: Principal,
    device: VerifiedMobileDeviceContext,
    *,
    now: datetime | None = None,
    ttl_seconds: int = 120,
) -> MobilePolicySnapshot:
    """Resolve a bounded mobile UX/offline policy from canonical Core permissions.

    The result is not a bearer credential and does not replace backend authorization.
    A transport endpoint must supply only a server-verified device context and must sign
    the serialized snapshot before a mobile client may cache it.
    """
    if not 15 <= ttl_seconds <= MAX_POLICY_TTL_SECONDS:
        raise MobilePolicyDenied("DENY_POLICY_TTL")

    issued_at = (now or datetime.now(UTC)).astimezone(UTC)
    _validate_device_context(principal, device, issued_at)

    operation_policies: dict[str, MobileOperationPolicy] = {}
    for rule in MOBILE_OPERATION_RULES:
        if device.runtime_profile not in rule.profiles:
            continue
        if rule.permission_key not in principal.permissions:
            continue
        if rule.requires_active_shift and not device.active_shift_id:
            continue
        if not _risk_allowed(device, rule.risk):
            continue

        scope = resolve_permission_scope(principal, rule.permission_key)
        if not _scope_allows_location(scope, device.location_id):
            continue

        operation_policies[rule.operation] = MobileOperationPolicy(
            operation=rule.operation,
            risk=rule.risk,
            offline_allowed=rule.offline_allowed and rule.risk != MobileRisk.CRITICAL,
            requires_active_shift=rule.requires_active_shift,
            permission_key=rule.permission_key,
            scope_fingerprint=_scope_fingerprint(scope),
        )

    expires_at = issued_at + timedelta(seconds=ttl_seconds)
    fingerprint_payload: dict[str, object] = {
        "tenant_id": str(principal.tenant_id),
        "actor_id": principal.subject,
        "device_id": device.device_id,
        "installation_id": device.installation_id,
        "location_id": device.location_id,
        "auth_binding_id": device.auth_binding_id,
        "runtime_profile": device.runtime_profile.value,
        "active_shift_id": device.active_shift_id,
        "issued_at": issued_at.isoformat(),
        "expires_at": expires_at.isoformat(),
        "operations": {
            key: value.model_dump(mode="json")
            for key, value in sorted(operation_policies.items())
        },
    }

    return MobilePolicySnapshot(
        tenant_id=principal.tenant_id,
        actor_id=principal.subject,
        device_id=device.device_id,
        installation_id=device.installation_id,
        location_id=device.location_id,
        auth_binding_id=device.auth_binding_id,
        runtime_profile=device.runtime_profile,
        operation_policies=operation_policies,
        issued_at=issued_at,
        expires_at=expires_at,
        policy_fingerprint=_policy_fingerprint(fingerprint_payload),
    )
