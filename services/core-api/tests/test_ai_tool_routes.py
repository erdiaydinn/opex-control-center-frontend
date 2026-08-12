from __future__ import annotations

from uuid import UUID

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.ai_tool_routes as routes
from app.core.ai_tool_authorization import (
    SCOPE_PERMISSION_KEYS,
    derive_ai_tool_capability,
)
from app.core.ai_tool_grants import RedisAiToolGrantStore
from app.core.jarvis_execution_broker import (
    BrokerToolExecutionResult,
    JarvisExecutionBrokerIndeterminate,
    JarvisExecutionBrokerUnavailable,
)
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.security import (
    PermissionAssignment,
    Principal,
    get_current_principal,
)

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


class FakeBroker:
    def __init__(
        self,
        *,
        enabled: bool = True,
        failure: Exception | None = None,
    ) -> None:
        self.enabled = enabled
        self.failure = failure
        self.calls: list[dict[str, object]] = []

    def require_enabled(self) -> None:
        if not self.enabled:
            raise JarvisExecutionBrokerUnavailable("disabled")

    async def execute(
        self,
        *,
        grant_token: str,
        tool: str,
        arguments: dict[str, object],
        reason: str,
    ) -> BrokerToolExecutionResult:
        self.calls.append(
            {
                "grant_token": grant_token,
                "tool": tool,
                "arguments": arguments,
                "reason": reason,
            }
        )
        if self.failure is not None:
            raise self.failure

        return BrokerToolExecutionResult.model_validate(
            {
                "tool": tool,
                "query_id": "ops.orders.v1",
                "required_scope": ["ops:read"],
                "execution": {
                    "execution_id": "execution-1",
                    "status": "executed",
                    "dry_run_bytes": 100,
                    "maximum_bytes_billed": 250 * 1024 * 1024,
                    "row_count": 1,
                    "rows": [{"orders": 5}],
                    "sql_sha256": "a" * 64,
                },
                "legal_grounding": None,
                "semantic_verification": None,
                "schema_verification": None,
                "runtime_activation": None,
                "activation_provenance_fingerprint": None,
                "result_contract_fingerprint": None,
                "model_authored_sql_allowed": False,
            }
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


def principal_with_ops_permission() -> Principal:
    permission = SCOPE_PERMISSION_KEYS["ops:read"]
    return Principal(
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


def jarvis_service() -> VerifiedJarvisService:
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id="jarvis-assertion-0001",
    )


def test_route_surface_keeps_bearer_grants_off_public_api() -> None:
    paths = {route.path for route in routes.router.routes}

    assert "/v1/ai/tool-executions" in paths
    assert "/v1/ai/tool-grants" not in paths
    assert "/internal/ai/tool-executions/authorize" in paths


def test_route_dependencies_keep_user_and_machine_auth_separate() -> None:
    execution_route = next(
        route
        for route in routes.router.routes
        if route.path == "/v1/ai/tool-executions"
    )
    internal_route = next(
        route
        for route in routes.router.routes
        if route.path == "/internal/ai/tool-executions/authorize"
    )

    execution_dependencies = {
        dependency.call
        for dependency in execution_route.dependant.dependencies
    }
    internal_dependencies = {
        dependency.call
        for dependency in internal_route.dependant.dependencies
    }

    assert get_current_principal in execution_dependencies
    assert require_fresh_jarvis_service not in execution_dependencies
    assert require_fresh_jarvis_service in internal_dependencies
    assert get_current_principal not in internal_dependencies


@pytest.mark.asyncio
async def test_broker_disabled_fails_before_audit_or_grant_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    broker = FakeBroker(enabled=False)
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)

    audit_calls = 0

    async def capture_audit(event: dict[str, object]) -> None:
        nonlocal audit_calls
        audit_calls += 1
        del event

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            routes.AiToolExecutionRequest(
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 503
    assert audit_calls == 0
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_user_without_permission_cannot_reach_audit_grant_or_broker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    broker = FakeBroker()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)

    audit_calls = 0

    async def capture_audit(event: dict[str, object]) -> None:
        nonlocal audit_calls
        audit_calls += 1
        del event

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)
    principal = Principal(
        subject="user-1",
        tenant_id=TENANT,
        roles=("viewer",),
        permissions=(),
        permission_assignments=(),
        auth_mode="oidc",
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            routes.AiToolExecutionRequest(
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-executions"),
            principal,
        )

    assert exc_info.value.status_code == 403
    assert audit_calls == 0
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_request_audit_failure_prevents_grant_issue_and_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    broker = FakeBroker()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)

    async def fail_audit(event: dict[str, object]) -> None:
        del event
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(routes, "write_audit_event", fail_audit)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            routes.AiToolExecutionRequest(
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 503
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_happy_path_keeps_grant_server_side_and_audits_hashes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    broker = FakeBroker()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)

    audit_events: list[dict[str, object]] = []

    async def capture_audit(event: dict[str, object]) -> None:
        audit_events.append(event)

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)
    reason = "read current orders"

    response = await routes.execute_ai_tool(
        routes.AiToolExecutionRequest(
            tool="ops_kpi_query",
            arguments={"metric": "orders"},
            reason=reason,
        ),
        request_for("/v1/ai/tool-executions"),
        principal_with_ops_permission(),
    )

    assert response.tool == "ops_kpi_query"
    assert response.execution.status == "executed"
    assert "grant_token" not in response.model_dump(mode="json")

    assert len(broker.calls) == 1
    call = broker.calls[0]
    token = call["grant_token"]
    assert isinstance(token, str)
    assert len(token) >= 32
    assert call["arguments"] == {"metric": "orders"}
    assert call["reason"] == reason

    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["tenant_id"] == str(TENANT)
    assert event["actor"] == "user-1"
    assert event["action"] == "ai_tool_execution_requested"
    metadata = event["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["tool"] == "ops_kpi_query"
    assert len(str(metadata["arguments_sha256"])) == 64
    assert len(str(metadata["reason_sha256"])) == 64
    assert "orders" not in repr(metadata)
    assert reason not in repr(metadata)
    assert token not in repr(audit_events)


@pytest.mark.asyncio
async def test_indeterminate_broker_outcome_is_503_and_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = FakeRedis()
    broker = FakeBroker(
        failure=JarvisExecutionBrokerIndeterminate("unknown")
    )
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)

    async def accept_audit(event: dict[str, object]) -> None:
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            routes.AiToolExecutionRequest(
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read current orders",
            ),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 503
    assert "do not retry automatically" in exc_info.value.detail
    assert len(broker.calls) == 1


