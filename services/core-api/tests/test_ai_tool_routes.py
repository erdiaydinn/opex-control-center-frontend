from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
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
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.security import PermissionAssignment, Principal, get_current_principal

TENANT = UUID(
    "11111111-1111-4111-8111-111111111111"
)
ENTITY_ID = "TEST_ENTITY_TR"


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

    async def getdel(
        self,
        key: str,
    ) -> str | None:
        return self.values.pop(key, None)


def query_context_record() -> AiTenantQueryContextRecord:
    context = AiTenantQueryContext(
        version=1,
        entity_ids=(ENTITY_ID,),
        source_reference="data-catalog:test-route",
    )
    return AiTenantQueryContextRecord(
        tenant_id=str(TENANT),
        context=context,
        record_fingerprint=(
            ai_tenant_query_context_fingerprint(context)
        ),
        updated_by="security-admin",
    )


async def load_query_context(
    tenant_id: str,
) -> AiTenantQueryContextRecord | None:
    assert tenant_id == str(TENANT)
    return query_context_record()


def grant_store(
    redis: FakeRedis | None = None,
) -> RedisAiToolGrantStore:
    return RedisAiToolGrantStore(
        redis or FakeRedis(),  # type: ignore[arg-type]
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
    request.state.request_id = "request-1"
    return request


def explicit_scope(*stores: str) -> dict[str, object]:
    return {
        "ai_data_scope": {
            "version": 1,
            "store_names": list(stores),
        }
    }


def ops_arguments(*stores: str) -> dict[str, object]:
    return {
        "metric": "orders",
        "stores": list(stores or ("Fulya",)),
    }


def principal_with_ops_permission() -> Principal:
    permission = SCOPE_PERMISSION_KEYS[
        "ops:read"
    ]

    return Principal(
        subject="user-1",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=(permission,),
        permission_assignments=(
            PermissionAssignment(
                key=permission,
                role_key="super_admin",
                scope=explicit_scope(
                    "Anka",
                    "Fulya",
                ),
            ),
        ),
        auth_mode="oidc",
    )


def jarvis_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-assertion-0001",
    )


def _iter_api_routes(route_items):
    """Flatten FastAPI 0.141+ included-router nodes for contract inspection."""

    for route in route_items:
        path = getattr(route, "path", None)
        if path is not None:
            yield route

        nested = getattr(route, "routes", None)
        if nested is not None:
            yield from _iter_api_routes(nested)


def test_route_dependencies_keep_user_and_machine_auth_separate() -> None:
    api_routes = tuple(
        _iter_api_routes(routes.router.routes)
    )

    issue_route = next(
        route
        for route in api_routes
        if route.path == "/v1/ai/tool-grants"
    )
    internal_route = next(
        route
        for route in api_routes
        if route.path
        == "/internal/ai/tool-executions/authorize"
    )

    issue_dependencies = {
        dependency.call
        for dependency in issue_route.dependant.dependencies
    }
    internal_dependencies = {
        dependency.call
        for dependency in internal_route.dependant.dependencies
    }

    assert get_current_principal in issue_dependencies
    assert require_fresh_jarvis_service not in issue_dependencies

    assert require_fresh_jarvis_service in internal_dependencies
    assert get_current_principal not in internal_dependencies


def test_request_models_reject_caller_authorization_smuggling() -> None:
    payloads = (
        (
            routes.AiToolGrantIssueRequest,
            {
                "tool": "ops_kpi_query",
                "arguments": ops_arguments(),
                "reason": "read orders",
                "data_scope": {"store_names": ["Other"]},
            },
        ),
        (
            routes.AiToolGrantIssueRequest,
            {
                "tool": "ops_kpi_query",
                "arguments": ops_arguments(),
                "reason": "read orders",
                "entity_ids": ["OTHER_ENTITY"],
            },
        ),
        (
            routes.InternalAiToolAuthorizationRequest,
            {
                "grant_token": "g" * 43,
                "tool": "ops_kpi_query",
                "arguments": ops_arguments(),
                "reason": "read orders",
                "tenant_id": str(TENANT),
            },
        ),
        (
            routes.InternalAiToolAuthorizationRequest,
            {
                "grant_token": "g" * 43,
                "tool": "ops_kpi_query",
                "arguments": ops_arguments(),
                "reason": "read orders",
                "tenant_query_context": {
                    "entity_ids": ["OTHER_ENTITY"]
                },
            },
        ),
    )

    for model, payload in payloads:
        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.asyncio
