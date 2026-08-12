from __future__ import annotations

import inspect
import json
from uuid import UUID

import pytest
from redis.exceptions import RedisError

from app.core.ai_data_scope import (
    AiDataScope,
    ai_data_scope_fingerprint,
)
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
    store_names: tuple[str, ...] = ("Fulya",),
) -> AiToolCapability:
    data_scope = AiDataScope(
        version=1,
        store_names=store_names,
    )
    return AiToolCapability(
        tenant_id=tenant_id,
        actor_subject=actor_subject,
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=(
            "action:ai_assistant:executeOpsRead",
        ),
        authorizing_roles=("super_admin",),
        data_scope=data_scope,
        data_scope_fingerprint=(
            ai_data_scope_fingerprint(data_scope)
        ),
        authorization_fingerprint=fingerprint,
    )


def ops_arguments(
    *,
    metric: str = "orders",
    stores: tuple[str, ...] = ("Fulya",),
) -> dict[str, object]:
    return {
        "metric": metric,
        "stores": list(stores),
    }


def test_arguments_hash_is_stable_for_key_order() -> None:
    first = canonical_arguments_sha256(
        {
            "metric": "orders",
            "stores": ["Fulya"],
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
            "stores": ["Fulya"],
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


def test_internal_consume_contract_accepts_no_caller_authorization_data() -> None:
    signature = inspect.signature(
        RedisAiToolGrantStore.consume_authorized_invocation
    )

    assert "capability" not in signature.parameters
    assert "tenant_id" not in signature.parameters
    assert "actor_subject" not in signature.parameters
    assert "granted_scopes" not in signature.parameters
    assert "data_scope" not in signature.parameters
    assert "store_names" not in signature.parameters


@pytest.mark.asyncio
async def test_issue_stores_only_hashed_token_and_invocation_content() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]

    issued = await store.issue(
        capability(),
        arguments=ops_arguments(metric="secret-metric"),
        reason="need secret reason",
    )

    token = issued.token.get_secret_value()
    stored_payload = next(
        iter(redis.values.values())
    )

    assert token not in redis.last_key
    assert "secret-metric" not in stored_payload
    assert "secret reason" not in stored_payload
    assert token not in repr(issued)

    # The short-lived authoritative data scope must be recoverable by the
    # machine caller without trusting request-body authorization fields.
    assert "Fulya" in stored_payload


@pytest.mark.asyncio
async def test_issue_rejects_missing_or_out_of_scope_stores() -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    cap = capability(store_names=("Fulya", "Anka"))

    for arguments in (
        {"metric": "orders"},
        ops_arguments(stores=()),
        ops_arguments(stores=("Dicle",)),
        ops_arguments(stores=("fulya",)),
    ):
        with pytest.raises(AiToolGrantInvalid):
            await store.issue(
                cap,
                arguments=arguments,
                reason="read KPI",
            )


@pytest.mark.asyncio
async def test_single_use_grant_consumes_exact_binding() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability()
    arguments = ops_arguments()
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
    assert binding.version == 2
    assert binding.data_scope.store_names == ("Fulya",)

    with pytest.raises(
        AiToolGrantReplayOrExpired
    ):
        await store.consume(
            token=token,
            capability=cap,
            arguments=arguments,
            reason=reason,
        )


@pytest.mark.asyncio
async def test_internal_consume_recovers_trusted_actor_tenant_and_data_scope() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability(
        tenant_id=TENANT_B,
        actor_subject="trusted-user",
        fingerprint="b" * 64,
        store_names=("Anka", "Fulya"),
    )
    arguments = ops_arguments(stores=("Anka",))
    reason = "read KPI"

    issued = await store.issue(
        cap,
        arguments=arguments,
        reason=reason,
    )

    binding = await store.consume_authorized_invocation(
        token=issued.token.get_secret_value(),
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )

    assert binding.tenant_id == TENANT_B
    assert binding.actor_subject == "trusted-user"
    assert binding.authorization_fingerprint == "b" * 64
    assert binding.data_scope.store_names == (
        "Anka",
        "Fulya",
    )
    assert binding.data_scope_fingerprint == (
        cap.data_scope_fingerprint
    )


@pytest.mark.asyncio
async def test_redis_scope_tamper_is_detected_after_atomic_consume() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability(store_names=("Fulya",))
    arguments = ops_arguments()
    issued = await store.issue(
        cap,
        arguments=arguments,
        reason="read KPI",
    )

    key = next(iter(redis.values))
    payload = json.loads(redis.values[key])
    payload["data_scope"] = {
        "version": 1,
        "store_names": ["Dicle"],
    }
    redis.values[key] = json.dumps(payload)

    with pytest.raises(AiToolGrantInvalid):
        await store.consume_authorized_invocation(
            token=issued.token.get_secret_value(),
            tool="ops_kpi_query",
            arguments=arguments,
            reason="read KPI",
        )

    assert key not in redis.values


@pytest.mark.asyncio
async def test_binding_mismatch_burns_grant() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability()
    original = ops_arguments()

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
            arguments=ops_arguments(metric="refunds"),
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


@pytest.mark.asyncio
async def test_internal_mismatch_burns_grant() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability()
    original = ops_arguments()

    issued = await store.issue(
        cap,
        arguments=original,
        reason="read orders",
    )
    token = issued.token.get_secret_value()

    with pytest.raises(
        AiToolGrantBindingMismatch
    ):
        await store.consume_authorized_invocation(
            token=token,
            tool="ops_kpi_query",
            arguments=ops_arguments(metric="refunds"),
            reason="read orders",
        )

    with pytest.raises(
        AiToolGrantReplayOrExpired
    ):
        await store.consume_authorized_invocation(
            token=token,
            tool="ops_kpi_query",
            arguments=original,
            reason="read orders",
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        capability(actor_subject="user-2"),
        capability(tenant_id=TENANT_B),
        capability(fingerprint="b" * 64),
        capability(store_names=("Anka",)),
    ],
)
async def test_grant_is_bound_to_actor_tenant_authorization_and_data_scope(
    changed: AiToolCapability,
) -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    original = capability()

    issued = await store.issue(
        original,
        arguments=ops_arguments(),
        reason="read KPI",
    )

    with pytest.raises(
        (AiToolGrantBindingMismatch, AiToolGrantInvalid)
    ):
        await store.consume(
            token=issued.token.get_secret_value(),
            capability=changed,
            arguments=ops_arguments(),
            reason="read KPI",
        )


@pytest.mark.asyncio
async def test_reason_is_part_of_single_use_binding() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability()

    issued = await store.issue(
        cap,
        arguments=ops_arguments(),
        reason="reason A",
    )

    with pytest.raises(
        AiToolGrantBindingMismatch
    ):
        await store.consume(
            token=issued.token.get_secret_value(),
            capability=cap,
            arguments=ops_arguments(),
            reason="reason B",
        )


@pytest.mark.asyncio
async def test_ttl_is_strictly_bounded() -> None:
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
                arguments=ops_arguments(),
                reason="read KPI",
                ttl_seconds=invalid,  # type: ignore[arg-type]
            )


@pytest.mark.asyncio
async def test_redis_failure_is_fail_closed_for_issue_and_consume() -> None:
    store = RedisAiToolGrantStore(
        UnavailableRedis()
    )  # type: ignore[arg-type]
    cap = capability()

    with pytest.raises(AiToolGrantUnavailable):
        await store.issue(
            cap,
            arguments=ops_arguments(),
            reason="read KPI",
        )

    with pytest.raises(AiToolGrantUnavailable):
        await store.consume(
            token="x" * 43,
            capability=cap,
            arguments=ops_arguments(),
            reason="read KPI",
        )
