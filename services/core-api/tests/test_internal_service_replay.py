"""Adversarial tests for internal service assertion replay protection."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import (
    ConnectionError as RedisConnectionError,
)

from app.core.internal_service_replay import (
    InternalServiceReplayDetected,
    InternalServiceReplayUnavailable,
    RedisInternalServiceReplayGuard,
)

ASSERTION_ID = (
    "service-assertion-replay-test-0001"
)


def test_raw_assertion_identifier_is_not_exposed_in_redis_key() -> None:
    redis = AsyncMock()

    guard = RedisInternalServiceReplayGuard(
        redis
    )

    key = guard._key(
        ASSERTION_ID
    )

    assert ASSERTION_ID not in key

    digest = key.rsplit(
        ":",
        1,
    )[-1]

    assert len(digest) == 64

    assert all(
        character
        in "0123456789abcdef"
        for character in digest
    )


@pytest.mark.asyncio
async def test_first_consume_uses_atomic_set_nx_ex() -> None:
    redis = AsyncMock()

    redis.set.return_value = True

    guard = RedisInternalServiceReplayGuard(
        redis
    )

    await guard.consume(
        assertion_id=ASSERTION_ID,
        ttl_seconds=70,
    )

    redis.set.assert_awaited_once()

    args, kwargs = (
        redis.set.await_args
    )

    assert len(args) == 2
    assert args[1] == "1"

    assert ASSERTION_ID not in args[0]

    assert kwargs == {
        "ex": 70,
        "nx": True,
    }


@pytest.mark.asyncio
async def test_second_consume_is_rejected_as_replay() -> None:
    redis = AsyncMock()

    redis.set.return_value = None

    guard = RedisInternalServiceReplayGuard(
        redis
    )

    with pytest.raises(
        InternalServiceReplayDetected
    ):
        await guard.consume(
            assertion_id=ASSERTION_ID,
            ttl_seconds=70,
        )


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed() -> None:
    redis = AsyncMock()

    redis.set.side_effect = (
        RedisConnectionError(
            "simulated outage"
        )
    )

    guard = RedisInternalServiceReplayGuard(
        redis
    )

    with pytest.raises(
        InternalServiceReplayUnavailable
    ):
        await guard.consume(
            assertion_id=ASSERTION_ID,
            ttl_seconds=70,
        )


@pytest.mark.parametrize(
    "ttl",
    [
        0,
        -1,
        121,
        True,
        1.5,
    ],
)
@pytest.mark.asyncio
async def test_invalid_replay_ttl_is_rejected_before_redis(
    ttl,
) -> None:
    redis = AsyncMock()

    guard = RedisInternalServiceReplayGuard(
        redis
    )

    with pytest.raises(
        ValueError,
        match="replay TTL is invalid",
    ):
        await guard.consume(
            assertion_id=ASSERTION_ID,
            ttl_seconds=ttl,
        )

    redis.set.assert_not_awaited()
