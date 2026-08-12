from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.jarvis_execution_admission import (
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionUnavailable,
    JarvisControlConflict,
    JarvisEmergencyHalt,
    JarvisExecutionAdmissionSettings,
    RedisJarvisExecutionAdmissionStore,
)

pytestmark = pytest.mark.skipif(
    os.getenv("EAY_RUN_JARVIS_ADMISSION_REDIS_TEST") != "1",
    reason="Jarvis admission Redis integration is opt-in",
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "runtime-sensitive-actor"
TOOL = "ops_kpi_query"


async def delete_prefix(redis: Redis, prefix: str) -> None:
    keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
    if keys:
        await redis.delete(*keys)


@pytest.mark.asyncio
async def test_runtime_admission_is_atomic_fail_closed_and_emergency_stoppable() -> None:
    redis = Redis.from_url(
        get_settings().redis_url,
        decode_responses=True,
    )
    prefix = f"opex:{{ai}}:jarvis-admission-test:{uuid4().hex}"
    store = RedisJarvisExecutionAdmissionStore(
        redis,
        JarvisExecutionAdmissionSettings(
            tenant_requests_per_window=20,
            actor_requests_per_window=10,
            tool_requests_per_window=20,
            window_seconds=60,
            tenant_concurrency=2,
            actor_concurrency=1,
            tool_concurrency=2,
            maximum_lease_ttl_seconds=180,
        ),
        key_prefix=prefix,
    )

    try:
        await delete_prefix(redis, prefix)

        with pytest.raises(JarvisAdmissionUnavailable):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                tool=TOOL,
                side_effect_class="read",
                request_timeout_seconds=30,
            )

        assert await store.initialize_control_mode("halted") == "halted"

        with pytest.raises(JarvisEmergencyHalt):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                tool=TOOL,
                side_effect_class="read",
                request_timeout_seconds=30,
            )

        assert (
            await store.change_control_mode(
                expected_mode="halted",
                new_mode="enabled",
            )
            == "enabled"
        )

        with pytest.raises(JarvisControlConflict):
            await store.change_control_mode(
                expected_mode="halted",
                new_mode="read_only",
            )

        first = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )

        with pytest.raises(JarvisAdmissionConcurrencyLimited):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                tool=TOOL,
                side_effect_class="read",
                request_timeout_seconds=30,
            )

        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        assert keys
        for sensitive in (str(TENANT), ACTOR, TOOL):
            assert all(sensitive not in key for key in keys)

        await store.release(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            lease=first,
        )

        second = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )

        assert (
            await store.change_control_mode(
                expected_mode="enabled",
                new_mode="halted",
            )
            == "halted"
        )

        with pytest.raises(JarvisEmergencyHalt):
            await store.require_control_allows(side_effect_class="read")

        await store.release(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            lease=second,
        )
    finally:
        await delete_prefix(redis, prefix)
        await redis.aclose()
