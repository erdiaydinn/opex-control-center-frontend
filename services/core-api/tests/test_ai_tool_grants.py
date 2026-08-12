from __future__ import annotations

from uuid import UUID

import pytest
from redis.exceptions import RedisError

from app.core.ai_tool_authorization import AiToolCapability
from app.core.ai_tool_grants import (
    AI_TOOL_GRANT_MAX_TTL_SECONDS,
    AiToolGrantBindingMismatch,
    AiToolGrantInvalid,
    AiToolGrantReplayOrExpired,
    AiToolGrantUnavailable,
    RedisAiToolGrantStore,
    canonical_arguments_sha256,
)


TENANT_A = UUID(
    "11111111-1111-4111-8111-111111111111"
)
TENANT_B = UUID(
    "22222222-2222-4222-8222-222222222222"
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.last_key = ""

    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool | None:
        assert ex > 0
        assert nx is True
        self.last_key = key

        if key in self.values:
            return None

        self.values[key] = value
        return True

    async def getdel(
        self,
        key: str,
    ) -> str | None:
        self.last_key = key
        return self.values.pop(key, None)


class UnavailableRedis(FakeRedis):
    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int,
        nx: bool,
    ) -> bool | None:
        raise RedisError("redis unavailable")

    async def getdel(
        self,
        key: str,
    ) -> str | None:
        raise RedisError("redis unavailable")


def capability(
    *,
    tenant_id: UUID = TENANT_A,
    actor_subject: str = "user-1",
    fingerprint: str = "a" * 64,
) -> AiToolCapability:
    return AiToolCapability(
        tenant_id=tenant_id,
        actor_subject=actor_subject,
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=(
            "action:ai_assistant:executeOpsRead",
        ),
        authorizing_roles=("super_admin",),
        authorization_fingerprint=fingerprint,
    )


def test_arguments_hash_is_stable_for_key_order() -> None:
    first = canonical_arguments_sha256(
        {
            "metric": "orders",
            "filters": {
                "warehouse": "A",
                "days": 7,
            },
        }
    )
    second = canonical_arguments_sha256(
        {
            "filters": {
                "days": 7,
                "warehouse": "A",
            },
            "metric": "orders",
        }
    )

    assert first == second
    assert len(first) == 64


def test_arguments_reject_ambiguous_or_nonfinite_json() -> None:
    with pytest.raises(AiToolGrantInvalid):
        canonical_arguments_sha256(
            {1: "ambiguous"}
        )

    with pytest.raises(AiToolGrantInvalid):
        canonical_arguments_sha256(
            {"value": float("nan")}
        )


def test_issue_stores_only_hashed_token_and_hashed_context() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]

    issued = pytest.run(
        store.issue(
            capability(),
            arguments={
                "metric": "secret-metric",
            },
            reason="need secret reason",
        )
    )

    token = issued.token.get_secret_value()

    assert token not in redis.last_key
    assert "secret-metric" not in next(iter(redis.values.values()))
    assert "secret reason" not in next(iter(redis.values.values()))
    assert token not in repr(issued)


def test_single_use_grant_consumes_exact_binding() -> None:
    async def scenario() -> None:
        redis = FakeRedis()
        store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
        cap = capability()
        arguments = {"metric": "orders"}
        reason = "authorized KPI lookup"

        issued = await store.issue(
            cap,
            arguments=arguments,
            reason=reason,
        )
        token = issued.token.get_secret_value()

        binding = await store.consume(
            token=token,
            capability=cap,
            arguments=arguments,
            reason=reason,
        )

        assert binding == issued.binding

        with pytest.raises(
            AiToolGrantReplayOrExpired
        ):
            await store.consume(
                token=token,
                capability=cap,
                arguments=arguments,
                reason=reason,
            )

    import asyncio

    asyncio.run(scenario())


def test_binding_mismatch_burns_grant() -> None:
    async def scenario() -> None:
        redis = FakeRedis()
        store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
        cap = capability()
        original = {"metric": "orders"}

        issued = await store.issue(
            cap,
            arguments=original,
            reason="read orders",
        )
        token = issued.token.get_secret_value()

        with pytest.raises(
            AiToolGrantBindingMismatch
        ):
            await store.consume(
                token=token,
                capability=cap,
                arguments={"metric": "refunds"},
                reason="read orders",
            )

        with pytest.raises(
            AiToolGrantReplayOrExpired
        ):
            await store.consume(
                token=token,
                capability=cap,
                arguments=original,
                reason="read orders",
            )

    import asyncio

    asyncio.run(scenario())


def test_grant_is_bound_to_actor_tenant_and_authorization_snapshot() -> None:
    async def mismatch(
        changed: AiToolCapability,
    ) -> None:
        redis = FakeRedis()
        store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
        original = capability()

        issued = await store.issue(
            original,
            arguments={"metric": "orders"},
            reason="read KPI",
        )

        with pytest.raises(
            AiToolGrantBindingMismatch
        ):
            await store.consume(
                token=issued.token.get_secret_value(),
                capability=changed,
                arguments={"metric": "orders"},
                reason="read KPI",
            )

    import asyncio

    asyncio.run(
        mismatch(
            capability(actor_subject="user-2")
        )
    )
    asyncio.run(
        mismatch(
            capability(tenant_id=TENANT_B)
        )
    )
    asyncio.run(
        mismatch(
            capability(fingerprint="b" * 64)
        )
    )


def test_reason_is_part_of_single_use_binding() -> None:
    async def scenario() -> None:
        redis = FakeRedis()
        store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
        cap = capability()

        issued = await store.issue(
            cap,
            arguments={"metric": "orders"},
            reason="reason A",
        )

        with pytest.raises(
            AiToolGrantBindingMismatch
        ):
            await store.consume(
                token=issued.token.get_secret_value(),
                capability=cap,
                arguments={"metric": "orders"},
                reason="reason B",
            )

    import asyncio

    asyncio.run(scenario())


def test_ttl_is_strictly_bounded() -> None:
    async def scenario() -> None:
        store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]

        for invalid in (
            True,
            0,
            -1,
            AI_TOOL_GRANT_MAX_TTL_SECONDS + 1,
        ):
            with pytest.raises(ValueError):
                await store.issue(
                    capability(),
                    arguments={"metric": "orders"},
                    reason="read KPI",
                    ttl_seconds=invalid,  # type: ignore[arg-type]
                )

    import asyncio

    asyncio.run(scenario())


def test_redis_failure_is_fail_closed_for_issue_and_consume() -> None:
    async def scenario() -> None:
        store = RedisAiToolGrantStore(
            UnavailableRedis()
        )  # type: ignore[arg-type]
        cap = capability()

        with pytest.raises(AiToolGrantUnavailable):
            await store.issue(
                cap,
                arguments={"metric": "orders"},
                reason="read KPI",
            )

        with pytest.raises(AiToolGrantUnavailable):
            await store.consume(
                token="x" * 43,
                capability=cap,
                arguments={"metric": "orders"},
                reason="read KPI",
            )

    import asyncio

    asyncio.run(scenario())
