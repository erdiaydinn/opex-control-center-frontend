from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.jarvis_execution_admission import (
    JarvisAdmissionUnavailable,
    JarvisEmergencyHalt,
    JarvisExecutionAdmissionSettings,
    JarvisReadOnlyModeDenied,
    RedisJarvisExecutionAdmissionStore,
)


def store(redis: AsyncMock) -> RedisJarvisExecutionAdmissionStore:
    return RedisJarvisExecutionAdmissionStore(
        redis,
        JarvisExecutionAdmissionSettings(),
    )


@pytest.mark.asyncio
async def test_control_recheck_accepts_enabled_and_read_only_reads() -> None:
    redis = AsyncMock()
    redis.get.side_effect = (b"enabled", b"read_only")
    admission = store(redis)

    assert await admission.require_control_allows(side_effect_class="read") == "enabled"
    assert await admission.require_control_allows(side_effect_class="read") == "read_only"
    assert redis.eval.await_count == 0


@pytest.mark.asyncio
async def test_control_recheck_halt_is_immediate_fail_closed() -> None:
    redis = AsyncMock()
    redis.get.return_value = b"halted"

    with pytest.raises(JarvisEmergencyHalt):
        await store(redis).require_control_allows(side_effect_class="read")


@pytest.mark.asyncio
async def test_control_recheck_read_only_denies_mutation() -> None:
    redis = AsyncMock()
    redis.get.return_value = b"read_only"

    with pytest.raises(JarvisReadOnlyModeDenied):
        await store(redis).require_control_allows(side_effect_class="write")


@pytest.mark.parametrize(
    "control_value",
    [None, b"invalid", "invalid", b"\xff"],
)
@pytest.mark.asyncio
async def test_missing_malformed_or_non_utf8_control_fails_closed(control_value) -> None:
    redis = AsyncMock()
    redis.get.return_value = control_value

    with pytest.raises(JarvisAdmissionUnavailable):
        await store(redis).require_control_allows(side_effect_class="read")


@pytest.mark.asyncio
async def test_control_redis_outage_fails_closed() -> None:
    redis = AsyncMock()
    redis.get.side_effect = RedisConnectionError("simulated outage")

    with pytest.raises(JarvisAdmissionUnavailable):
        await store(redis).require_control_allows(side_effect_class="read")
