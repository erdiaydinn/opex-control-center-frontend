from __future__ import annotations

import os
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.core.jarvis_execution_admission import (
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionRateLimited,
    JarvisExecutionAdmissionSettings,
    RedisJarvisExecutionAdmissionStore,
    broker_lease_ttl_seconds,
)
from app.core.jarvis_grant_idempotency import (
    JarvisGrantIdempotencyConflict,
    JarvisGrantIdempotencyReplay,
    RedisJarvisGrantIdempotencyStore,
    grant_issue_request_fingerprint,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "user:security-test"


def _integration_enabled() -> bool:
    return os.getenv("EAY_JARVIS_SECURITY_REDIS_INTEGRATION") == "1"


def _grant_fingerprint(*, tool: str = "ops_kpi_query") -> str:
    return grant_issue_request_fingerprint(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=tool,
        arguments_sha256="a" * 64,
        reason_sha256="b" * 64,
        authorization_fingerprint="c" * 64,
        data_scope_fingerprint="d" * 64,
    )


def test_grant_issue_fingerprint_binds_server_authority_and_invocation() -> None:
    base = _grant_fingerprint()
    changed_tool = _grant_fingerprint(tool="catalog_query")

    assert len(base) == 64
    assert base != changed_tool
    assert str(TENANT) not in base
    assert ACTOR not in base


def test_admission_lease_policy_is_bounded() -> None:
    assert broker_lease_ttl_seconds(
        120,
        maximum_lease_ttl_seconds=180,
    ) == 135

    with pytest.raises(Exception, match="lease capacity"):
        broker_lease_ttl_seconds(
            180,
            maximum_lease_ttl_seconds=180,
        )


def test_admission_policy_rejects_actor_budget_above_tenant() -> None:
    with pytest.raises(ValueError, match="actor request budget"):
        JarvisExecutionAdmissionSettings(
            tenant_requests_per_window=3,
            actor_requests_per_window=4,
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="real Redis Jarvis security acceptance is opt-in",
)
async def test_real_redis_grant_idempotency_blocks_replay_conflict_and_raw_data() -> None:
    client = Redis.from_url(
        os.environ["OPEX_REDIS_URL"],
        decode_responses=True,
    )
    prefix = f"opex:{{ai}}:grant-test:{uuid4()}"
    store = RedisJarvisGrantIdempotencyStore(
        client,
        key_prefix=prefix,
        ttl_seconds=120,
    )
    try:
        await client.ping()
        reservation = await store.reserve(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            idempotency_key="request-key-0001",
            request_fingerprint=_grant_fingerprint(),
        )

        with pytest.raises(JarvisGrantIdempotencyReplay):
            await store.reserve(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                idempotency_key="request-key-0001",
                request_fingerprint=_grant_fingerprint(),
            )

        with pytest.raises(JarvisGrantIdempotencyConflict):
            await store.reserve(
                tenant_id=TENANT,
                actor_subject=ACTOR,
                idempotency_key="request-key-0001",
                request_fingerprint="e" * 64,
            )

        keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
        assert len(keys) == 1
        stored = await client.get(keys[0])
        evidence = "|".join([*keys, str(stored)])
        assert str(TENANT) not in evidence
        assert ACTOR not in evidence
        assert "request-key-0001" not in evidence

        await store.release(reservation)
        assert await client.exists(keys[0]) == 0

        # A pre-grant failure may release its reservation and retry safely.
        second = await store.reserve(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            idempotency_key="request-key-0001",
            request_fingerprint=_grant_fingerprint(),
        )
        await store.release(second)
    finally:
        keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="real Redis Jarvis security acceptance is opt-in",
)
async def test_real_redis_admission_enforces_actor_and_tenant_concurrency() -> None:
    client = Redis.from_url(
        os.environ["OPEX_REDIS_URL"],
        decode_responses=True,
    )
    prefix = f"opex:{{ai}}:admission-concurrency-test:{uuid4()}"
    store = RedisJarvisExecutionAdmissionStore(
        client,
        JarvisExecutionAdmissionSettings(
            tenant_requests_per_window=20,
            actor_requests_per_window=10,
            window_seconds=60,
            tenant_concurrency=2,
            actor_concurrency=1,
            execution_timeout_seconds=10,
            maximum_lease_ttl_seconds=30,
        ),
        key_prefix=prefix,
    )
    try:
        await client.ping()
        first = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
        )

        with pytest.raises(JarvisAdmissionConcurrencyLimited):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject=ACTOR,
            )

        second = await store.acquire(
            tenant_id=TENANT,
            actor_subject="user:security-test-2",
        )
        with pytest.raises(JarvisAdmissionConcurrencyLimited):
            await store.acquire(
                tenant_id=TENANT,
                actor_subject="user:security-test-3",
            )

        keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
        evidence_parts = list(keys)
        for key in keys:
            key_type = await client.type(key)
            if key_type == "string":
                evidence_parts.append(str(await client.get(key)))
            elif key_type == "zset":
                evidence_parts.extend(await client.zrange(key, 0, -1))
        evidence = "|".join(evidence_parts)
        assert str(TENANT) not in evidence
        assert ACTOR not in evidence
        assert "user:security-test-2" not in evidence

        await store.release(first)
        replacement = await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
        )
        await store.release(replacement)
        await store.release(second)
    finally:
        keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not _integration_enabled(),
    reason="real Redis Jarvis security acceptance is opt-in",
)
async def test_real_redis_admission_counts_rate_even_after_early_release() -> None:
    client = Redis.from_url(
        os.environ["OPEX_REDIS_URL"],
        decode_responses=True,
    )
    prefix = f"opex:{{ai}}:admission-rate-test:{uuid4()}"
    store = RedisJarvisExecutionAdmissionStore(
        client,
        JarvisExecutionAdmissionSettings(
            tenant_requests_per_window=2,
            actor_requests_per_window=2,
            window_seconds=60,
            tenant_concurrency=2,
            actor_concurrency=1,
            execution_timeout_seconds=10,
            maximum_lease_ttl_seconds=30,
        ),
        key_prefix=prefix,
    )
    try:
        await client.ping()
        first = await store.acquire(tenant_id=TENANT, actor_subject=ACTOR)
        await store.release(first)
        second = await store.acquire(tenant_id=TENANT, actor_subject=ACTOR)
        await store.release(second)

        with pytest.raises(JarvisAdmissionRateLimited):
            await store.acquire(tenant_id=TENANT, actor_subject=ACTOR)
    finally:
        keys = [key async for key in client.scan_iter(match=f"{prefix}:*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()
