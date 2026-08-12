"""Distributed fail-closed admission and emergency controls for Jarvis.

Idempotency prevents one client key from executing twice. Admission control
limits a different blast radius: many unique requests from one tenant, actor or
tool. Redis operations are atomic and use a shared hash slot. Raw tenant IDs,
actors and tool names are never embedded in Redis keys.

The runtime control mode is deliberately explicit. A missing, malformed or
unreachable control state fails closed; execution never assumes "enabled".
Bootstrap starts halted and recovery from an emergency halt must pass through
read-only before full execution can be enabled again.
"""

from __future__ import annotations

import hashlib
import math
import secrets
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal
from uuid import UUID

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from redis.asyncio import Redis
from redis.exceptions import RedisError

ADMISSION_KEY_PREFIX = "opex:{ai}:jarvis-admission"
ADMISSION_LEASE_SAFETY_SECONDS = 15
JarvisControlMode = Literal["enabled", "read_only", "halted"]
JarvisSideEffectClass = Literal["none", "read", "write", "irreversible"]

ALLOWED_CONTROL_TRANSITIONS = MappingProxyType(
    {
        "enabled": frozenset({"read_only", "halted"}),
        "read_only": frozenset({"enabled", "halted"}),
        "halted": frozenset({"read_only"}),
    }
)

_ADMIT_SCRIPT = r"""
local control_key = KEYS[1]
local tenant_rate_key = KEYS[2]
local actor_rate_key = KEYS[3]
local tool_rate_key = KEYS[4]
local tenant_concurrency_key = KEYS[5]
local actor_concurrency_key = KEYS[6]
local tool_concurrency_key = KEYS[7]

local tenant_rate_limit = tonumber(ARGV[1])
local actor_rate_limit = tonumber(ARGV[2])
local tool_rate_limit = tonumber(ARGV[3])
local window_ms = tonumber(ARGV[4])
local tenant_concurrency_limit = tonumber(ARGV[5])
local actor_concurrency_limit = tonumber(ARGV[6])
local tool_concurrency_limit = tonumber(ARGV[7])
local lease_ttl_ms = tonumber(ARGV[8])
local lease_id = ARGV[9]
local side_effect_class = ARGV[10]

local mode = redis.call('GET', control_key)
if not mode then
    return {0, 'control_missing'}
end
if mode == 'halted' then
    return {0, 'halted'}
end
if mode ~= 'enabled' and mode ~= 'read_only' then
    return {0, 'control_invalid'}
end
if mode == 'read_only' and side_effect_class ~= 'none' and side_effect_class ~= 'read' then
    return {0, 'read_only'}
end

local server_time = redis.call('TIME')
local now_ms = (tonumber(server_time[1]) * 1000) + math.floor(tonumber(server_time[2]) / 1000)
local lease_expires_ms = now_ms + lease_ttl_ms

redis.call('ZREMRANGEBYSCORE', tenant_concurrency_key, '-inf', now_ms)
redis.call('ZREMRANGEBYSCORE', actor_concurrency_key, '-inf', now_ms)
redis.call('ZREMRANGEBYSCORE', tool_concurrency_key, '-inf', now_ms)

if redis.call('ZCARD', tenant_concurrency_key) >= tenant_concurrency_limit then
    return {0, 'tenant_concurrency'}
end
if redis.call('ZCARD', actor_concurrency_key) >= actor_concurrency_limit then
    return {0, 'actor_concurrency'}
end
if redis.call('ZCARD', tool_concurrency_key) >= tool_concurrency_limit then
    return {0, 'tool_concurrency'}
end

local tenant_rate = tonumber(redis.call('GET', tenant_rate_key) or '0')
local actor_rate = tonumber(redis.call('GET', actor_rate_key) or '0')
local tool_rate = tonumber(redis.call('GET', tool_rate_key) or '0')
if tenant_rate >= tenant_rate_limit then
    return {0, 'tenant_rate'}
end
if actor_rate >= actor_rate_limit then
    return {0, 'actor_rate'}
end
if tool_rate >= tool_rate_limit then
    return {0, 'tool_rate'}
end

local new_tenant_rate = redis.call('INCR', tenant_rate_key)
if new_tenant_rate == 1 then
    redis.call('PEXPIRE', tenant_rate_key, window_ms)
end
local new_actor_rate = redis.call('INCR', actor_rate_key)
if new_actor_rate == 1 then
    redis.call('PEXPIRE', actor_rate_key, window_ms)
end
local new_tool_rate = redis.call('INCR', tool_rate_key)
if new_tool_rate == 1 then
    redis.call('PEXPIRE', tool_rate_key, window_ms)
end

redis.call('ZADD', tenant_concurrency_key, lease_expires_ms, lease_id)
redis.call('ZADD', actor_concurrency_key, lease_expires_ms, lease_id)
redis.call('ZADD', tool_concurrency_key, lease_expires_ms, lease_id)
redis.call('PEXPIRE', tenant_concurrency_key, lease_ttl_ms + 1000)
redis.call('PEXPIRE', actor_concurrency_key, lease_ttl_ms + 1000)
redis.call('PEXPIRE', tool_concurrency_key, lease_ttl_ms + 1000)

return {1, mode}
"""

