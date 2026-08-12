from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from pydantic import ValidationError
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.jarvis_execution_admission import (
    ADMISSION_LEASE_SAFETY_SECONDS,
    ALLOWED_CONTROL_TRANSITIONS,
    JarvisAdmissionConcurrencyLimited,
    JarvisAdmissionInvalid,
    JarvisAdmissionRateLimited,
    JarvisAdmissionUnavailable,
    JarvisControlConflict,
    JarvisEmergencyHalt,
    JarvisExecutionAdmissionSettings,
    JarvisReadOnlyModeDenied,
    RedisJarvisExecutionAdmissionStore,
    broker_lease_ttl_seconds,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "employee-subject-12345"
TOOL = "ops_kpi_query"


def settings(**overrides) -> JarvisExecutionAdmissionSettings:
    values = {
        "tenant_requests_per_window": 30,
        "actor_requests_per_window": 10,
        "tool_requests_per_window": 20,
        "window_seconds": 60,
        "tenant_concurrency": 4,
        "actor_concurrency": 2,
        "tool_concurrency": 3,
        "maximum_lease_ttl_seconds": 180,
    }
    values.update(overrides)
    return JarvisExecutionAdmissionSettings(**values)


def test_scope_keys_never_expose_raw_tenant_actor_or_tool() -> None:
    store = RedisJarvisExecutionAdmissionStore(AsyncMock(), settings())
    keys = store._keys(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=TOOL,
    )
    assert len(keys) == 7
    assert all("{ai}" in key for key in keys)
    for sensitive in (str(TENANT), ACTOR, TOOL):
        assert all(sensitive not in key for key in keys)
    assert keys[0].endswith(":control:mode")


def test_budget_hierarchy_cannot_expand_child_blast_radius() -> None:
    for updates in (
        {"tenant_requests_per_window": 5, "actor_requests_per_window": 6},
        {"tenant_requests_per_window": 5, "tool_requests_per_window": 6},
        {"tenant_concurrency": 2, "actor_concurrency": 3},
        {"tenant_concurrency": 2, "tool_concurrency": 3},
    ):
        with pytest.raises(ValidationError):
            settings(**updates)


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


def test_control_transition_graph_requires_staged_recovery() -> None:
    expected = {
        "enabled": frozenset({"read_only", "halted"}),
        "read_only": frozenset({"enabled", "halted"}),
        "halted": frozenset({"read_only"}),
    }
    assert not set(ALLOWED_CONTROL_TRANSITIONS).symmetric_difference(expected)
    for mode, transitions in expected.items():
        assert not ALLOWED_CONTROL_TRANSITIONS[mode].symmetric_difference(transitions)
    assert ALLOWED_CONTROL_TRANSITIONS["halted"].isdisjoint({"enabled"})


@pytest.mark.asyncio
async def test_missing_control_state_fails_closed() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [0, "control_missing"]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    with pytest.raises(JarvisAdmissionUnavailable):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_emergency_halt_fails_before_capacity_allocation() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [0, "halted"]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    with pytest.raises(JarvisEmergencyHalt):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_read_only_mode_allows_reads_but_denies_writes() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, "read_only"], [0, "read_only"])
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    lease = await store.acquire(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=TOOL,
        side_effect_class="read",
        request_timeout_seconds=30,
    )
    assert lease.control_mode == "read_only"
    with pytest.raises(JarvisReadOnlyModeDenied):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="write",
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_admit_is_one_atomic_decision_with_hashed_scope_keys() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, "enabled"]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    lease = await store.acquire(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=TOOL,
        side_effect_class="read",
        request_timeout_seconds=30,
    )
    redis.eval.assert_awaited_once()
    args = redis.eval.await_args.args
    assert args[1] == 7
    redis_keys = args[2:9]
    for sensitive in (str(TENANT), ACTOR, TOOL):
        assert all(sensitive not in key for key in redis_keys)
    assert lease.lease_ttl_seconds == 45
    assert lease.control_mode == "enabled"
    assert str(lease.token) == "**********"


