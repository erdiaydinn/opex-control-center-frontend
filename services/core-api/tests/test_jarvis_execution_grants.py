from __future__ import annotations

import inspect
from uuid import UUID

import pytest

from app.core.ai_tool_authorization import AiToolCapability
from app.core.ai_tool_grants import (
    AiToolGrantBindingMismatch,
    AiToolGrantReplayOrExpired,
    RedisAiToolGrantStore,
)

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}

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
        if key in self.values:
            return None
        self.values[key] = value
        return True

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


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


def test_internal_consume_accepts_no_caller_identity_or_scopes() -> None:
    signature = inspect.signature(
        RedisAiToolGrantStore.consume_authorized_invocation
    )
    for forbidden in (
        "capability",
        "tenant_id",
        "actor_subject",
        "permissions",
        "granted_scopes",
    ):
        assert forbidden not in signature.parameters


@pytest.mark.asyncio
async def test_internal_consume_recovers_trusted_actor_and_tenant() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    cap = capability(
        tenant_id=TENANT_B,
        actor_subject="trusted-user",
        fingerprint="b" * 64,
    )
    arguments = {"metric": "orders"}
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


@pytest.mark.asyncio
async def test_internal_mismatch_burns_grant() -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(redis)  # type: ignore[arg-type]
    original = {"metric": "orders"}
    issued = await store.issue(
        capability(),
        arguments=original,
        reason="read orders",
    )
    token = issued.token.get_secret_value()

    with pytest.raises(AiToolGrantBindingMismatch):
        await store.consume_authorized_invocation(
            token=token,
            tool="ops_kpi_query",
            arguments={"metric": "refunds"},
            reason="read orders",
        )

    with pytest.raises(AiToolGrantReplayOrExpired):
        await store.consume_authorized_invocation(
            token=token,
            tool="ops_kpi_query",
            arguments=original,
            reason="read orders",
        )
