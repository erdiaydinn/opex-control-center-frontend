"""Single-use replay protection for verified Jarvis service assertions.

The verifier proves that a short-lived assertion was signed by the dedicated
EAY AI Core trust root. This module consumes that verified assertion exactly
once through Redis before any Jarvis execution grant may be used.
"""

from __future__ import annotations

import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.jarvis_service_identity import (
    JARVIS_SERVICE_MAX_LIFETIME_SECONDS,
    JARVIS_SERVICE_REPLAY_SKEW_SECONDS,
    JARVIS_SERVICE_SUBJECT,
    JTI_PATTERN,
    JarvisServiceVerifierSettings,
    VerifiedJarvisService,
    verify_jarvis_service_assertion,
)

JARVIS_SERVICE_REPLAY_MAX_TTL_SECONDS = (
    JARVIS_SERVICE_MAX_LIFETIME_SECONDS
    + JARVIS_SERVICE_REPLAY_SKEW_SECONDS
)


class JarvisServiceReplayError(PermissionError):
    """Base denial for Jarvis service assertion replay controls."""


class JarvisServiceReplayDetected(JarvisServiceReplayError):
    """The verified Jarvis assertion has already been consumed."""


class JarvisServiceReplayUnavailable(JarvisServiceReplayError):
    """The distributed Jarvis replay authority is unavailable."""


class JarvisServiceReplayInvalid(JarvisServiceReplayError):
    """The verified assertion cannot be consumed safely."""


class RedisJarvisServiceReplayGuard:
    """Atomically consume verified Jarvis assertions by hashed JTI."""

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = "opex:{jarvis}:service-replay",
    ) -> None:
        if (
            not isinstance(key_prefix, str)
            or not key_prefix
            or len(key_prefix) > 128
        ):
            raise ValueError("Jarvis service replay key prefix is invalid")

        self._redis = redis_client
        self._key_prefix = key_prefix

    def _key(self, assertion_id: str) -> str:
        if (
            not isinstance(assertion_id, str)
            or not JTI_PATTERN.fullmatch(assertion_id)
        ):
            raise JarvisServiceReplayInvalid(
                "Jarvis service assertion identifier is invalid"
            )

        digest = hashlib.sha256(assertion_id.encode("utf-8")).hexdigest()
        return f"{self._key_prefix}:{digest}"

    async def consume(self, verified: VerifiedJarvisService) -> None:
        if not isinstance(verified, VerifiedJarvisService):
            raise JarvisServiceReplayInvalid(
                "Verified Jarvis service identity is required"
            )

        if verified.service_subject != JARVIS_SERVICE_SUBJECT:
            raise JarvisServiceReplayInvalid(
                "Jarvis service subject is invalid"
            )

        ttl_seconds = verified.replay_ttl_seconds
        if (
            isinstance(ttl_seconds, bool)
            or not isinstance(ttl_seconds, int)
            or not 1 <= ttl_seconds <= JARVIS_SERVICE_REPLAY_MAX_TTL_SECONDS
        ):
            raise JarvisServiceReplayInvalid(
                "Jarvis service replay TTL is invalid"
            )

        key = self._key(verified.assertion_id)

        try:
            consumed = await self._redis.set(
                key,
                "1",
                ex=ttl_seconds,
                nx=True,
            )
        except RedisError as exc:
            raise JarvisServiceReplayUnavailable(
                "Jarvis service replay authority is unavailable"
            ) from exc

        if consumed is not True:
            raise JarvisServiceReplayDetected(
                "Jarvis service assertion has already been consumed"
            )


async def verify_and_consume_jarvis_service_assertion(
    token: str,
    settings: JarvisServiceVerifierSettings,
    replay_guard: RedisJarvisServiceReplayGuard,
    *,
    now: float | None = None,
) -> VerifiedJarvisService:
    """Verify the machine assertion and burn its JTI before execution."""

    verified = verify_jarvis_service_assertion(
        token,
        settings,
        now=now,
    )
    await replay_guard.consume(verified)
    return verified