@pytest.mark.parametrize(
    ("decision", "error"),
    [
        ([0, "tenant_rate"], JarvisAdmissionRateLimited),
        ([0, "actor_rate"], JarvisAdmissionRateLimited),
        ([0, "tool_rate"], JarvisAdmissionRateLimited),
        ([0, "tenant_concurrency"], JarvisAdmissionConcurrencyLimited),
        ([0, "actor_concurrency"], JarvisAdmissionConcurrencyLimited),
        ([0, "tool_concurrency"], JarvisAdmissionConcurrencyLimited),
    ],
)
@pytest.mark.asyncio
async def test_capacity_denials_are_typed(decision, error) -> None:
    redis = AsyncMock()
    redis.eval.return_value = decision
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    with pytest.raises(error):
        await store.acquire(
            tenant_id=TENANT,
            actor_subject=ACTOR,
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )


@pytest.mark.parametrize(
    "response",
    [None, [], [1], [1, "unexpected"], [0, "unknown"], [2, "enabled"], [0, b"\xff"]],
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
            tool=TOOL,
            side_effect_class="read",
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
            tool=TOOL,
            side_effect_class="read",
            request_timeout_seconds=30,
        )


@pytest.mark.asyncio
async def test_release_uses_only_three_concurrency_keys_and_random_lease() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, "enabled"], 3)
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    lease = await store.acquire(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=TOOL,
        side_effect_class="read",
        request_timeout_seconds=30,
    )
    await store.release(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool=TOOL,
        lease=lease,
    )
    release_args = redis.eval.await_args_list[1].args
    assert release_args[1] == 3
    redis_keys = release_args[2:5]
    for sensitive in (str(TENANT), ACTOR, TOOL):
        assert all(sensitive not in key for key in redis_keys)
    assert release_args[5] == lease.token.get_secret_value()


@pytest.mark.asyncio
async def test_control_bootstrap_must_start_halted() -> None:
    redis = AsyncMock()
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    with pytest.raises(JarvisAdmissionInvalid):
        await store.initialize_control_mode("enabled")
    with pytest.raises(JarvisAdmissionInvalid):
        await store.initialize_control_mode("read_only")
    redis.eval.assert_not_awaited()


@pytest.mark.asyncio
async def test_control_initialization_is_create_only() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, "halted"], [0, "already_initialized"])
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    assert await store.initialize_control_mode("halted") == "halted"
    with pytest.raises(JarvisControlConflict):
        await store.initialize_control_mode("halted")


@pytest.mark.asyncio
async def test_control_change_requires_compare_and_set() -> None:
    redis = AsyncMock()
    redis.eval.side_effect = ([1, "read_only"], [0, "compare_failed"])
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    assert (
        await store.change_control_mode(
            expected_mode="halted",
            new_mode="read_only",
        )
        == "read_only"
    )
    with pytest.raises(JarvisControlConflict):
        await store.change_control_mode(
            expected_mode="halted",
            new_mode="enabled",
        )


@pytest.mark.asyncio
async def test_direct_halted_to_enabled_is_rejected_by_atomic_authority() -> None:
    redis = AsyncMock()
    redis.eval.return_value = [0, "transition_denied"]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    with pytest.raises(JarvisAdmissionInvalid, match="staged recovery"):
        await store.change_control_mode(
            expected_mode="halted",
            new_mode="enabled",
        )
    redis.eval.assert_awaited_once()


@pytest.mark.parametrize(
    ("source", "target"),
    [
        ("halted", "read_only"),
        ("read_only", "enabled"),
        ("read_only", "halted"),
        ("enabled", "read_only"),
        ("enabled", "halted"),
    ],
)
@pytest.mark.asyncio
async def test_allowed_control_transitions_are_cas_guarded(source, target) -> None:
    redis = AsyncMock()
    redis.eval.return_value = [1, target]
    store = RedisJarvisExecutionAdmissionStore(redis, settings())
    assert await store.change_control_mode(expected_mode=source, new_mode=target) == target
    args = redis.eval.await_args.args
    assert args[-2:] == (source, target)


@pytest.mark.asyncio
async def test_control_change_rejects_noop_and_invalid_modes() -> None:
    store = RedisJarvisExecutionAdmissionStore(AsyncMock(), settings())
    with pytest.raises(JarvisAdmissionInvalid):
        await store.change_control_mode(
            expected_mode="enabled",
            new_mode="enabled",
        )
    with pytest.raises(JarvisAdmissionInvalid):
        await store.initialize_control_mode("broken")  # type: ignore[arg-type]
