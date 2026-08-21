"""Single-use replay protection for internal service assertions."""

import hashlib

from redis.asyncio import Redis
from redis.exceptions import RedisError

INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS = 120
INTERNAL_SERVICE_REPLAY_TTL_SKEW_SECONDS = 10

class InternalServiceReplayError(
    PermissionError
):
    """Base denial for internal service assertion replay controls."""


class InternalServiceReplayDetected(
    InternalServiceReplayError
):
    """The service assertion identifier has already been consumed."""


class InternalServiceReplayUnavailable(
    InternalServiceReplayError
):
    """The distributed replay authority cannot be reached safely."""


class RedisInternalServiceReplayGuard:
    """
    Atomically consume a verified service-assertion JTI.

    Raw assertion identifiers are never stored in Redis keys.
    """

    def __init__(
        self,
        redis_client: Redis,
        *,
        key_prefix: str = (
            "opex:{identity}:service-replay"
        ),
    ) -> None:
        if (
            not isinstance(
                key_prefix,
                str,
            )
            or not key_prefix
            or len(key_prefix) > 128
        ):
            raise ValueError(
                "Internal service replay key prefix is invalid"
            )

        self._redis = redis_client
        self._key_prefix = key_prefix


    def _key(
        self,
        assertion_id: str,
    ) -> str:
        if (
            not isinstance(
                assertion_id,
                str,
            )
            or not assertion_id
            or len(assertion_id) > 128
        ):
            raise ValueError(
                "Internal service assertion identifier is invalid"
            )

        digest = hashlib.sha256(
            assertion_id.encode(
                "utf-8"
            )
        ).hexdigest()

        return (
            self._key_prefix
            + ":"
            + digest
        )


    async def consume(
        self,
        *,
        assertion_id: str,
        ttl_seconds: int,
    ) -> None:
        if (
            isinstance(
                ttl_seconds,
                bool,
            )
            or not isinstance(
                ttl_seconds,
                int,
            )
            or not (
                1
                <= ttl_seconds
                <= INTERNAL_SERVICE_REPLAY_MAX_TTL_SECONDS
            )
        ):
            raise ValueError(
                "Internal service replay TTL is invalid"
            )

        key = self._key(
            assertion_id
        )

        try:
            consumed = (
                await self._redis.set(
                    key,
                    "1",
                    ex=ttl_seconds,
                    nx=True,
                )
            )

        except RedisError as exc:
            raise (
                InternalServiceReplayUnavailable(
                    "Internal service replay authority "
                    "is unavailable"
                )
            ) from exc

        # redis-py returns True only when SET NX succeeded.
        # None/False means this JTI already exists.
        if consumed is not True:
            raise (
                InternalServiceReplayDetected(
                    "Internal service assertion "
                    "has already been consumed"
                )
            )
