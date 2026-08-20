"""Fail-closed request idempotency for user-issued Jarvis Grant V4 tokens.

Grant V4 consumption is already atomic and single-use. This guard closes the
remaining browser/network retry gap at *grant issuance*: the same
Idempotency-Key cannot mint a second short-lived grant, and the same key
cannot be reused for a different reviewed invocation.

Redis stores only SHA-256 scoped identifiers and one request fingerprint.
Raw idempotency keys, tenant/actor values, arguments, human reasons and grant
tokens are never persisted by this authority.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from redis.asyncio import Redis
from redis.exceptions import RedisError

GRANT_IDEMPOTENCY_KEY_PREFIX = "opex:{ai}:grant-issue-idempotency"
GRANT_IDEMPOTENCY_TTL_SECONDS = 120

_RELEASE_SCRIPT = r"""
local current = redis.call('GET', KEYS[1])
if not current then
    return 0
end
if current ~= ARGV[1] then
    return -1
end
return redis.call('DEL', KEYS[1])
"""


class JarvisGrantIdempotencyError(RuntimeError):
    """Base error for Grant V4 issuance idempotency."""


class JarvisGrantIdempotencyInvalid(JarvisGrantIdempotencyError):
    """The request cannot be represented safely."""


class JarvisGrantIdempotencyConflict(JarvisGrantIdempotencyError):
    """The same idempotency key was used for a different request."""


class JarvisGrantIdempotencyReplay(JarvisGrantIdempotencyError):
    """The same protected request was already reserved/issued."""


class JarvisGrantIdempotencyUnavailable(JarvisGrantIdempotencyError):
    """The distributed retry authority is unavailable."""


@dataclass(frozen=True)
class JarvisGrantIdempotencyReservation:
    redis_key: str
    request_fingerprint: str


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def grant_issue_request_fingerprint(
    *,
    tenant_id: UUID,
    actor_subject: str,
    tool: str,
    arguments_sha256: str,
    reason_sha256: str,
    authorization_fingerprint: str,
    data_scope_fingerprint: str,
) -> str:
    """Bind the retry key to exact server-derived authority and invocation."""

    if not isinstance(tenant_id, UUID):
        raise JarvisGrantIdempotencyInvalid("Grant tenant is invalid")
    if not isinstance(actor_subject, str) or not actor_subject:
        raise JarvisGrantIdempotencyInvalid("Grant actor is invalid")

    values = {
        "version": 1,
        "tenant_id": str(tenant_id),
        "actor_subject": actor_subject,
        "tool": tool,
        "arguments_sha256": arguments_sha256,
        "reason_sha256": reason_sha256,
        "authorization_fingerprint": authorization_fingerprint,
        "data_scope_fingerprint": data_scope_fingerprint,
    }
    encoded = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return _sha256(encoded)


class RedisJarvisGrantIdempotencyStore:
    """Reserve one retry key before issuing a Grant V4 token."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = GRANT_IDEMPOTENCY_KEY_PREFIX,
        ttl_seconds: int = GRANT_IDEMPOTENCY_TTL_SECONDS,
    ) -> None:
        if (
            not isinstance(key_prefix, str)
            or not key_prefix
            or len(key_prefix) > 128
            or "{ai}" not in key_prefix
        ):
            raise ValueError("Grant idempotency key prefix is invalid")
        if isinstance(ttl_seconds, bool) or not 60 <= ttl_seconds <= 600:
            raise ValueError("Grant idempotency TTL is invalid")
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
        if not isinstance(tenant_id, UUID):
            raise JarvisGrantIdempotencyInvalid("Grant tenant is invalid")
        if (
            not isinstance(actor_subject, str)
            or not actor_subject
            or len(actor_subject) > 512
        ):
            raise JarvisGrantIdempotencyInvalid("Grant actor is invalid")
        if (
            not isinstance(idempotency_key, str)
            or not 8 <= len(idempotency_key) <= 200
        ):
            raise JarvisGrantIdempotencyInvalid(
                "Idempotency-Key must be between 8 and 200 characters"
            )

        scope = _sha256(
            f"tenant:{tenant_id}:actor:{actor_subject}:key:{idempotency_key}"
        )
        return f"{self._key_prefix}:{scope}"

    async def reserve(
        self,
        *,
        tenant_id: UUID,
        actor_subject: str,
        idempotency_key: str,
        request_fingerprint: str,
    ) -> JarvisGrantIdempotencyReservation:
        if (
            not isinstance(request_fingerprint, str)
            or len(request_fingerprint) != 64
            or any(character not in "0123456789abcdef" for character in request_fingerprint)
        ):
            raise JarvisGrantIdempotencyInvalid(
                "Grant request fingerprint is invalid"
            )

        redis_key = self._key(
            tenant_id=tenant_id,
            actor_subject=actor_subject,
            idempotency_key=idempotency_key,
        )
        try:
            created = await self._redis.set(
                redis_key,
                request_fingerprint,
                ex=self._ttl_seconds,
                nx=True,
            )
            if created is True:
                return JarvisGrantIdempotencyReservation(
                    redis_key=redis_key,
                    request_fingerprint=request_fingerprint,
                )

            existing = await self._redis.get(redis_key)
        except RedisError as exc:
            raise JarvisGrantIdempotencyUnavailable(
                "Grant idempotency authority is unavailable"
            ) from exc

        if isinstance(existing, bytes):
            existing = existing.decode("ascii", errors="strict")
        if existing == request_fingerprint:
            raise JarvisGrantIdempotencyReplay(
                "Grant issuance replay is blocked"
            )
        if isinstance(existing, str):
            raise JarvisGrantIdempotencyConflict(
                "Idempotency-Key is bound to a different request"
            )
        raise JarvisGrantIdempotencyUnavailable(
            "Grant idempotency authority returned an invalid state"
        )

    async def release(
        self,
        reservation: JarvisGrantIdempotencyReservation,
    ) -> None:
        """Release only pre-grant failures; successful issuance remains blocked."""

        if not isinstance(reservation, JarvisGrantIdempotencyReservation):
            raise JarvisGrantIdempotencyInvalid(
                "Grant idempotency reservation is invalid"
            )
        try:
            result = await self._redis.eval(
                _RELEASE_SCRIPT,
                1,
                reservation.redis_key,
                reservation.request_fingerprint,
            )
        except RedisError as exc:
            raise JarvisGrantIdempotencyUnavailable(
                "Grant idempotency reservation could not be released"
            ) from exc
        if result not in {0, 1}:
            raise JarvisGrantIdempotencyUnavailable(
                "Grant idempotency release returned an invalid state"
            )
