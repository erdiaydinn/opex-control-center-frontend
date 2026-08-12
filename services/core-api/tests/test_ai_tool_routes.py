from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from starlette.requests import Request

import app.ai_tool_routes as routes
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
    for model, payload in (
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
            routes.InternalAiToolAuthorizationRequest,
            {
                "grant_token": "g" * 43,
                "tool": "ops_kpi_query",
                "arguments": ops_arguments(),
                "reason": "read orders",
                "tenant_id": str(TENANT),
            },
        ),
    ):
        with pytest.raises(ValidationError):
            model.model_validate(payload)


@pytest.mark.asyncio
async def test_user_grant_issue_derives_capability_server_side(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
    )

    payload = routes.AiToolGrantIssueRequest(
        tool="ops_kpi_query",
        arguments=ops_arguments("Fulya"),
        reason="read current orders",
    )

    response = await routes.issue_ai_tool_grant(
        payload,
        request_for("/v1/ai/tool-grants"),
        principal_with_ops_permission(),
    )

    assert response.tool == "ops_kpi_query"
    assert len(response.grant_token) >= 32
    assert response.expires_in_seconds <= 60
    assert len(response.data_scope_fingerprint) == 64
    assert response.query_contract_id == "ops.kpi.orders.v1"
    assert response.query_contract_revision == 1
    assert len(response.query_contract_fingerprint) == 64
    assert len(response.execution_scope_fingerprint) == 64


@pytest.mark.asyncio
async def test_user_without_permission_cannot_issue_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
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
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
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
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        store,
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
async def test_internal_authorization_recovers_identity_scope_and_writes_minimal_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
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
    assert metadata["data_scope_fingerprint"] == (
        capability.data_scope_fingerprint
    )
    assert metadata["query_contract_id"] == "ops.kpi.orders.v1"
    assert metadata["query_contract_revision"] == 1
    assert len(metadata["query_contract_fingerprint"]) == 64
    assert len(metadata["execution_scope_fingerprint"]) == 64

    # Query contract identifiers are approved metadata and may contain words
    # also used by tool arguments. Verify raw invocation content by field and
    # value, not by substring-matching the whole metadata representation.
    assert "arguments" not in metadata
    assert "reason" not in metadata
    assert "stores" not in metadata
    assert "metric" not in repr(metadata)
    assert reason not in repr(metadata)
    assert "Fulya" not in repr(metadata)
    assert "Anka" not in repr(metadata)


@pytest.mark.asyncio
async def test_audit_failure_denies_execution_after_burning_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
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
