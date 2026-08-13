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
from app.core.ai_tenant_query_context import (
    AiTenantQueryContext,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)
from app.core.ai_tool_authorization import AiToolCapability
from app.core.ai_tool_grants import (
    AI_TOOL_GRANT_MAX_TTL_SECONDS,
    AiToolGrantBindingMismatch,
    AiToolGrantInvalid,
    AiToolGrantReplayOrExpired,
    AiToolGrantTenantContextUnavailable,
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


class ContextAuthority:
    def __init__(
        self,
        records: dict[str, AiTenantQueryContextRecord] | None = None,
    ) -> None:
        self.records = records or {}
        self.error: Exception | None = None
        self.calls: list[str] = []

    async def __call__(
        self,
        tenant_id: str,
    ) -> AiTenantQueryContextRecord | None:
        self.calls.append(tenant_id)
        if self.error is not None:
            raise self.error
        return self.records.get(tenant_id)


def query_context_record(
    *,
    tenant_id: UUID,
    entity_ids: tuple[str, ...],
    source_reference: str,
) -> AiTenantQueryContextRecord:
    context = AiTenantQueryContext(
        version=1,
        entity_ids=entity_ids,
        source_reference=source_reference,
    )
    return AiTenantQueryContextRecord(
        tenant_id=str(tenant_id),
        context=context,
        record_fingerprint=(
            ai_tenant_query_context_fingerprint(context)
        ),
        updated_by="security-admin",
    )


def default_authority() -> ContextAuthority:
    return ContextAuthority(
        {
            str(TENANT_A): query_context_record(
                tenant_id=TENANT_A,
                entity_ids=("TEST_ENTITY_A",),
                source_reference="data-catalog:test-a",
            ),
            str(TENANT_B): query_context_record(
                tenant_id=TENANT_B,
                entity_ids=("TEST_ENTITY_B",),
                source_reference="data-catalog:test-b",
            ),
        }
    )


def grant_store(
    redis: FakeRedis,
    *,
    authority: ContextAuthority | None = None,
) -> RedisAiToolGrantStore:
    return RedisAiToolGrantStore(
        redis,  # type: ignore[arg-type]
        tenant_query_context_loader=(
            authority or default_authority()
        ),
    )


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
        canonical_arguments_sha256({1: "ambiguous"})

    with pytest.raises(AiToolGrantInvalid):
        canonical_arguments_sha256(
            {"value": float("nan")}
        )


def test_internal_consume_accepts_no_caller_authority_context() -> None:
    signature = inspect.signature(
        RedisAiToolGrantStore.consume_authorized_invocation
    )

    for forbidden in (
        "capability",
        "tenant_id",
        "actor_subject",
        "granted_scopes",
        "data_scope",
        "store_names",
        "query_policy",
        "query_contract_fingerprint",
        "tenant_query_context",
        "tenant_query_context_fingerprint",
        "entity_ids",
    ):
        assert forbidden not in signature.parameters


@pytest.mark.asyncio
async def test_issue_stores_minimal_binding_without_raw_tenant_entities() -> None:
    redis = FakeRedis()
    authority = default_authority()
    store = grant_store(redis, authority=authority)

    issued = await store.issue(
        capability(),
        arguments=ops_arguments(metric="secret-metric"),
        reason="need secret reason",
    )

    token = issued.token.get_secret_value()
    stored_payload = next(iter(redis.values.values()))

    assert token not in redis.last_key
    assert "secret-metric" not in stored_payload
    assert "secret reason" not in stored_payload
    assert "TEST_ENTITY_A" not in stored_payload
    assert "data-catalog:test-a" not in stored_payload
    assert "Fulya" in stored_payload
    assert token not in repr(issued)
    assert issued.binding.version == 4
    assert len(
        issued.binding.tenant_query_context_fingerprint
    ) == 64


@pytest.mark.asyncio
async def test_issue_requires_authoritative_tenant_query_context() -> None:
    redis = FakeRedis()
    authority = ContextAuthority()
    store = grant_store(redis, authority=authority)

    with pytest.raises(AiToolGrantTenantContextUnavailable):
        await store.issue(
            capability(),
            arguments=ops_arguments(),
            reason="read KPI",
        )

    assert redis.values == {}

    authority.error = RuntimeError("database unavailable")
    with pytest.raises(AiToolGrantTenantContextUnavailable):
        await store.issue(
            capability(),
            arguments=ops_arguments(),
            reason="read KPI",
        )

    assert redis.values == {}


@pytest.mark.asyncio
async def test_issue_rejects_missing_or_out_of_scope_stores() -> None:
    store = grant_store(FakeRedis())
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
async def test_single_use_grant_consumes_exact_v4_binding() -> None:
    redis = FakeRedis()
    store = grant_store(redis)
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
    assert binding.version == 4
    assert binding.data_scope.store_names == ("Fulya",)
    assert binding.query_contract_id == "ops.kpi.orders.v1"
    assert binding.query_contract_revision == 1
    assert len(binding.query_contract_fingerprint) == 64
    assert len(binding.tenant_query_context_fingerprint) == 64
    assert len(binding.execution_scope_fingerprint) == 64

    with pytest.raises(AiToolGrantReplayOrExpired):
        await store.consume(
            token=token,
            capability=cap,
            arguments=arguments,
            reason=reason,
        )


@pytest.mark.asyncio
async def test_internal_consume_recovers_fresh_tenant_entities() -> None:
    redis = FakeRedis()
    authority = default_authority()
    store = grant_store(redis, authority=authority)
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

    authorization = await store.consume_authorized_invocation(
        token=issued.token.get_secret_value(),
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )
    binding = authorization.binding

    assert binding.tenant_id == TENANT_B
    assert binding.actor_subject == "trusted-user"
    assert binding.authorization_fingerprint == "b" * 64
    assert binding.data_scope.store_names == (
        "Anka",
        "Fulya",
    )
    assert authorization.tenant_entity_ids == (
        "TEST_ENTITY_B",
    )
    assert authority.calls == [str(TENANT_B), str(TENANT_B)]


@pytest.mark.asyncio
async def test_redis_scope_tamper_is_detected_after_atomic_consume() -> None:
    redis = FakeRedis()
    store = grant_store(redis)
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
async def test_query_and_tenant_context_tamper_burn_grant() -> None:
    for field, replacement in (
        ("query_contract_revision", 999),
        ("tenant_query_context_fingerprint", "f" * 64),
    ):
        redis = FakeRedis()
        store = grant_store(redis)
        cap = capability()
        arguments = ops_arguments()
        issued = await store.issue(
            cap,
            arguments=arguments,
            reason="read KPI",
        )

        key = next(iter(redis.values))
        payload = json.loads(redis.values[key])
        payload[field] = replacement
        redis.values[key] = json.dumps(payload)

        with pytest.raises(AiToolGrantBindingMismatch):
            await store.consume_authorized_invocation(
                token=issued.token.get_secret_value(),
                tool="ops_kpi_query",
                arguments=arguments,
                reason="read KPI",
            )

        assert key not in redis.values


@pytest.mark.asyncio
async def test_tenant_context_change_or_outage_burns_outstanding_grant() -> None:
    for mode in ("change", "outage"):
        redis = FakeRedis()
        authority = default_authority()
        store = grant_store(redis, authority=authority)
        issued = await store.issue(
            capability(),
            arguments=ops_arguments(),
            reason="read KPI",
        )
        token = issued.token.get_secret_value()

        if mode == "change":
            authority.records[str(TENANT_A)] = query_context_record(
                tenant_id=TENANT_A,
                entity_ids=("TEST_ENTITY_A_NEXT",),
                source_reference="data-catalog:test-a-next",
            )
            expected_error = AiToolGrantBindingMismatch
        else:
            authority.error = RuntimeError("database unavailable")
            expected_error = AiToolGrantTenantContextUnavailable

        with pytest.raises(expected_error):
            await store.consume_authorized_invocation(
                token=token,
                tool="ops_kpi_query",
                arguments=ops_arguments(),
                reason="read KPI",
            )

        authority.error = None
        with pytest.raises(AiToolGrantReplayOrExpired):
            await store.consume_authorized_invocation(
                token=token,
                tool="ops_kpi_query",
                arguments=ops_arguments(),
                reason="read KPI",
            )


@pytest.mark.asyncio
async def test_source_reference_changes_binding_but_is_never_disclosed() -> None:
    redis = FakeRedis()
    authority = default_authority()
    store = grant_store(redis, authority=authority)
    issued = await store.issue(
        capability(),
        arguments=ops_arguments(),
        reason="read KPI",
    )
    original_fingerprint = (
        issued.binding.tenant_query_context_fingerprint
    )
    stored_payload = next(iter(redis.values.values()))
    assert "data-catalog:test-a" not in stored_payload

    authority.records[str(TENANT_A)] = query_context_record(
        tenant_id=TENANT_A,
        entity_ids=("TEST_ENTITY_A",),
        source_reference="data-catalog:test-a-reviewed-again",
    )
    assert (
        authority.records[str(TENANT_A)].record_fingerprint
        != original_fingerprint
    )

    with pytest.raises(AiToolGrantBindingMismatch):
        await store.consume_authorized_invocation(
            token=issued.token.get_secret_value(),
            tool="ops_kpi_query",
            arguments=ops_arguments(),
            reason="read KPI",
        )


@pytest.mark.asyncio
async def test_old_v3_binding_is_rejected_after_atomic_consume() -> None:
    redis = FakeRedis()
    store = grant_store(redis)
    issued = await store.issue(
        capability(),
        arguments=ops_arguments(),
        reason="read KPI",
    )
    key = next(iter(redis.values))
    payload = json.loads(redis.values[key])
    payload["version"] = 3
    redis.values[key] = json.dumps(payload)

    with pytest.raises(AiToolGrantInvalid):
        await store.consume_authorized_invocation(
            token=issued.token.get_secret_value(),
            tool="ops_kpi_query",
            arguments=ops_arguments(),
            reason="read KPI",
        )

    assert key not in redis.values


@pytest.mark.asyncio
async def test_binding_mismatch_burns_grant() -> None:
    redis = FakeRedis()
    store = grant_store(redis)
    cap = capability()
    original = ops_arguments()

    issued = await store.issue(
        cap,
        arguments=original,
        reason="read orders",
    )
    token = issued.token.get_secret_value()

    with pytest.raises(AiToolGrantBindingMismatch):
        await store.consume(
            token=token,
            capability=cap,
            arguments=ops_arguments(metric="refunds"),
            reason="read orders",
        )

    with pytest.raises(AiToolGrantReplayOrExpired):
        await store.consume(
            token=token,
            capability=cap,
            arguments=original,
            reason="read orders",
        )


@pytest.mark.asyncio
async def test_internal_mismatch_burns_grant() -> None:
    redis = FakeRedis()
    store = grant_store(redis)
    cap = capability()
    original = ops_arguments()

    issued = await store.issue(
        cap,
        arguments=original,
        reason="read orders",
    )
    token = issued.token.get_secret_value()

    with pytest.raises(AiToolGrantBindingMismatch):
        await store.consume_authorized_invocation(
            token=token,
            tool="ops_kpi_query",
            arguments=ops_arguments(metric="refunds"),
            reason="read orders",
        )

    with pytest.raises(AiToolGrantReplayOrExpired):
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
    store = grant_store(redis)
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
    store = grant_store(redis)
    cap = capability()

    issued = await store.issue(
        cap,
        arguments=ops_arguments(),
        reason="reason A",
    )

    with pytest.raises(AiToolGrantBindingMismatch):
        await store.consume(
            token=issued.token.get_secret_value(),
            capability=cap,
            arguments=ops_arguments(),
            reason="reason B",
        )


@pytest.mark.asyncio
async def test_ttl_is_strictly_bounded() -> None:
    store = grant_store(FakeRedis())

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
        UnavailableRedis(),  # type: ignore[arg-type]
        tenant_query_context_loader=default_authority(),
    )
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