_RELEASE_SCRIPT = r"""
local removed_tenant = redis.call('ZREM', KEYS[1], ARGV[1])
local removed_actor = redis.call('ZREM', KEYS[2], ARGV[1])
local removed_tool = redis.call('ZREM', KEYS[3], ARGV[1])
for index = 1, 3 do
    if redis.call('ZCARD', KEYS[index]) == 0 then
        redis.call('DEL', KEYS[index])
    end
end
return removed_tenant + removed_actor + removed_tool
"""

_INITIALIZE_CONTROL_SCRIPT = r"""
if redis.call('EXISTS', KEYS[1]) ~= 0 then
    return {0, 'already_initialized'}
end
redis.call('SET', KEYS[1], ARGV[1])
return {1, ARGV[1]}
"""

_CHANGE_CONTROL_SCRIPT = r"""
local current = redis.call('GET', KEYS[1])
if not current then
    return {0, 'control_missing'}
end
if current ~= ARGV[1] then
    return {0, 'compare_failed'}
end
redis.call('SET', KEYS[1], ARGV[2])
return {1, ARGV[2]}
"""


class JarvisAdmissionError(PermissionError):
    """Base denial for the distributed Jarvis admission boundary."""


class JarvisAdmissionInvalid(JarvisAdmissionError):
    """Admission inputs or policy are invalid."""


class JarvisAdmissionUnavailable(JarvisAdmissionError):
    """The distributed admission authority cannot fail safely."""


class JarvisAdmissionRateLimited(JarvisAdmissionError):
    """A tenant, actor or tool exceeded the request budget."""


class JarvisAdmissionConcurrencyLimited(JarvisAdmissionError):
    """A tenant, actor or tool exceeded the in-flight budget."""


class JarvisEmergencyHalt(JarvisAdmissionError):
    """Emergency execution stop is active."""


class JarvisReadOnlyModeDenied(JarvisAdmissionError):
    """The runtime is intentionally restricted to read-only tools."""


class JarvisControlConflict(JarvisAdmissionError):
    """A control-mode compare-and-set precondition failed."""


class JarvisExecutionAdmissionSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="OPEX_JARVIS_ADMISSION_",
        case_sensitive=False,
        extra="ignore",
    )

    tenant_requests_per_window: int = Field(default=30, ge=1, le=10_000)
    actor_requests_per_window: int = Field(default=10, ge=1, le=1_000)
    tool_requests_per_window: int = Field(default=20, ge=1, le=5_000)
    window_seconds: int = Field(default=60, ge=1, le=3600)
    tenant_concurrency: int = Field(default=4, ge=1, le=100)
    actor_concurrency: int = Field(default=2, ge=1, le=20)
    tool_concurrency: int = Field(default=3, ge=1, le=50)
    maximum_lease_ttl_seconds: int = Field(default=180, ge=20, le=300)

    @model_validator(mode="after")
    def validate_hierarchy(self) -> JarvisExecutionAdmissionSettings:
        if self.actor_requests_per_window > self.tenant_requests_per_window:
            raise ValueError("Jarvis actor request budget cannot exceed tenant budget")
        if self.tool_requests_per_window > self.tenant_requests_per_window:
            raise ValueError("Jarvis tool request budget cannot exceed tenant budget")
        if self.actor_concurrency > self.tenant_concurrency:
            raise ValueError("Jarvis actor concurrency cannot exceed tenant concurrency")
        if self.tool_concurrency > self.tenant_concurrency:
            raise ValueError("Jarvis tool concurrency cannot exceed tenant concurrency")
        return self


@dataclass(frozen=True)
class JarvisAdmissionLease:
    token: SecretStr
    lease_ttl_seconds: int
    control_mode: JarvisControlMode


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


