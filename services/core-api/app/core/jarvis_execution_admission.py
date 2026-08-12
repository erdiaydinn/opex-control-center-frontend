"""Distributed abuse and concurrency controls for Jarvis tool execution.

Request idempotency prevents accidental duplicate execution under the same
client key. Admission control addresses the different threat: a caller can
submit many unique keys and still amplify expensive governed reads.

Redis stores only SHA-256-scoped identifiers, counters, and random lease IDs.
Raw tenant actors, tool arguments, human reasons, grant tokens, and results are
never written by this authority. Admission is fail closed when Redis is not
available or returns an unexpected script result.
"""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from redis.exceptions import RedisError

ADMISSION_KEY_PREFIX = "opex:{ai}:jarvis-admission"
ADMISSION_LEASE_SAFETY_SECONDS = 15

_ADMIT_SCRIPT = r"""
local tenant_rate_key = KEYS[1]
local actor_rate_key = KEYS[2]
local tenant_concurrency_key = KEYS[3]
local actor_concurrency_key = KEYS[4]

local tenant_rate_limit = tonumber(ARGV[1])
local actor_rate_limit = tonumber(ARGV[2])
local window_ms = tonumber(ARGV[3])
local tenant_concurrency_limit = tonumber(ARGV[4])
local actor_concurrency_limit = tonumber(ARGV[5])
local lease_ttl_ms = tonumber(ARGV[6])
local lease_id = ARGV[7]

local server_time = redis.call('TIME')
local now_ms = (tonumber(server_time[1]) * 1000) + math.floor(tonumber(server_time[2]) / 1000)
local lease_expires_ms = now_ms + lease_ttl_ms

redis.call('ZREMRANGEBYSCORE', tenant_concurrency_key, '-inf', now_ms)
redis.call('ZREMRANGEBYSCORE', actor_concurrency_key, '-inf', now_ms)

if redis.call('ZCARD', tenant_concurrency_key) >= tenant_concurrency_limit then
    return {0, 'tenant_concurrency'}
end
if redis.call('ZCARD', actor_concurrency_key) >= actor_concurrency_limit then
    return {0, 'actor_concurrency'}
end

local tenant_rate = tonumber(redis.call('GET', tenant_rate_key) or '0')
local actor_rate = tonumber(redis.call('GET', actor_rate_key) or '0')
if tenant_rate >= tenant_rate_limit then
    return {0, 'tenant_rate'}
end
if actor_rate >= actor_rate_limit then
    return {0, 'actor_rate'}
end

tenant_rate = redis.call('INCR', tenant_rate_key)
if tenant_rate == 1 then
    redis.call('PEXPIRE', tenant_rate_key, window_ms)
end
actor_rate = redis.call('INCR', actor_rate_key)
if actor_rate == 1 then
    redis.call('PEXPIRE', actor_rate_key, window_ms)
end

redis.call('ZADD', tenant_concurrency_key, lease_expires_ms, lease_id)
redis.call('ZADD', actor_concurrency_key, lease_expires_ms, lease_id)
redis.call('PEXPIRE', tenant_concurrency_key, lease_ttl_ms + 1000)
redis.call('PEXPIRE', actor_concurrency_key, lease_ttl_ms + 1000)

return {1, 'admitted'}
"""

_RELEASE_SCRIPT = r"""
local removed_tenant = redis.call('ZREM', KEYS[1], ARGV[1])
local removed_actor = redis.call('ZREM', KEYS[2], ARGV[1])
if redis.call('ZCARD', KEYS[1]) == 0 then
    redis.call('DEL', KEYS[1])
end
if redis.call('ZCARD', KEYS[2]) == 0 then
    redis.call('DEL', KEYS[2])
end
return removed_tenant + removed_actor
"""


class JarvisAdmissionError(PermissionError):
    """Base denial for the distributed Jarvis admission boundary."""


class JarvisAdmissionInvalid(JarvisAdmissionError):
    """Admission inputs or policy are invalid."""


class JarvisAdmissionUnavailable(JarvisAdmissionError):
    """The distributed admission authority cannot fail safely."""


class JarvisAdmissionRateLimited(JarvisAdmissionError):
    """A tenant or actor exceeded the configured request budget."""


class JarvisAdmissionConcurrencyLimited(JarvisAdmissionError):
    """A tenant or actor exceeded the configured in-flight budget."""


class JarvisExecutionAdmissionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_JARVIS_ADMISSION_",
        case_sensitive=False,
        extra="ignore",
    )

    tenant_requests_per_window: int = Field(default=30, ge=1, le=10_000)
    actor_requests_per_window: int = Field(default=10, ge=1, le=1_000)
    window_seconds: int = Field(default=60, ge=1, le=3600)
    tenant_concurrency: int = Field(default=4, ge=1, le=100)
    actor_concurrency: int = Field(default=2, ge=1, le=20)
    maximum_lease_ttl_seconds: int = Field(default=180, ge=20, le=300)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> JarvisExecutionAdmissionSettings:
        if self.actor_requests_per_window > self.tenant_requests_per_window:
            raise ValueError("Jarvis actor request budget cannot exceed tenant budget")
        if self.actor_concurrency > self.tenant_concurrency:
            raise ValueError("Jarvis actor concurrency cannot exceed tenant concurrency")
        return self


@dataclass(frozen=True)
class JarvisAdmissionLease:
    token: SecretStr
    lease_ttl_seconds: int


