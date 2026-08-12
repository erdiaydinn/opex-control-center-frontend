"""Adversarial tests for Jarvis service assertion replay protection."""

from unittest.mock import AsyncMock, patch

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.jarvis_service_identity import (
    JARVIS_SERVICE_SUBJECT,
    JarvisServiceAssertionInvalid,
    JarvisServiceVerifierSettings,
    VerifiedJarvisService,
)
from app.core.jarvis_service_replay import (
    JarvisServiceReplayDetected,
    JarvisServiceReplayInvalid,
    JarvisServiceReplayUnavailable,
    RedisJarvisServiceReplayGuard,
    verify_and_consume_jarvis_service_assertion,
)

ASSERTION_ID = "jarvis-service-replay-test-0001"


def _verified(*, replay_ttl_seconds: int = 40) -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject=JARVIS_SERVICE_SUBJECT,
        assertion_id=ASSERTION_ID,
        issued_at=1_700_000_000,
        expires_at=1_700_000_030,
        replay_ttl_seconds=replay_ttl_seconds,
    )


def test_raw_assertion_identifier_is_not_exposed_in_redis_key() -> None:
    guard = RedisJarvisServiceReplayGuard(AsyncMock())

    key = guard._key(ASSERTION_ID)

    assert ASSERTION_ID not in key
    digest = key.rsplit(":", 1)[-1]
    assert len(digest) == 64
    assert all(character in "0123456789abcdef" for character in digest)


@pytest.mark.asyncio
async def test_first_consume_uses_atomic_set_nx_ex() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    guard = RedisJarvisServiceReplayGuard(redis)

    await guard.consume(_verified())

    redis.set.assert_awaited_once()
    args, kwargs = redis.set.await_args
    assert len(args) == 2
    assert args[1] == "1"
    assert ASSERTION_ID not in args[0]
    assert kwargs == {"ex": 40, "nx": True}


@pytest.mark.asyncio
async def test_second_consume_is_rejected_as_replay() -> None:
    redis = AsyncMock()
    redis.set.return_value = None
    guard = RedisJarvisServiceReplayGuard(redis)

    with pytest.raises(JarvisServiceReplayDetected):
        await guard.consume(_verified())


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed() -> None:
    redis = AsyncMock()
    redis.set.side_effect = RedisConnectionError("simulated outage")
    guard = RedisJarvisServiceReplayGuard(redis)

    with pytest.raises(JarvisServiceReplayUnavailable):
        await guard.consume(_verified())


@pytest.mark.parametrize("ttl", [0, -1, 41, True, 1.5])
@pytest.mark.asyncio
async def test_invalid_replay_ttl_is_rejected_before_redis(ttl) -> None:
    redis = AsyncMock()
    guard = RedisJarvisServiceReplayGuard(redis)

    with pytest.raises(
        JarvisServiceReplayInvalid,
        match="replay TTL is invalid",
    ):
        await guard.consume(_verified(replay_ttl_seconds=ttl))

    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_wrong_subject_is_rejected_before_redis() -> None:
    redis = AsyncMock()
    guard = RedisJarvisServiceReplayGuard(redis)
    verified = _verified().model_copy(
        update={"service_subject": "identity-gateway"}
    )

    with pytest.raises(
        JarvisServiceReplayInvalid,
        match="subject is invalid",
    ):
        await guard.consume(verified)

    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_verification_failure_never_touches_replay_store() -> None:
    redis = AsyncMock()
    guard = RedisJarvisServiceReplayGuard(redis)
    settings = JarvisServiceVerifierSettings(jwks_file="unused.json")

    with patch(
        "app.core.jarvis_service_replay.verify_jarvis_service_assertion",
        side_effect=JarvisServiceAssertionInvalid("bad assertion"),
    ):
        with pytest.raises(JarvisServiceAssertionInvalid):
            await verify_and_consume_jarvis_service_assertion(
                "bad-token",
                settings,
                guard,
            )

    redis.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_verified_assertion_is_consumed_before_return() -> None:
    redis = AsyncMock()
    redis.set.return_value = True
    guard = RedisJarvisServiceReplayGuard(redis)
    settings = JarvisServiceVerifierSettings(jwks_file="unused.json")
    verified = _verified(replay_ttl_seconds=17)

    with patch(
        "app.core.jarvis_service_replay.verify_jarvis_service_assertion",
        return_value=verified,
    ) as verifier:
        result = await verify_and_consume_jarvis_service_assertion(
            "signed-token",
            settings,
            guard,
            now=1_700_000_005.0,
        )

    verifier.assert_called_once_with(
        "signed-token",
        settings,
        now=1_700_000_005.0,
    )
    assert result == verified
    assert redis.set.await_count == 1
    _, kwargs = redis.set.await_args
    assert kwargs == {"ex": 17, "nx": True}
