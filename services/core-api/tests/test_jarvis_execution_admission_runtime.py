import os
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.core.jarvis_execution_admission import (
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionRateLimited,
    JarvisExecutionAdmissionSettings,
    RedisJarvisExecutionAdmissionStore,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "runtime-admission-actor"


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.getenv("EAY_RUN_JARVIS_ADMISSION_REDIS_TEST") != "1",
    reason="real Redis admission test is opt-in",
)
async def test_real_redis_enforces_concurrency_then_rate_without_raw_identity() -> None:
    redis = Redis.from_url(
        os.environ["OPEX_REDIS_URL"],
        decode_responses=True,
    )
    prefix = f"opex:{{ai}}:jarvis-admission-test:{uuid4().hex}"
    store = RedisJarvisExecutionAdmissionStore(
        redis,
        JarvisExecutionAdmissionSettings(
            tenant_requests_per_window=2,
            actor_requests_per_window=2,
            window_seconds=60,
            tenant_concurrency=1,
            actor_concurrency=1,
            maximum_lease_ttl_seconds=60,
        ),
        key_prefix=prefix,
    )

    try:
        first = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            request_timeout_seconds=10,
        )

        with pytest.raises(JarvisAdmissionConcurrencyLimited):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                request_timeout_seconds=10,
            )

        await store.release(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            lease=first,
        )

        second = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            request_timeout_seconds=10,
        )
        await store.release(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            lease=second,
        )

        with pytest.raises(JarvisAdmissionRateLimited):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                request_timeout_seconds=10,
            )

        stored_keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        assert stored_keys
        assert all(str(TENANT) not in key for key in stored_keys)
        assert all(ACTOR not in key for key in stored_keys)
    finally:
        keys = [key async for key in redis.scan_iter(match=f"{prefix}:*")]
        if keys:
            await redis.delete(*keys)
        await redis.aclose()
