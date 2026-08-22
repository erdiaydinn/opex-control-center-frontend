from uuid import UUID

import pytest
from pydantic import ValidationError

from app.core.mobile_fleet_health import (
    BatteryBucket,
    ConnectivityState,
    FleetCredentialRequest,
    FleetDeviceClass,
    FleetHealthObservation,
    FleetHealthRejected,
    FleetOperationalHealth,
    FleetProofInvalid,
    MobileRuntimeProfile,
    RolloutRing,
    ScannerHealth,
    build_snapshot,
    classify_fleet_health,
    issue_fleet_credentials,
    validate_observation_freshness,
    verify_fleet_proof,
)

TENANT = UUID("11111111-1111-1111-1111-111111111111")
OTHER_TENANT = UUID("22222222-2222-2222-2222-222222222222")
SECRET = "fleet-test-secret-which-is-longer-than-thirty-two-bytes"
NOW_SECONDS = 1_800_000_000
NOW_MS = NOW_SECONDS * 1000


def observation(**updates) -> FleetHealthObservation:
    values = {
        "fleet_device_token": "fleet-device-token-0001",
        "fleet_site_token": "fleet-site-token-0001",
        "runtime_profile": MobileRuntimeProfile.EAY_TERMINAL,
        "device_class": FleetDeviceClass.RUGGED,
        "app_version": "30.0.1",
        "rollout_ring": RolloutRing.LAB,
        "connectivity": ConnectivityState.ONLINE,
        "pending_sync_count": 0,
        "quarantined_sync_count": 0,
        "oldest_pending_age_ms": None,
        "last_successful_sync_age_ms": 1_000,
        "scanner_health": ScannerHealth.HEALTHY,
        "recent_crash_count": 0,
        "recent_anr_count": 0,
        "battery_bucket": BatteryBucket.NORMAL,
        "observed_at_epoch_ms": NOW_MS,
    }
    values.update(updates)
    return FleetHealthObservation.model_validate(values)


def credentials(
    *,
    tenant_id: UUID = TENANT,
    runtime_profile: MobileRuntimeProfile = MobileRuntimeProfile.EAY_TERMINAL,
    rollout_ring: RolloutRing = RolloutRing.LAB,
    site_binding: str | None = "FULYA",
):
    return issue_fleet_credentials(
        tenant_id,
        FleetCredentialRequest(
            runtime_profile=runtime_profile,
            rollout_ring=rollout_ring,
            site_binding=site_binding,
        ),
        now_epoch_seconds=NOW_SECONDS,
        secret=SECRET,
    )


def bound_observation(issued, **updates) -> FleetHealthObservation:
    return observation(
        fleet_device_token=issued.fleet_device_token,
        fleet_site_token=issued.fleet_site_token,
        runtime_profile=issued.runtime_profile,
        rollout_ring=issued.rollout_ring,
        **updates,
    )


def test_payload_rejects_raw_identity_or_operation_fields() -> None:
    values = observation().model_dump(mode="json")
    values["employee_id"] = "EMP-1"
    with pytest.raises(ValidationError):
        FleetHealthObservation.model_validate(values)

    values = observation().model_dump(mode="json")
    values["barcode"] = "8690000000000"
    with pytest.raises(ValidationError):
        FleetHealthObservation.model_validate(values)


def test_server_issued_proof_binds_tenant_runtime_ring_and_site() -> None:
    issued = credentials()
    payload = bound_observation(issued)
    window = verify_fleet_proof(
        TENANT,
        payload,
        issued.fleet_proof,
        now_epoch_seconds=NOW_SECONDS + 1,
        secret=SECRET,
    )
    assert window.expires_at_epoch_seconds == issued.expires_at_epoch_seconds

    with pytest.raises(FleetProofInvalid, match="binding"):
        verify_fleet_proof(
            OTHER_TENANT,
            payload,
            issued.fleet_proof,
            now_epoch_seconds=NOW_SECONDS + 1,
            secret=SECRET,
        )

    tampered_ring = payload.model_copy(update={"rollout_ring": RolloutRing.PERCENT_100})
    with pytest.raises(FleetProofInvalid, match="binding"):
        verify_fleet_proof(
            TENANT,
            tampered_ring,
            issued.fleet_proof,
            now_epoch_seconds=NOW_SECONDS + 1,
            secret=SECRET,
        )

    tampered_site = payload.model_copy(update={"fleet_site_token": "fleet-site-token-9999"})
    with pytest.raises(FleetProofInvalid, match="binding"):
        verify_fleet_proof(
            TENANT,
            tampered_site,
            issued.fleet_proof,
            now_epoch_seconds=NOW_SECONDS + 1,
            secret=SECRET,
        )