async def test_user_grant_issue_derives_all_authority_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = grant_store()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
    )

    response = await routes.issue_ai_tool_grant(
        routes.AiToolGrantIssueRequest(
            tool="ops_kpi_query",
            arguments=ops_arguments("Fulya"),
            reason="read current orders",
        ),
        request_for("/v1/ai/tool-grants"),
        principal_with_ops_permission(),
    )

    assert response.tool == "ops_kpi_query"
    assert len(response.grant_token) >= 32
    assert response.expires_in_seconds <= 60
    assert len(response.data_scope_fingerprint) == 64
    assert len(response.tenant_query_context_fingerprint) == 64
    assert response.query_contract_id == "ops.kpi.orders.v1"
    assert response.query_contract_revision == 1
    assert len(response.query_contract_fingerprint) == 64
    assert len(response.execution_scope_fingerprint) == 64


@pytest.mark.asyncio
async def test_missing_tenant_context_is_503_and_no_grant_is_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()

    async def missing_context(
        tenant_id: str,
    ) -> AiTenantQueryContextRecord | None:
        assert tenant_id == str(TENANT)
        return None

    store = RedisAiToolGrantStore(
        redis,  # type: ignore[arg-type]
        tenant_query_context_loader=missing_context,
    )
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    with pytest.raises(HTTPException) as exc_info:
        await routes.issue_ai_tool_grant(
            routes.AiToolGrantIssueRequest(
                tool="ops_kpi_query",
                arguments=ops_arguments(),
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-grants"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "AI tenant query context is unavailable"
    )
    assert redis.values == {}


@pytest.mark.asyncio
async def test_user_without_permission_cannot_issue_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        grant_store(),
    )

    principal = Principal(
        subject="user-1",
        tenant_id=TENANT,
        roles=("viewer",),
        permissions=(),
        permission_assignments=(),
        auth_mode="oidc",
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.issue_ai_tool_grant(
            routes.AiToolGrantIssueRequest(
                tool="ops_kpi_query",
                arguments=ops_arguments(),
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-grants"),
            principal,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "AI tool access denied"


@pytest.mark.asyncio
async def test_empty_data_scope_cannot_issue_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        grant_store(),
    )
    permission = SCOPE_PERMISSION_KEYS["ops:read"]
    principal = Principal(
        subject="user-1",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=(permission,),
        permission_assignments=(
            PermissionAssignment(
                key=permission,
                role_key="super_admin",
                scope={},
            ),
        ),
        auth_mode="oidc",
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.issue_ai_tool_grant(
            routes.AiToolGrantIssueRequest(
                tool="ops_kpi_query",
                arguments=ops_arguments(),
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-grants"),
            principal,
        )

    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "AI tool access denied"


@pytest.mark.asyncio
async def test_scope_exceeding_arguments_cannot_issue_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        grant_store(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.issue_ai_tool_grant(
            routes.AiToolGrantIssueRequest(
                tool="ops_kpi_query",
                arguments=ops_arguments("Dicle"),
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-grants"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "AI tool request is invalid"


@pytest.mark.asyncio
async def test_internal_authorization_recovers_fresh_scope_and_minimal_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = grant_store()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
    )

    principal = principal_with_ops_permission()
    capability = derive_ai_tool_capability(
        principal,
        tool="ops_kpi_query",
    )
    arguments = ops_arguments("Fulya")
    reason = "read current orders"

    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )

    audit_events: list[dict[str, object]] = []

    async def capture_audit(
        event: dict[str, object],
    ) -> None:
        audit_events.append(event)

    monkeypatch.setattr(
        routes,
        "write_audit_event",
        capture_audit,
    )

    response = await routes.authorize_internal_ai_tool_execution(
        routes.InternalAiToolAuthorizationRequest(
            grant_token=issued.token.get_secret_value(),
            tool="ops_kpi_query",
            arguments=arguments,
            reason=reason,
        ),
        request_for(
            "/internal/ai/tool-executions/authorize"
        ),
        jarvis_service(),
    )

    assert response.tenant_id == str(TENANT)
    assert response.actor_subject == "user-1"
    assert response.granted_scopes == ("ops:read",)
    assert response.tool == "ops_kpi_query"
    assert response.data_scope.store_names == (
        "Anka",
        "Fulya",
    )
    assert response.data_scope_fingerprint == (
        capability.data_scope_fingerprint
    )
    assert response.tenant_entity_ids == (ENTITY_ID,)
    assert response.tenant_query_context_fingerprint == (
        issued.binding.tenant_query_context_fingerprint
    )
    assert response.query_contract_id == "ops.kpi.orders.v1"
    assert response.query_contract_revision == 1
    assert len(response.query_contract_fingerprint) == 64
    assert len(response.execution_scope_fingerprint) == 64

    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["tenant_id"] == str(TENANT)
    assert event["actor"] == "user-1"
    assert event["action"] == "ai_tool_execution_authorized"

    metadata = event["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["service_subject"] == "eay-ai-core"
    assert metadata["tool"] == "ops_kpi_query"
    assert metadata["data_scope_store_count"] == 2
    assert metadata["tenant_entity_count"] == 1
    assert metadata["tenant_query_context_fingerprint"] == (
        issued.binding.tenant_query_context_fingerprint
    )
    assert metadata["query_contract_id"] == "ops.kpi.orders.v1"
    assert metadata["query_contract_revision"] == 1

    assert "arguments" not in metadata
    assert "reason" not in metadata
    assert "stores" not in metadata
    assert "entity_ids" not in metadata
    assert "metric" not in repr(metadata)
    assert reason not in repr(metadata)
    assert "Fulya" not in repr(metadata)
    assert "Anka" not in repr(metadata)
    assert ENTITY_ID not in repr(metadata)
    assert "data-catalog:test-route" not in repr(metadata)


@pytest.mark.asyncio
async def test_tenant_context_outage_after_issue_burns_grant_and_maps_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    available = True

    async def mutable_loader(
        tenant_id: str,
    ) -> AiTenantQueryContextRecord | None:
        assert tenant_id == str(TENANT)
        if not available:
            raise RuntimeError("database unavailable")
        return query_context_record()

    store = RedisAiToolGrantStore(
        redis,  # type: ignore[arg-type]
        tenant_query_context_loader=mutable_loader,
    )
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    capability = derive_ai_tool_capability(
        principal_with_ops_permission(),
        tool="ops_kpi_query",
    )
    arguments = ops_arguments("Fulya")
    reason = "read current orders"
    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )
    token = issued.token.get_secret_value()
    available = False

    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=token,
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )
    with pytest.raises(HTTPException) as exc_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for(
                "/internal/ai/tool-executions/authorize"
            ),
            jarvis_service(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "AI tenant query context is unavailable"
    )

    available = True
    with pytest.raises(HTTPException) as replay_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for(
                "/internal/ai/tool-executions/authorize"
            ),
            jarvis_service(),
        )
    assert replay_info.value.status_code == 401


@pytest.mark.asyncio
async def test_audit_failure_denies_execution_after_burning_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = grant_store()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
    )

    capability = derive_ai_tool_capability(
        principal_with_ops_permission(),
        tool="ops_kpi_query",
    )
    arguments = ops_arguments("Fulya")
    reason = "read current orders"

    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )
    token = issued.token.get_secret_value()

    async def fail_audit(
        event: dict[str, object],
    ) -> None:
        del event
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(
        routes,
        "write_audit_event",
        fail_audit,
    )

    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=token,
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for(
                "/internal/ai/tool-executions/authorize"
            ),
            jarvis_service(),
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == (
        "AI tool execution audit is unavailable"
    )

    async def accept_audit(
        event: dict[str, object],
    ) -> None:
        del event

    monkeypatch.setattr(
        routes,
        "write_audit_event",
        accept_audit,
    )

    with pytest.raises(HTTPException) as replay_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for(
                "/internal/ai/tool-executions/authorize"
            ),
            jarvis_service(),
        )

    assert replay_info.value.status_code == 401
    assert replay_info.value.detail == (
        "AI tool grant authentication failed"
    )