def broker_lease_ttl_seconds(
    request_timeout_seconds: float,
    *,
    maximum_lease_ttl_seconds: int,
) -> int:
    if (
        isinstance(request_timeout_seconds, bool)
        or not isinstance(request_timeout_seconds, (int, float))
        or not math.isfinite(float(request_timeout_seconds))
        or request_timeout_seconds <= 0
    ):
        raise JarvisAdmissionInvalid("Jarvis broker timeout is invalid")
    if (
        isinstance(maximum_lease_ttl_seconds, bool)
        or not isinstance(maximum_lease_ttl_seconds, int)
        or maximum_lease_ttl_seconds < 1
    ):
        raise JarvisAdmissionInvalid("Jarvis admission lease policy is invalid")

    ttl = math.ceil(float(request_timeout_seconds)) + ADMISSION_LEASE_SAFETY_SECONDS
    if ttl > maximum_lease_ttl_seconds:
        raise JarvisAdmissionInvalid(
            "Jarvis broker timeout exceeds admission lease capacity"
        )
    return ttl


def _scope_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class RedisJarvisExecutionAdmissionStore:
    """Atomically enforce tenant + actor rate and concurrency budgets."""

    def __init__(
        self,
        redis_client: Redis,
        settings: JarvisExecutionAdmissionSettings,
        *,
        key_prefix: str = ADMISSION_KEY_PREFIX,
    ) -> None:
        if (
            not isinstance(key_prefix, str)
            or not key_prefix
            or len(key_prefix) > 128
            or "{ai}" not in key_prefix
        ):
            raise ValueError("Jarvis admission key prefix is invalid")
        self._redis = redis_client
        self._settings = settings
        self._key_prefix = key_prefix

    def _keys(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
    ) -> tuple[str, str, str, str]:
        if not isinstance(tenant_id, UUID):
            raise JarvisAdmissionInvalid("Jarvis admission tenant is invalid")
        if (
            not isinstance(actor_subject, str)
            or not actor_subject
            or len(actor_subject) > 512
        ):
            raise JarvisAdmissionInvalid("Jarvis admission actor is invalid")

        tenant_digest = _scope_digest(f"tenant:{tenant_id}")
        actor_digest = _scope_digest(f"tenant:{tenant_id}:actor:{actor_subject}")
        return (
            f"{self._key_prefix}:tenant:{tenant_digest}:rate",
            f"{self._key_prefix}:actor:{actor_digest}:rate",
            f"{self._key_prefix}:tenant:{tenant_digest}:concurrency",
            f"{self._key_prefix}:actor:{actor_digest}:concurrency",
        )

    async def acquire(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        request_timeout_seconds: float,
    ) -> JarvisAdmissionLease:
        keys = self._keys(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
        )
        lease_ttl_seconds = broker_lease_ttl_seconds(
            request_timeout_seconds,
            maximum_lease_ttl_seconds=(
                self._settings.maximum_lease_ttl_seconds
            ),
        )
        lease_token = secrets.token_urlsafe(32)

        try:
            response = await self._redis.eval(
                _ADMIT_SCRIPT,
                len(keys),
                *keys,
                self._settings.tenant_requests_per_window,
                self._settings.actor_requests_per_window,
                self._settings.window_seconds * 1000,
                self._settings.tenant_concurrency,
                self._settings.actor_concurrency,
                lease_ttl_seconds * 1000,
                lease_token,
            )
        except RedisError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission authority is unavailable"
            ) from exc

        if not isinstance(response, (list, tuple)) or len(response) != 2:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission authority returned an invalid result"
            )

        admitted, reason = response
        if isinstance(reason, bytes):
            reason = reason.decode("utf-8", errors="strict")

        if admitted in {1, "1", b"1"} and reason == "admitted":
            return JarvisAdmissionLease(
                token=SecretStr(lease_token),
                lease_ttl_seconds=lease_ttl_seconds,
            )

        if admitted not in {0, "0", b"0"}:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission authority returned an invalid decision"
            )
        if reason in {"tenant_rate", "actor_rate"}:
            raise JarvisAdmissionRateLimited("Jarvis execution rate limit exceeded")
        if reason in {"tenant_concurrency", "actor_concurrency"}:
            raise JarvisAdmissionConcurrencyLimited(
                "Jarvis execution concurrency limit exceeded"
            )
        raise JarvisAdmissionUnavailable(
            "Jarvis admission authority returned an unknown denial"
        )

    async def release(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        lease: JarvisAdmissionLease,
    ) -> None:
        keys = self._keys(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
        )
        if not isinstance(lease, JarvisAdmissionLease):
            raise JarvisAdmissionInvalid("Jarvis admission lease is invalid")
        lease_token = lease.token.get_secret_value()
        if len(lease_token) < 32 or len(lease_token) > 256:
            raise JarvisAdmissionInvalid("Jarvis admission lease is invalid")

        try:
            response = await self._redis.eval(
                _RELEASE_SCRIPT,
                2,
                keys[2],
                keys[3],
                lease_token,
            )
        except RedisError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission lease could not be released"
            ) from exc

        if isinstance(response, bool) or not isinstance(response, int):
            raise JarvisAdmissionUnavailable(
                "Jarvis admission release returned an invalid result"
            )
        if response not in {0, 1, 2}:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission release returned an invalid count"
            )
