"""Privacy-minimal request idempotency for governed Jarvis execution.

Only a hashed client key plus a request fingerprint/state are stored in Redis.
No grant, raw arguments, reason, actor, tenant or result rows are persisted.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.ai_tool_authorization import AiToolCapability

JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS = 24 * 60 * 60
JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS = 7 * 24 * 60 * 60
JARVIS_IDEMPOTENCY_VERSION = 1
JARVIS_IDEMPOTENCY_KEY_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$"
)
SHA256_PATTERN = r"^[0-9a-f]{64}$"

IdempotencyState = Literal[
    "reserved",
    "dispatched",
    "completed",
    "indeterminate",
    "denied",
]

_TRANSITION_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return 0
end
if current ~= ARGV[1] then
  return -1
end
redis.call('SET', KEYS[1], ARGV[2], 'EX', ARGV[3])
return 1
"""

_RELEASE_SCRIPT = """
local current = redis.call('GET', KEYS[1])
if not current then
  return 0
end
if current ~= ARGV[1] then
  return -1
end
redis.call('DEL', KEYS[1])
return 1
"""


class JarvisIdempotencyError(RuntimeError):
    """Base idempotency authority failure."""


class JarvisIdempotencyInvalid(JarvisIdempotencyError):
    """Idempotency input is invalid."""


class JarvisIdempotencyConflict(JarvisIdempotencyError):
    """The same client key was used for a different governed request."""


class JarvisIdempotencyReplay(JarvisIdempotencyError):
    """The same governed request has already claimed this client key."""

    def __init__(self, state: IdempotencyState) -> None:
        super().__init__("Jarvis idempotency key has already been used")
        self.state = state


class JarvisIdempotencyUnavailable(JarvisIdempotencyError):
    """Distributed idempotency authority is unavailable or inconsistent."""


class JarvisIdempotencyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: Literal[1] = JARVIS_IDEMPOTENCY_VERSION
    request_fingerprint: str = Field(pattern=SHA256_PATTERN)
    state: IdempotencyState


def validate_idempotency_key(value: str) -> str:
    if not isinstance(value, str) or not JARVIS_IDEMPOTENCY_KEY_PATTERN.fullmatch(
        value
    ):
        raise JarvisIdempotencyInvalid(
            "Jarvis idempotency key is invalid"
        )
    return value


def _canonical_json_sha256(value: Mapping[str, Any]) -> str:
    try:
        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise JarvisIdempotencyInvalid(
            "Jarvis idempotency request cannot be canonicalized"
        ) from exc
    return hashlib.sha256(encoded).hexdigest()


def build_execution_request_fingerprint(
    capability: AiToolCapability,
    *,
    arguments_sha256: str,
    reason_sha256: str,
    execution_policy: Mapping[str, Any],
) -> str:
    if not re.fullmatch(SHA256_PATTERN, arguments_sha256):
        raise JarvisIdempotencyInvalid("Arguments fingerprint is invalid")
    if not re.fullmatch(SHA256_PATTERN, reason_sha256):
        raise JarvisIdempotencyInvalid("Reason fingerprint is invalid")

    policy_sha256 = _canonical_json_sha256(execution_policy)
    return _canonical_json_sha256(
        {
            "tenant_id": str(capability.tenant_id),
            "actor_subject": capability.actor_subject,
            "tool": capability.tool,
            "arguments_sha256": arguments_sha256,
            "reason_sha256": reason_sha256,
            "authorization_fingerprint": (
                capability.authorization_fingerprint
            ),
            "execution_policy_sha256": policy_sha256,
        }
    )


def _serialize(record: JarvisIdempotencyRecord) -> str:
    return json.dumps(
        record.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
    )


class RedisJarvisExecutionIdempotencyStore:
    """Atomically reserve and transition one governed request key."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = "opex:{ai}:execution-idempotency",
        ttl_seconds: int = JARVIS_IDEMPOTENCY_DEFAULT_TTL_SECONDS,
    ) -> None:
        if (
            not isinstance(key_prefix, str)
            or not key_prefix
            or len(key_prefix) > 128
        ):
            raise ValueError("Jarvis idempotency key prefix is invalid")
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 60 <= ttl_seconds <= JARVIS_IDEMPOTENCY_MAX_TTL_SECONDS
        ):
            raise ValueError("Jarvis idempotency TTL is invalid")

        self._redis = redis_client
        self._key_prefix = key_prefix
        self._ttl_seconds = ttl_seconds

    def _key(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
    ) -> str:
        validate_idempotency_key(idempotency_key)
        if not isinstance(actor_subject, str) or not actor_subject:
            raise JarvisIdempotencyInvalid("Jarvis actor subject is invalid")

        digest = hashlib.sha256(
            (
                f"{tenant_id}\n{actor_subject}\n{idempotency_key}"
            ).encode("utf-8")
        ).hexdigest()
        return f"{self._key_prefix}:{digest}"

    async def reserve(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JarvisIdempotencyRecord:
        record = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state="reserved",
        )
        payload = _serialize(record)
        key = self._key(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
        )

        try:
            created = await self._redis.set(
                key,
                payload,
                ex=self._ttl_seconds,
                nx=True,
            )
            if created is True:
                return record
            existing_payload = await self._redis.get(key)
        except RedisError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency authority is unavailable"
            ) from exc

        if existing_payload is None:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency reservation changed unexpectedly"
            )
        if isinstance(existing_payload, bytes):
            try:
                existing_payload = existing_payload.decode("utf-8")
            except UnicodeError as exc:
                raise JarvisIdempotencyUnavailable(
                    "Stored Jarvis idempotency state is invalid"
                ) from exc

        try:
            existing = JarvisIdempotencyRecord.model_validate_json(
                existing_payload
            )
        except (TypeError, ValueError) as exc:
            raise JarvisIdempotencyUnavailable(
                "Stored Jarvis idempotency state is invalid"
            ) from exc

        if existing.request_fingerprint != request_fingerprint:
            raise JarvisIdempotencyConflict(
                "Jarvis idempotency key conflicts with another request"
            )
        raise JarvisIdempotencyReplay(existing.state)

    async def transition(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
        expected_state: IdempotencyState,
        new_state: IdempotencyState,
    ) -> JarvisIdempotencyRecord:
        expected = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state=expected_state,
        )
        updated = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state=new_state,
        )
        key = self._key(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
        )

        try:
            result = await self._redis.eval(
                _TRANSITION_SCRIPT,
                1,
                key,
                _serialize(expected),
                _serialize(updated),
                str(self._ttl_seconds),
            )
        except RedisError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency transition is unavailable"
            ) from exc

        if result != 1:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency state changed unexpectedly"
            )
        return updated

    async def release_reserved(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> None:
        expected = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state="reserved",
        )
        key = self._key(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
        )

        try:
            result = await self._redis.eval(
                _RELEASE_SCRIPT,
                1,
                key,
                _serialize(expected),
            )
        except RedisError as exc:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency release is unavailable"
            ) from exc

        if result not in {0, 1}:
            raise JarvisIdempotencyUnavailable(
                "Jarvis idempotency state changed unexpectedly"
            )