def _decode_reason(value: object) -> str:
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission authority returned invalid text"
            ) from exc
    if not isinstance(value, str):
        raise JarvisAdmissionUnavailable(
            "Jarvis admission authority returned invalid text"
        )
    return value


def _validate_mode(mode: str) -> JarvisControlMode:
    if mode not in {"enabled", "read_only", "halted"}:
        raise JarvisAdmissionInvalid("Jarvis control mode is invalid")
    return mode  # type: ignore[return-value]


def _validate_control_transition(
    expected_mode: JarvisControlMode,
    new_mode: JarvisControlMode,
) -> None:
    if expected_mode == new_mode:
        raise JarvisAdmissionInvalid("Jarvis control transition is a no-op")
    if new_mode not in ALLOWED_CONTROL_TRANSITIONS[expected_mode]:
        raise JarvisAdmissionInvalid(
            "Jarvis control transition violates staged recovery policy"
        )


class RedisJarvisExecutionAdmissionStore:
    """Atomically enforce emergency mode, rate and concurrency budgets."""

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

    @property
    def control_key(self) -> str:
        return f"{self._key_prefix}:control:mode"

    def _keys(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        tool: str,
    ) -> tuple[str, str, str, str, str, str, str]:
        if not isinstance(tenant_id, UUID):
            raise JarvisAdmissionInvalid("Jarvis admission tenant is invalid")
        if (
            not isinstance(actor_subject, str)
            or not actor_subject
            or len(actor_subject) > 512
        ):
            raise JarvisAdmissionInvalid("Jarvis admission actor is invalid")
        if not isinstance(tool, str) or not tool or len(tool) > 128:
            raise JarvisAdmissionInvalid("Jarvis admission tool is invalid")

        tenant_digest = _scope_digest(f"tenant:{tenant_id}")
        actor_digest = _scope_digest(f"tenant:{tenant_id}:actor:{actor_subject}")
        tool_digest = _scope_digest(f"tenant:{tenant_id}:tool:{tool}")
        return (
            self.control_key,
            f"{self._key_prefix}:tenant:{tenant_digest}:rate",
            f"{self._key_prefix}:actor:{actor_digest}:rate",
            f"{self._key_prefix}:tool:{tool_digest}:rate",
            f"{self._key_prefix}:tenant:{tenant_digest}:concurrency",
            f"{self._key_prefix}:actor:{actor_digest}:concurrency",
            f"{self._key_prefix}:tool:{tool_digest}:concurrency",
        )

    async def initialize_control_mode(self, mode: JarvisControlMode) -> JarvisControlMode:
        mode = _validate_mode(mode)
        if mode != "halted":
            raise JarvisAdmissionInvalid(
                "Jarvis control must be initialized in halted mode"
            )
        try:
            response = await self._redis.eval(
                _INITIALIZE_CONTROL_SCRIPT,
                1,
                self.control_key,
                mode,
            )
        except RedisError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis control authority is unavailable"
            ) from exc
        return self._parse_control_write(response, expected_mode=mode)

    async def change_control_mode(
        self,
        *,
        expected_mode: JarvisControlMode,
        new_mode: JarvisControlMode,
    ) -> JarvisControlMode:
        expected_mode = _validate_mode(expected_mode)
        new_mode = _validate_mode(new_mode)
        _validate_control_transition(expected_mode, new_mode)
        try:
            response = await self._redis.eval(
                _CHANGE_CONTROL_SCRIPT,
                1,
                self.control_key,
                expected_mode,
                new_mode,
            )
        except RedisError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis control authority is unavailable"
            ) from exc
        return self._parse_control_write(response, expected_mode=new_mode)

    async def require_control_allows(
        self,
        *,
        side_effect_class: JarvisSideEffectClass,
    ) -> JarvisControlMode:
        if side_effect_class not in {"none", "read", "write", "irreversible"}:
            raise JarvisAdmissionInvalid("Jarvis side-effect class is invalid")
        try:
            raw_mode = await self._redis.get(self.control_key)
        except RedisError as exc:
            raise JarvisAdmissionUnavailable(
                "Jarvis control authority is unavailable"
            ) from exc
        if raw_mode is None:
            raise JarvisAdmissionUnavailable("Jarvis control state is missing")

        mode = _decode_reason(raw_mode)
        if mode == "halted":
            raise JarvisEmergencyHalt("Jarvis emergency stop is active")
        if mode == "read_only":
            if side_effect_class not in {"none", "read"}:
                raise JarvisReadOnlyModeDenied("Jarvis runtime is read-only")
            return "read_only"
        if mode == "enabled":
            return "enabled"
        raise JarvisAdmissionUnavailable("Jarvis control state is invalid")

    @staticmethod
    def _parse_control_write(
        response: object,
        *,
        expected_mode: JarvisControlMode,
    ) -> JarvisControlMode:
        if not isinstance(response, (list, tuple)) or len(response) != 2:
            raise JarvisAdmissionUnavailable(
                "Jarvis control authority returned an invalid result"
            )
        accepted, reason = response
        reason = _decode_reason(reason)
        if accepted in {1, "1", b"1"} and reason == expected_mode:
            return expected_mode
        if accepted not in {0, "0", b"0"}:
            raise JarvisAdmissionUnavailable(
                "Jarvis control authority returned an invalid decision"
            )
        if reason in {"already_initialized", "compare_failed"}:
            raise JarvisControlConflict("Jarvis control state changed concurrently")
        if reason == "control_missing":
            raise JarvisAdmissionUnavailable("Jarvis control state is missing")
        raise JarvisAdmissionUnavailable(
            "Jarvis control authority returned an unknown denial"
        )

    async def acquire(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        tool: str,
        side_effect_class: JarvisSideEffectClass,
        request_timeout_seconds: float,
    ) -> JarvisAdmissionLease:
        if side_effect_class not in {"none", "read", "write", "irreversible"}:
            raise JarvisAdmissionInvalid("Jarvis side-effect class is invalid")
        keys = self._keys(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            tool=tool,
        )
        lease_ttl_seconds = broker_lease_ttl_seconds(
            request_timeout_seconds,
            maximum_lease_ttl_seconds=self._settings.maximum_lease_ttl_seconds,
        )
        lease_token = secrets.token_urlsafe(32)

        try:
            response = await self._redis.eval(
                _ADMIT_SCRIPT,
                len(keys),
                *keys,
                self._settings.tenant_requests_per_window,
                self._settings.actor_requests_per_window,
                self._settings.tool_requests_per_window,
                self._settings.window_seconds * 1000,
                self._settings.tenant_concurrency,
                self._settings.actor_concurrency,
                self._settings.tool_concurrency,
                lease_ttl_seconds * 1000,
                lease_token,
                side_effect_class,
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
        reason = _decode_reason(reason)
        if admitted in {1, "1", b"1"} and reason in {"enabled", "read_only"}:
            return JarvisAdmissionLease(
                token=SecretStr(lease_token),
                lease_ttl_seconds=lease_ttl_seconds,
                control_mode=reason,  # type: ignore[arg-type]
            )
        if admitted not in {0, "0", b"0"}:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission authority returned an invalid decision"
            )
        if reason in {"tenant_rate", "actor_rate", "tool_rate"}:
            raise JarvisAdmissionRateLimited("Jarvis execution rate limit exceeded")
        if reason in {
            "tenant_concurrency",
            "actor_concurrency",
            "tool_concurrency",
        }:
            raise JarvisAdmissionConcurrencyLimited(
                "Jarvis execution concurrency limit exceeded"
            )
        if reason == "halted":
            raise JarvisEmergencyHalt("Jarvis emergency stop is active")
        if reason == "read_only":
            raise JarvisReadOnlyModeDenied("Jarvis runtime is read-only")
        if reason in {"control_missing", "control_invalid"}:
            raise JarvisAdmissionUnavailable(
                "Jarvis control state is unavailable"
            )
        raise JarvisAdmissionUnavailable(
            "Jarvis admission authority returned an unknown denial"
        )

    async def release(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        tool: str,
        lease: JarvisAdmissionLease,
    ) -> None:
        keys = self._keys(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            tool=tool,
        )
        if not isinstance(lease, JarvisAdmissionLease):
            raise JarvisAdmissionInvalid("Jarvis admission lease is invalid")
        lease_token = lease.token.get_secret_value()
        if len(lease_token) < 32 or len(lease_token) > 256:
            raise JarvisAdmissionInvalid("Jarvis admission lease is invalid")

        try:
            response = await self._redis.eval(
                _RELEASE_SCRIPT,
                3,
                keys[4],
                keys[5],
                keys[6],
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
        if response not in {0, 1, 2, 3}:
            raise JarvisAdmissionUnavailable(
                "Jarvis admission release returned an invalid count"
            )
