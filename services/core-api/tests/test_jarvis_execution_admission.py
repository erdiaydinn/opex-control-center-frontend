from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.jarvis_execution_admission import (
    ADMISSION_LEASE_SAFETY_SECONDS,
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionInvalid,
    JarvisAdmissionRateLimited,
    JarvisAdmissionUnavailable,
    JarvisExecutionAdmissionSettings,
    RedisJarvisExecutionAdmissionStore,
    broker_lease_ttl_seconds,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "employee-subject-12345"


def settings(**overrides) -> JarvisExecutionAdmissionSettings:
    values = {
        "tenant_requests_per_window": 30,
        "actor_requests_per_window": 10,
        "window_seconds": 60,
        "tenant_concurrency": 4,
        "actor_concurrency": 2,
        "maximum_lease_ttl_seconds": 180,
    }
    values.update(overrides)
    return JarvisExecutionAdmissionSettings(**values)


def test_scope_keys_never_expose_raw_tenant_or_actor() -> None:
    store = RedisJarvisExecutionAdmissionStore(AsyncMock(), settings())

    keys = store._keys(tenant_id=TENANT, actor_subject=ACTOR)

    assert len(keys) == 4
    assert all("{ai}" in key for key in keys)
    assert all(str(TENANT) not in key for key in keys)
    assert all(ACTOR not in key for key in keys)
    assert all(len(key.rsplit(":", 2)[-2]) == 64 for key in keys)


def test_actor_budgets_cannot_exceed_tenant_budgets() -> None:
    with pytest.raises(ValidationError):
        settings(
            tenant_requests_per_window=5,
            actor_requests_per_window=6,
        )

    with pytest.raises(ValidationError):
        settings(
            tenant_concurrency=2,
            actor_concurrency=3,
        )


def test_broker_timeout_is_bound_to_lease_ttl_and_hard_cap() -> None:
    assert broker_lease_ttl_seconds(
        30.1,
        maximum_lease_ttl_seconds=180,
    ) == 31 + ADMISSION_LEASE_SAFETY_SECONDS

    with pytest.raises(JarvisAdmissionInvalid):
        broker_lease_ttl_seconds(
            170,
            maximum_lease_ttl_seconds=180,
        )


@pytest.mark.asyncio
async def test_admit_uses_one_atomic_script_with_only_hashed_scope_keys() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, "admitted"]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())

    lease = await store.acquire(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        request_timeout_seconds=30,
    )

    redis.eval.assert_awaited_once()
    args = redis.eval.await_args.args
    assert args[1] == 4
    redis_keys = args[2:6]
    assert all(str(TENANT) not in key for key in redis_keys)
    assert all(ACTOR not in key for key in redis_keys)
    assert lease.lease_ttl_seconds == 45
    assert str(lease.token) == "**********"


@pytest.mark.parametrize(
    ("decision", "error"),
    [
        ([0, "tenant_rate"], JarvisAdmissionRateLimited),
        ([0, "actor_rate"], JarvisAdmissionRateLimited),
        ([0, "tenant_concurrency"], JarvisAdmissionConcurrencyLimited),
        ([0, "actor_concurrency"], JarvisAdmissionConcurrencyLimited),
    ],
)
@pytest.mark.asyncio
async def test_admission_denials_are_typed_and_fail_before_execution(
    decision,
    error,
) -> None:
    redis = AsyncMock()
    redis.eval.return_value = decision
    store = RedisJarvisExecutionAdmissionStore(redis, settings())

    with pytest.raises(error):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            request_timeout_seconds=30,
        )


@pytest.mark.parametrize(
    "response",
    [
        None,
        [],
        [1],
        [1, "unexpected"],
        [0, "unknown"],
        [2, "admitted"],
    ],
)
@pytest.mark.asyncio
async def test_malformed_redis_decision_fails_closed(response) -> None:
    redis = AsyncMock()
    redis.eval.return_value = response
    store = RedisJarvisExecutionAdmissionStore(redis, settings())

    with pytest.raises(JarvisAdmissionUnavailable):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_redis_outage_fails_closed() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = RedisConnectionError("simulated outage")
    store = RedisJarvisExecutionAdmissionStore(redis, settings())

    with pytest.raises(JarvisAdmissionUnavailable):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_release_uses_only_concurrency_keys_and_random_lease_token() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, "admitted"], 2)
    store = RedisJarvisExecutionAdmissionStore(redis, settings())

    lease = await store.acquire(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        request_timeout_seconds=30,
    )
    await store.release(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        lease=lease,
    )

    release_args = redis.eval.await_args_list[1].args
    assert release_args[1] == 2
    assert all(str(TENANT) not in key for key in release_args[2:4])
    assert all(ACTOR not in key for key in release_args[2:4])
    assert release_args[4] == lease.token.get_secret_value()
