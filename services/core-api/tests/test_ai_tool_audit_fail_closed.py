from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.ai_tool_routes as routes
from app.core.ai_data_scope import AiDataScope, ai_data_scope_fingerprint
from app.core.ai_tenant_query_context import (
    AiTenantQueryContext,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)
from app.core.ai_tool_authorization import AiToolCapability
from app.core.ai_tool_grants import RedisAiToolGrantStore
from app.core.jarvis_service_identity import VerifiedJarvisService

TENANT = UUID("11111111-1111-4111-8111-111111111111")


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


def tenant_context() -> AiTenantQueryContextRecord:
    context = AiTenantQueryContext(
        version=1,
        entity_ids=("TEST_ENTITY_TR",),
        source_reference="data-catalog:audit-fail-closed",
    )
    return AiTenantQueryContextRecord(
        tenant_id=str(TENANT),
        context=context,
        record_fingerprint=ai_tenant_query_context_fingerprint(context),
        updated_by="security-admin",
    )


async def load_tenant_context(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    assert tenant_id == str(TENANT)
    return tenant_context()


def capability() -> AiToolCapability:
    data_scope = AiDataScope(
        version=1,
        store_names=("Fulya",),
    )
    return AiToolCapability(
        tenant_id=TENANT,
        actor_subject="user-1",
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=("action:ai_assistant:executeOpsRead",),
        authorizing_roles=("super_admin",),
        data_scope=data_scope,
        data_scope_fingerprint=ai_data_scope_fingerprint(data_scope),
        authorization_fingerprint="a" * 64,
    )


def request_for(path: str) -> Request:
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        }
    )
    request.state.request_id = "request-audit-failure"
    return request


def jarvis_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-audit-failure-0001",
    )


@pytest.mark.asyncio
async def test_audit_failure_burns_consumed_tool_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    store = RedisAiToolGrantStore(
        redis,  # type: ignore[arg-type]
        tenant_query_context_loader=load_tenant_context,
    )
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    arguments = {
        "metric": "orders",
        "stores": ["Fulya"],
    }
    reason = "read current orders"
    issued = await store.issue(
        capability(),
        arguments=arguments,
        reason=reason,
    )
    token = issued.token.get_secret_value()

    async def fail_audit(_: dict[str, object]) -> None:
        raise RuntimeError("audit database unavailable")

    monkeypatch.setattr(routes, "write_audit_event", fail_audit)

    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=token,
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )

    with pytest.raises(HTTPException) as first_error:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )

    assert first_error.value.status_code == 503
    assert first_error.value.detail == (
        "AI tool execution audit is unavailable"
    )
    assert redis.values == {}

    with pytest.raises(HTTPException) as replay_error:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )

    assert replay_error.value.status_code == 401
    assert replay_error.value.detail == (
        "AI tool grant authentication failed"
    )
