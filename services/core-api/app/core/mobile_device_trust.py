"""Canonical EAY Mobile device-trust derivation.

Raw mobile input is never a VerifiedMobileDeviceContext. A caller must first
combine canonical registry state with cryptographically verified request
proof. This module then enforces exact binding and freshness before policy
resolution can run.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field

from app.core.mobile_policy import (
    MobileDeviceTrust,
    MobileIntegrityVerdict,
    MobilePolicyDenied,
    MobileRuntimeProfile,
    VerifiedMobileDeviceContext,
)
from app.core.security import Principal

MAX_REQUEST_PROOF_AGE_SECONDS = 60
MAX_REQUEST_PROOF_FUTURE_SKEW_SECONDS = 5
MAX_INTEGRITY_AGE_SECONDS = 300


class MobileDeviceState(StrEnum):
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"
    LOST = "LOST"
    REPLACED = "REPLACED"


class MobileDeviceRegistryRecord(BaseModel):
    tenant_id: UUID
    device_id: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(min_length=1, max_length=128)
    assigned_actor_id: str | None = Field(default=None, max_length=256)
    runtime_profile: MobileRuntimeProfile
    trust_level: MobileDeviceTrust
    allowed_location_ids: frozenset[str]
    public_key_thumbprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    state: MobileDeviceState


class ServerVerifiedMobileEvidence(BaseModel):
    """Evidence after signature/attestation verification, never raw HTTP fields."""

    tenant_id: UUID
    actor_id: str = Field(min_length=1, max_length=256)
    device_id: str = Field(min_length=1, max_length=128)
    installation_id: str = Field(min_length=1, max_length=128)
    location_id: str = Field(min_length=1, max_length=128)
    auth_binding_id: str = Field(min_length=1, max_length=128)
    runtime_profile: MobileRuntimeProfile
    request_proof_verified: bool
    request_proof_verified_at: datetime
    integrity_verdict: MobileIntegrityVerdict
    integrity_verified_at: datetime | None = None
    active_shift_id: str | None = Field(default=None, max_length=128)


def _aware_utc(value: datetime, code: str) -> datetime:
    if value.tzinfo is None:
        raise MobilePolicyDenied(code)
    return value.astimezone(UTC)


def _assert_fresh(
    observed_at: datetime,
    *,
    now: datetime,
    max_age_seconds: int,
    stale_code: str,
    future_code: str,
) -> None:
    age = (now - _aware_utc(observed_at, stale_code)).total_seconds()
    if age > max_age_seconds:
        raise MobilePolicyDenied(stale_code)
    if age < -MAX_REQUEST_PROOF_FUTURE_SKEW_SECONDS:
        raise MobilePolicyDenied(future_code)


def derive_verified_mobile_device_context(
    principal: Principal,
    registry: MobileDeviceRegistryRecord,
    evidence: ServerVerifiedMobileEvidence,
    *,
    now: datetime | None = None,
) -> VerifiedMobileDeviceContext:
    current = _aware_utc(now or datetime.now(UTC), "DENY_DEVICE_CLOCK")

    if registry.state != MobileDeviceState.ACTIVE:
        raise MobilePolicyDenied("DENY_DEVICE_NOT_ACTIVE")
    if (
        principal.tenant_id != registry.tenant_id
        or evidence.tenant_id != registry.tenant_id
    ):
        raise MobilePolicyDenied("DENY_DEVICE_TENANT_BINDING")
    if evidence.actor_id != principal.subject:
        raise MobilePolicyDenied("DENY_DEVICE_ACTOR_BINDING")
    if registry.assigned_actor_id and registry.assigned_actor_id != principal.subject:
        raise MobilePolicyDenied("DENY_DEVICE_ASSIGNMENT")
    if evidence.device_id != registry.device_id:
        raise MobilePolicyDenied("DENY_DEVICE_ID_BINDING")
    if evidence.installation_id != registry.installation_id:
        raise MobilePolicyDenied("DENY_DEVICE_INSTALLATION_BINDING")
    if evidence.runtime_profile != registry.runtime_profile:
        raise MobilePolicyDenied("DENY_DEVICE_RUNTIME_BINDING")
    if (
        not registry.allowed_location_ids
        or evidence.location_id not in registry.allowed_location_ids
    ):
        raise MobilePolicyDenied("DENY_DEVICE_LOCATION_BINDING")
    if not evidence.request_proof_verified:
        raise MobilePolicyDenied("DENY_DEVICE_REQUEST_PROOF")

    _assert_fresh(
        evidence.request_proof_verified_at,
        now=current,
        max_age_seconds=MAX_REQUEST_PROOF_AGE_SECONDS,
        stale_code="DENY_DEVICE_REQUEST_PROOF_STALE",
        future_code="DENY_DEVICE_REQUEST_PROOF_FUTURE",
    )

    integrity = evidence.integrity_verdict
    if integrity == MobileIntegrityVerdict.PASS:
        if evidence.integrity_verified_at is None:
            integrity = MobileIntegrityVerdict.UNKNOWN
        else:
            integrity_at = _aware_utc(
                evidence.integrity_verified_at,
                "DENY_DEVICE_INTEGRITY_TIME",
            )
            age = (current - integrity_at).total_seconds()
            if (
                age > MAX_INTEGRITY_AGE_SECONDS
                or age < -MAX_REQUEST_PROOF_FUTURE_SKEW_SECONDS
            ):
                integrity = MobileIntegrityVerdict.UNKNOWN

    return VerifiedMobileDeviceContext(
        tenant_id=registry.tenant_id,
        device_id=registry.device_id,
        installation_id=registry.installation_id,
        location_id=evidence.location_id,
        auth_binding_id=evidence.auth_binding_id,
        runtime_profile=registry.runtime_profile,
        trust_level=registry.trust_level,
        integrity_verdict=integrity,
        active_shift_id=evidence.active_shift_id,
        verified_at=current,
    )
