from __future__ import annotations

from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.ai_tool_routes as routes
from app.core.ai_tenant_query_context import (
    AiTenantQueryContext,
    AiTenantQueryContextRecord,
    ai_tenant_query_context_fingerprint,
)
from app.core.ai_tool_authorization import (
    SCOPE_PERMISSION_KEYS,
    derive_ai_tool_capability,
)
from app.core.ai_tool_grants import RedisAiToolGrantStore
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.security import PermissionAssignment, Principal

TENANT = UUID("11111111-1111-4111-8111-111111111111")
OPS_PERMISSION = SCOPE_PERMISSION_KEYS["ops:read"]


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.set_calls = 0

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
        self.set_calls += 1
        if key in self.values:
            return None
        self.values[key] = value
        return True

    async def getdel(self, key: str) -> str | None:
        return self.values.pop(key, None)


async def load_query_context(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    assert tenant_id == str(TENANT)
    context = AiTenantQueryContext(
        version=1,
        entity_ids=("TEST_ENTITY_TR",),
        source_reference="data-catalog:query-contract-test",
    )
    return AiTenantQueryContextRecord(
        tenant_id=tenant_id,
        context=context,
        record_fingerprint=(
            ai_tenant_query_context_fingerprint(context)
        ),
        updated_by="security-admin",
    )


def grant_store(redis: FakeRedis) -> RedisAiToolGrantStore:
    return RedisAiToolGrantStore(
        redis,  # type: ignore[arg-type]
        tenant_query_context_loader=load_query_context,
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
    request.state.request_id = "request-query-contract-1"
    return request


def principal() -> Principal:
    return Principal(
        subject="user-1",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=(OPS_PERMISSION,),
        permission_assignments=(
            PermissionAssignment(
                key=OPS_PERMISSION,
                role_key="super_admin",
                scope={
                    "ai_data_scope": {
                        "version": 1,
                        "store_names": ["Fulya"],
                    }
                },
            ),
        ),
        auth_mode="oidc",
    )


def arguments() -> dict[str, object]:
    return {
        "metric": "orders",
        "stores": ["Fulya"],
    }


def jarvis_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-assertion-query-contract-1",
    )


@pytest.mark.asyncio
async def test_production_not_ready_contract_blocks_before_any_authority_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    store = grant_store(redis)
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.issue_ai_tool_grant(
            routes.AiToolGrantIssueRequest(
                tool="ops_kpi_query",
                arguments=arguments(),
                reason="read tenant KPI",
            ),
            request_for("/v1/ai/tool-grants"),
            principal(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "AI tool execution contract is not ready"
    )
    assert redis.set_calls == 0
    assert redis.values == {}


@pytest.mark.asyncio
async def test_readiness_withdrawal_burns_outstanding_v4_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    store = grant_store(redis)
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    capability = derive_ai_tool_capability(
        principal(),
        tool="ops_kpi_query",
    )
    issued = await store.issue(
        capability,
        arguments=arguments(),
        reason="read tenant KPI",
    )
    token = issued.token.get_secret_value()
    assert redis.values

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(environment="production"),
    )

    async def audit_must_not_run(event: dict[str, object]) -> None:
        del event
        pytest.fail("audit must not run after readiness withdrawal")

    monkeypatch.setattr(
        routes,
        "write_audit_event",
        audit_must_not_run,
    )

    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=token,
        tool="ops_kpi_query",
        arguments=arguments(),
        reason="read tenant KPI",
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "AI tool execution contract is not ready"
    )
    assert redis.values == {}

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(environment="test"),
    )

    with pytest.raises(HTTPException) as replay_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )

    assert replay_info.value.status_code == 401
    assert replay_info.value.detail == (
        "AI tool grant authentication failed"
    )
