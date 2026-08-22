from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.resources import redis_client

FLEET_SNAPSHOT_TTL_SECONDS = 48 * 60 * 60
MAX_OBSERVATION_AGE_SECONDS = 10 * 60
MAX_CLOCK_SKEW_SECONDS = 120
DEFAULT_PROOF_TTL_SECONDS = 30 * 24 * 60 * 60
MAX_PROOF_TTL_SECONDS = 31 * 24 * 60 * 60
MIN_PROOF_TTL_SECONDS = 5 * 60
FLEET_PROOF_SECRET_ENV = "EAY_MOBILE_FLEET_PROOF_SECRET"


class MobileRuntimeProfile(StrEnum):
    EAY_ONE = "EAY_ONE"
    EAY_TERMINAL = "EAY_TERMINAL"


class FleetDeviceClass(StrEnum):
    PHONE = "PHONE"
    RUGGED = "RUGGED"
    TABLET = "TABLET"
    UNKNOWN = "UNKNOWN"


class RolloutRing(StrEnum):
    DEVELOPER = "DEVELOPER"
    DOGFOOD = "DOGFOOD"
    LAB = "LAB"
    PILOT_1 = "PILOT_1"
    PILOT_5 = "PILOT_5"
    PILOT_20 = "PILOT_20"
    PERCENT_25 = "PERCENT_25"
    PERCENT_50 = "PERCENT_50"
    PERCENT_100 = "PERCENT_100"


class ConnectivityState(StrEnum):
    ONLINE = "ONLINE"
    OFFLINE = "OFFLINE"


class ScannerHealth(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


class BatteryBucket(StrEnum):
    UNKNOWN = "UNKNOWN"
    CRITICAL = "CRITICAL"
    LOW = "LOW"
    NORMAL = "NORMAL"
    HIGH = "HIGH"


class FleetOperationalHealth(StrEnum):
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    CRITICAL = "CRITICAL"


class FleetHealthRejected(ValueError):
    pass


class FleetProofInvalid(ValueError):
    pass


class FleetTelemetryUnavailable(RuntimeError):
    pass


class FleetSnapshotConflict(ValueError):
    pass


class FleetHealthObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_device_token: str = Field(pattern=r"^[A-Za-z0-9._:-]{16,128}$")
    fleet_site_token: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z0-9._:-]{16,128}$",
    )
    runtime_profile: MobileRuntimeProfile
    device_class: FleetDeviceClass
    app_version: str = Field(min_length=1, max_length=64)
    rollout_ring: RolloutRing
    connectivity: ConnectivityState
    pending_sync_count: int = Field(ge=0, le=1_000_000)
    quarantined_sync_count: int = Field(ge=0, le=1_000_000)
    oldest_pending_age_ms: int | None = Field(default=None, ge=0, le=604_800_000)
    last_successful_sync_age_ms: int | None = Field(default=None, ge=0, le=604_800_000)
    scanner_health: ScannerHealth
    recent_crash_count: int = Field(ge=0, le=10_000)
    recent_anr_count: int = Field(ge=0, le=10_000)
    battery_bucket: BatteryBucket
    observed_at_epoch_ms: int = Field(gt=0)

    @field_validator("app_version")
    @classmethod
    def _bounded_app_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(ord(character) < 32 for character in normalized):
            raise ValueError("app_version is invalid")
        return normalized


class FleetCredentialRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    runtime_profile: MobileRuntimeProfile
    rollout_ring: RolloutRing
    site_binding: str | None = Field(default=None, max_length=128)

    @field_validator("site_binding")
    @classmethod
    def _normalize_site_binding(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        if any(ord(character) < 32 for character in normalized):
            raise ValueError("site_binding is invalid")
        return normalized


class FleetCredentialIssue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    fleet_device_token: str
    fleet_site_token: str | None
    fleet_proof: str
    issued_at_epoch_seconds: int
    expires_at_epoch_seconds: int
    runtime_profile: MobileRuntimeProfile
    rollout_ring: RolloutRing


class FleetSnapshotRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: int = 1
    health: FleetOperationalHealth
    observation: FleetHealthObservation
    observation_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    received_at_epoch_ms: int = Field(gt=0)


@dataclass(frozen=True)
class FleetProofWindow:
    issued_at_epoch_seconds: int
    expires_at_epoch_seconds: int


def _urlsafe(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _proof_key(secret: str | bytes | None = None) -> bytes:
    raw = secret if secret is not None else os.getenv(FLEET_PROOF_SECRET_ENV, "")
    value = raw if isinstance(raw, bytes) else raw.encode("utf-8")
    if len(value) < 32:
        raise FleetTelemetryUnavailable("Mobile fleet proof authority is not configured")
    return value


def _site_token(key: bytes, tenant_id: UUID, site_binding: str | None) -> str | None:
    if site_binding is None:
        return None
    digest = hmac.new(
        key,
        f"fleet-site\0{tenant_id}\0{site_binding}".encode(),
        hashlib.sha256,
    ).digest()
    return _urlsafe(digest[:24])


def _proof_message(
    *,
    tenant_id: UUID,
    fleet_device_token: str,
    fleet_site_token: str | None,
    runtime_profile: MobileRuntimeProfile,
    rollout_ring: RolloutRing,
    issued_at_epoch_seconds: int,
    expires_at_epoch_seconds: int,
) -> bytes:
    return "\0".join(
        (
            "fleet-proof-v1",
            str(tenant_id),
            fleet_device_token,
            fleet_site_token or "-",
            runtime_profile.value,
            rollout_ring.value,
            str(issued_at_epoch_seconds),
            str(expires_at_epoch_seconds),
        )
    ).encode()


def issue_fleet_credentials(
    tenant_id: UUID,
    request: FleetCredentialRequest,
    *,
    now_epoch_seconds: int,
    ttl_seconds: int = DEFAULT_PROOF_TTL_SECONDS,
    secret: str | bytes | None = None,
) -> FleetCredentialIssue:
    if ttl_seconds < MIN_PROOF_TTL_SECONDS or ttl_seconds > MAX_PROOF_TTL_SECONDS:
        raise FleetProofInvalid("Fleet proof TTL is outside the allowed window")
    if now_epoch_seconds <= 0:
        raise FleetProofInvalid("Fleet proof issue time is invalid")

    key = _proof_key(secret)
    device_token = secrets.token_urlsafe(24)
    site_token = _site_token(key, tenant_id, request.site_binding)
    expires = now_epoch_seconds + ttl_seconds
    signature = hmac.new(
        key,
        _proof_message(
            tenant_id=tenant_id,
            fleet_device_token=device_token,
            fleet_site_token=site_token,
            runtime_profile=request.runtime_profile,
            rollout_ring=request.rollout_ring,
            issued_at_epoch_seconds=now_epoch_seconds,
            expires_at_epoch_seconds=expires,
        ),
        hashlib.sha256,
    ).digest()
    proof = f"fp1.{now_epoch_seconds}.{expires}.{_urlsafe(signature)}"
    return FleetCredentialIssue(
        fleet_device_token=device_token,
        fleet_site_token=site_token,
        fleet_proof=proof,
        issued_at_epoch_seconds=now_epoch_seconds,
        expires_at_epoch_seconds=expires,
        runtime_profile=request.runtime_profile,
        rollout_ring=request.rollout_ring,
    )


def verify_fleet_proof(
    tenant_id: UUID,
    observation: FleetHealthObservation,
    proof: str,
    *,
    now_epoch_seconds: int,
    secret: str | bytes | None = None,
) -> FleetProofWindow:
    parts = proof.split(".")
    if len(parts) != 4 or parts[0] != "fp1":
        raise FleetProofInvalid("Fleet proof format is invalid")
    try:
        issued = int(parts[1])
        expires = int(parts[2])
    except ValueError as exc:
        raise FleetProofInvalid("Fleet proof time window is invalid") from exc

    lifetime = expires - issued
    if lifetime < MIN_PROOF_TTL_SECONDS or lifetime > MAX_PROOF_TTL_SECONDS:
        raise FleetProofInvalid("Fleet proof lifetime is invalid")
    if issued > now_epoch_seconds + MAX_CLOCK_SKEW_SECONDS:
        raise FleetProofInvalid("Fleet proof is not active yet")
    if expires < now_epoch_seconds - MAX_CLOCK_SKEW_SECONDS:
        raise FleetProofInvalid("Fleet proof has expired")

    key = _proof_key(secret)
    expected = _urlsafe(
        hmac.new(
            key,
            _proof_message(
                tenant_id=tenant_id,
                fleet_device_token=observation.fleet_device_token,
                fleet_site_token=observation.fleet_site_token,
                runtime_profile=observation.runtime_profile,
                rollout_ring=observation.rollout_ring,
                issued_at_epoch_seconds=issued,
                expires_at_epoch_seconds=expires,
            ),
            hashlib.sha256,
        ).digest()
    )
    if not hmac.compare_digest(expected, parts[3]):
        raise FleetProofInvalid("Fleet proof binding is invalid")
    return FleetProofWindow(issued, expires)


def validate_observation_freshness(
    observation: FleetHealthObservation,
    *,
    now_epoch_ms: int,
) -> None:
    age_ms = now_epoch_ms - observation.observed_at_epoch_ms
    if age_ms > MAX_OBSERVATION_AGE_SECONDS * 1000:
        raise FleetHealthRejected("Fleet observation is stale")
    if age_ms < -(MAX_CLOCK_SKEW_SECONDS * 1000):
        raise FleetHealthRejected("Fleet observation is from the future")


def classify_fleet_health(observation: FleetHealthObservation) -> FleetOperationalHealth:
    if observation.recent_crash_count >= 3:
        return FleetOperationalHealth.CRITICAL
    if observation.quarantined_sync_count >= 100:
        return FleetOperationalHealth.CRITICAL
    if (
        observation.runtime_profile == MobileRuntimeProfile.EAY_TERMINAL
        and observation.scanner_health == ScannerHealth.UNAVAILABLE
    ):
        return FleetOperationalHealth.CRITICAL

    stale_online_sync = (
        observation.connectivity == ConnectivityState.ONLINE
        and (observation.last_successful_sync_age_ms or 0) >= 15 * 60 * 1000
    )
    if (
        observation.quarantined_sync_count > 0
        or observation.pending_sync_count >= 500
        or (observation.oldest_pending_age_ms or 0) >= 15 * 60 * 1000
        or observation.recent_anr_count > 0
        or observation.scanner_health == ScannerHealth.DEGRADED
        or stale_online_sync
        or observation.battery_bucket == BatteryBucket.CRITICAL
    ):
        return FleetOperationalHealth.DEGRADED
    return FleetOperationalHealth.HEALTHY


def observation_hash(observation: FleetHealthObservation) -> str:
    canonical = json.dumps(
        observation.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def build_snapshot(
    observation: FleetHealthObservation,
    *,
    received_at_epoch_ms: int,
) -> FleetSnapshotRecord:
    return FleetSnapshotRecord(
        health=classify_fleet_health(observation),
        observation=observation,
        observation_hash=observation_hash(observation),
        received_at_epoch_ms=received_at_epoch_ms,
    )


STORE_LATEST_SCRIPT = """
local existing = redis.call('GET', KEYS[1])
local new_observed = tonumber(ARGV[1])
if existing then
  local decoded = cjson.decode(existing)
  local old_observed = tonumber(decoded['observation']['observed_at_epoch_ms'])
  if old_observed > new_observed then
    return -1
  end
  if old_observed == new_observed then
    if decoded['observation_hash'] ~= ARGV[2] then
      return -2
    end
    redis.call('EXPIRE', KEYS[1], tonumber(ARGV[4]))
    redis.call('ZADD', KEYS[2], tonumber(ARGV[5]), ARGV[6])
    redis.call('EXPIRE', KEYS[2], tonumber(ARGV[4]))
    redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, tonumber(ARGV[7]))
    return 0
  end
end
redis.call('SET', KEYS[1], ARGV[3], 'EX', tonumber(ARGV[4]))
redis.call('ZADD', KEYS[2], tonumber(ARGV[5]), ARGV[6])
redis.call('EXPIRE', KEYS[2], tonumber(ARGV[4]))
redis.call('ZREMRANGEBYSCORE', KEYS[2], 0, tonumber(ARGV[7]))
return 1
""".strip()


class RedisFleetHealthStore:
    def __init__(self, redis: Any = redis_client) -> None:
        self.redis = redis

    @staticmethod
    def _snapshot_key(tenant_id: UUID, fleet_device_token: str) -> str:
        return f"eay:mobile:fleet:latest:{tenant_id}:{fleet_device_token}"

    @staticmethod
    def _index_key(tenant_id: UUID) -> str:
        return f"eay:mobile:fleet:index:{tenant_id}"

    async def store_latest(
        self,
        tenant_id: UUID,
        observation: FleetHealthObservation,
        *,
        now_epoch_ms: int,
    ) -> tuple[FleetSnapshotRecord, bool]:
        record = build_snapshot(observation, received_at_epoch_ms=now_epoch_ms)
        encoded = json.dumps(
            record.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        )
        cutoff = now_epoch_ms - FLEET_SNAPSHOT_TTL_SECONDS * 1000
        try:
            result = int(
                await self.redis.eval(
                    STORE_LATEST_SCRIPT,
                    2,
                    self._snapshot_key(tenant_id, observation.fleet_device_token),
                    self._index_key(tenant_id),
                    observation.observed_at_epoch_ms,
                    record.observation_hash,
                    encoded,
                    FLEET_SNAPSHOT_TTL_SECONDS,
                    now_epoch_ms,
                    observation.fleet_device_token,
                    cutoff,
                )
            )
        except Exception as exc:
            raise FleetTelemetryUnavailable("Mobile fleet telemetry store is unavailable") from exc

        if result == -1:
            raise FleetSnapshotConflict("Older fleet observation cannot replace newer health")
        if result == -2:
            raise FleetSnapshotConflict(
                "Fleet observation timestamp was reused with different data"
            )
        if result == 0:
            try:
                existing = await self.redis.get(
                    self._snapshot_key(tenant_id, observation.fleet_device_token)
                )
                if not existing:
                    raise FleetTelemetryUnavailable("Fleet replay snapshot disappeared")
                return FleetSnapshotRecord.model_validate_json(existing), True
            except FleetTelemetryUnavailable:
                raise
            except Exception as exc:
                raise FleetTelemetryUnavailable("Fleet replay snapshot is unreadable") from exc
        if result != 1:
            raise FleetTelemetryUnavailable("Unexpected fleet telemetry store result")
        return record, False

    async def list_latest(
        self,
        tenant_id: UUID,
        *,
        now_epoch_ms: int,
        limit: int,
    ) -> list[FleetSnapshotRecord]:
        safe_limit = max(1, min(limit, 500))
        index_key = self._index_key(tenant_id)
        cutoff = now_epoch_ms - FLEET_SNAPSHOT_TTL_SECONDS * 1000
        try:
            await self.redis.zremrangebyscore(index_key, 0, cutoff)
            tokens = await self.redis.zrevrange(index_key, 0, safe_limit - 1)
            if not tokens:
                return []
            values = await self.redis.mget(
                [self._snapshot_key(tenant_id, str(token)) for token in tokens]
            )
        except Exception as exc:
            raise FleetTelemetryUnavailable("Mobile fleet telemetry read is unavailable") from exc

        records: list[FleetSnapshotRecord] = []
        for value in values:
            if not value:
                continue
            try:
                record = FleetSnapshotRecord.model_validate_json(value)
            except Exception:
                continue
            if record.received_at_epoch_ms >= cutoff:
                records.append(record)
        return records


fleet_health_store = RedisFleetHealthStore()