@pytest.mark.asyncio
async def test_internal_authorization_recovers_identity_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    principal = principal_with_ops_permission()
    capability = derive_ai_tool_capability(
        principal,
        tool="ops_kpi_query",
    )
    arguments = {"metric": "orders"}
    reason = "read current orders"
    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )

    audit_events: list[dict[str, object]] = []

    async def capture_audit(event: dict[str, object]) -> None:
        audit_events.append(event)

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)

    response = await routes.authorize_internal_ai_tool_execution(
        routes.InternalAiToolAuthorizationRequest(
            grant_token=issued.token.get_secret_value(),
            tool="ops_kpi_query",
            arguments=arguments,
            reason=reason,
        ),
        request_for("/internal/ai/tool-executions/authorize"),
        jarvis_service(),
    )

    assert response.tenant_id == str(TENANT)
    assert response.actor_subject == "user-1"
    assert response.granted_scopes == ("ops:read",)
    assert response.tool == "ops_kpi_query"

    assert len(audit_events) == 1
    event = audit_events[0]
    assert event["tenant_id"] == str(TENANT)
    assert event["actor"] == "user-1"
    assert event["action"] == "ai_tool_execution_authorized"

    metadata = event["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["service_subject"] == "eay-ai-core"
    assert metadata["tool"] == "ops_kpi_query"
    assert "orders" not in repr(metadata)
    assert reason not in repr(metadata)


@pytest.mark.asyncio
async def test_internal_audit_failure_burns_grant_and_denies_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)

    principal = principal_with_ops_permission()
    capability = derive_ai_tool_capability(
        principal,
        tool="ops_kpi_query",
    )
    arguments = {"metric": "orders"}
    reason = "read current orders"
    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )
    token = issued.token.get_secret_value()

    async def fail_audit(event: dict[str, object]) -> None:
        del event
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(routes, "write_audit_event", fail_audit)
    payload = routes.InternalAiToolAuthorizationRequest(
        grant_token=token,
        tool="ops_kpi_query",
        arguments=arguments,
        reason=reason,
    )

    with pytest.raises(HTTPException) as exc_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )
    assert exc_info.value.status_code == 503

    async def accept_audit(event: dict[str, object]) -> None:
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    with pytest.raises(HTTPException) as replay_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )
    assert replay_info.value.status_code == 401
