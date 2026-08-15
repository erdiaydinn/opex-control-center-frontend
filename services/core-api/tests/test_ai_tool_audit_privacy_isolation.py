from __future__ import annotations

from uuid import UUID

import pytest
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

TENANT = UUID("22222222-2222-4222-8222-222222222222")
ACTOR = "audit-user-tenant-a"
STORE = "Fulya Secret Store"
ENTITY = "TENANT_A_PRIVATE_ENTITY"
REASON = "investigate confidential orders anomaly"


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


async def load_tenant_context(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    assert tenant_id == str(TENANT)
    context = AiTenantQueryContext(
        version=1,
        entity_ids=(ENTITY,),
        source_reference="data-catalog:audit-privacy-isolation",
    )
    return AiTenantQueryContextRecord(
        tenant_id=str(TENANT),
        context=context,
        record_fingerprint=ai_tenant_query_context_fingerprint(context),
        updated_by="security-admin",
    )


def capability() -> AiToolCapability:
    data_scope = AiDataScope(
        version=1,
        store_names=(STORE,),
    )
    return AiToolCapability(
        tenant_id=TENANT,
        actor_subject=ACTOR,
        tool="ops_kpi_query",
        granted_scopes=("ops:read",),
        permission_keys=("action:ai_assistant:executeOpsRead",),
        authorizing_roles=("super_admin",),
        data_scope=data_scope,
        data_scope_fingerprint=ai_data_scope_fingerprint(data_scope),
        authorization_fingerprint="b" * 64,
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
    request.state.request_id = "request-audit-privacy"
    return request


def jarvis_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-audit-privacy-0001",
    )


@pytest.mark.asyncio
async def test_authorization_audit_is_tenant_bound_and_payload_private(
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
        "stores": [STORE],
        "customer_note": "private payload marker",
    }
    issued = await store.issue(
        capability(),
        arguments=arguments,
        reason=REASON,
    )

    captured: list[dict[str, object]] = []

    async def capture_audit(event: dict[str, object]) -> None:
        captured.append(event)

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)

    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=issued.token.get_secret_value(),
        tool="ops_kpi_query",
        arguments=arguments,
        reason=REASON,
    )

    result = await routes.authorize_internal_ai_tool_execution(
        payload,
        request_for("/internal/ai/tool-executions/authorize"),
        jarvis_service(),
    )

    assert result.tenant_id == str(TENANT)
    assert result.actor_subject == ACTOR
    assert len(captured) == 1

    event = captured[0]
    assert event["tenant_id"] == str(TENANT)
    assert event["actor"] == ACTOR
    assert event["action"] == "ai_tool_execution_authorized"

    metadata = event["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["data_scope_store_count"] == 1
    assert metadata["tenant_entity_count"] == 1
    assert metadata["arguments_sha256"]
    assert metadata["reason_sha256"]

    serialized = repr(event)
    for secret in (
        STORE,
        ENTITY,
        REASON,
        "private payload marker",
    ):
        assert secret not in serialized