def test_proof_expiry_and_ttl_are_fail_closed() -> None:
    issued = credentials()
    payload = bound_observation(issued)
    with pytest.raises(FleetProofInvalid, match="expired"):
        verify_fleet_proof(
            TENANT,
            payload,
            issued.fleet_proof,
            now_epoch_seconds=issued.expires_at_epoch_seconds + 121,
            secret=SECRET,
        )

    with pytest.raises(FleetProofInvalid, match="TTL"):
        issue_fleet_credentials(
            TENANT,
            FleetCredentialRequest(
                runtime_profile=MobileRuntimeProfile.EAY_TERMINAL,
                rollout_ring=RolloutRing.LAB,
            ),
            now_epoch_seconds=NOW_SECONDS,
            ttl_seconds=60,
            secret=SECRET,
        )


def test_site_correlation_is_opaque_and_device_tokens_are_unique() -> None:
    first = credentials(site_binding="FULYA")
    second = credentials(site_binding="FULYA")
    assert first.fleet_site_token == second.fleet_site_token
    assert first.fleet_device_token != second.fleet_device_token
    for value in (first.fleet_site_token, first.fleet_device_token, first.fleet_proof):
        assert value is not None
        assert "FULYA" not in value


def test_server_classifier_matches_mobile_health_contract() -> None:
    assert classify_fleet_health(observation()) == FleetOperationalHealth.HEALTHY
    assert (
        classify_fleet_health(observation(scanner_health=ScannerHealth.UNAVAILABLE))
        == FleetOperationalHealth.CRITICAL
    )
    assert (
        classify_fleet_health(observation(recent_crash_count=3))
        == FleetOperationalHealth.CRITICAL
    )
    assert (
        classify_fleet_health(observation(quarantined_sync_count=1))
        == FleetOperationalHealth.DEGRADED
    )
    assert (
        classify_fleet_health(observation(recent_anr_count=1))
        == FleetOperationalHealth.DEGRADED
    )
    assert (
        classify_fleet_health(
            observation(last_successful_sync_age_ms=15 * 60 * 1000)
        )
        == FleetOperationalHealth.DEGRADED
    )
    assert (
        classify_fleet_health(
            observation(
                connectivity=ConnectivityState.OFFLINE,
                last_successful_sync_age_ms=60 * 60 * 1000,
            )
        )
        == FleetOperationalHealth.HEALTHY
    )


def test_health_is_server_derived_not_client_supplied() -> None:
    values = observation().model_dump(mode="json")
    values["health"] = "HEALTHY"
    with pytest.raises(ValidationError):
        FleetHealthObservation.model_validate(values)

    snapshot = build_snapshot(
        observation(scanner_health=ScannerHealth.UNAVAILABLE),
        received_at_epoch_ms=NOW_MS + 1,
    )
    assert snapshot.health == FleetOperationalHealth.CRITICAL
    dump = snapshot.model_dump(mode="json")
    assert "fleet_proof" not in dump
    assert "actor_id" not in dump
    assert "employee_id" not in dump
    assert "device_id" not in dump


def test_stale_or_future_observation_is_rejected() -> None:
    with pytest.raises(FleetHealthRejected, match="stale"):
        validate_observation_freshness(
            observation(observed_at_epoch_ms=NOW_MS - 10 * 60 * 1000 - 1),
            now_epoch_ms=NOW_MS,
        )
    with pytest.raises(FleetHealthRejected, match="future"):
        validate_observation_freshness(
            observation(observed_at_epoch_ms=NOW_MS + 120 * 1000 + 1),
            now_epoch_ms=NOW_MS,
        )
