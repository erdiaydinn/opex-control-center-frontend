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
from app.core.jarvis_execution_idempotency import (
    JarvisIdempotencyConflict,
    JarvisIdempotencyRecord,
    JarvisIdempotencyReplay,
    JarvisIdempotencyUnavailable,
)
from app.core.jarvis_service_identity import VerifiedJarvisService
from app.core.jarvis_service_security import require_fresh_jarvis_service
from app.core.security import (
    PermissionAssignment,
    Principal,
    get_current_principal,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")
IDEMPOTENCY_KEY = "request-20260812-route-0001"


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


class FakeIdempotencyStore:
    def __init__(self, *, fail_dispatch: bool = False) -> None:
        self.records: dict[tuple[str, str, str], JarvisIdempotencyRecord] = {}
        self.fail_dispatch = fail_dispatch
        self.reserve_calls = 0

    @staticmethod
    def _key(tenant_id, actor_subject, idempotency_key):
        return (str(tenant_id), actor_subject, idempotency_key)

    async def reserve(
        self,
        *,
        tenant_id,
        actor_subject,
        idempotency_key,
        request_fingerprint,
    ):
        self.reserve_calls += 1
        key = self._key(tenant_id, actor_subject, idempotency_key)
        existing = self.records.get(key)
        if existing is not None:
            if existing.request_fingerprint != request_fingerprint:
                raise JarvisIdempotencyConflict("conflict")
            raise JarvisIdempotencyReplay(existing.state)
        record = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state="reserved",
        )
        self.records[key] = record
        return record

    async def transition(
        self,
        *,
        tenant_id,
        actor_subject,
        idempotency_key,
        request_fingerprint,
        expected_state,
        new_state,
    ):
        if self.fail_dispatch and new_state == "dispatched":
            raise JarvisIdempotencyUnavailable("dispatch unavailable")
        key = self._key(tenant_id, actor_subject, idempotency_key)
        existing = self.records.get(key)
        if (
            existing is None
            or existing.request_fingerprint != request_fingerprint
            or existing.state != expected_state
        ):
            raise JarvisIdempotencyUnavailable("state mismatch")
        updated = JarvisIdempotencyRecord(
            request_fingerprint=request_fingerprint,
            state=new_state,
        )
        self.records[key] = updated
        return updated

    async def release_reserved(
        self,
        *,
        tenant_id,
        actor_subject,
        idempotency_key,
        request_fingerprint,
    ) -> None:
        key = self._key(tenant_id, actor_subject, idempotency_key)
        existing = self.records.get(key)
        if (
            existing is None
            or existing.request_fingerprint != request_fingerprint
            or existing.state != "reserved"
        ):
            raise JarvisIdempotencyUnavailable("release mismatch")
        del self.records[key]

    def state(self, key: str = IDEMPOTENCY_KEY) -> str | None:
        record = self.records.get((str(TENANT), "user-1", key))
        return record.state if record else None


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
        execution_policy,
    ) -> BrokerToolExecutionResult:
        self.calls.append(
            {
                "grant_token": grant_token,
                "tool": tool,
                "arguments": arguments,
                "reason": reason,
                "execution_policy": execution_policy,
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
                    "maximum_bytes_billed": execution_policy.maximum_bytes_billed,
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


def request_for(
    path: str,
    *,
    idempotency_key: str | None = IDEMPOTENCY_KEY,
    duplicate_key_header: bool = False,
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if idempotency_key is not None:
        encoded = idempotency_key.encode("ascii")
        headers.append((b"idempotency-key", encoded))
        if duplicate_key_header:
            headers.append((b"idempotency-key", encoded))
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": b"",
            "headers": headers,
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


def install_execution_fakes(
    monkeypatch: pytest.MonkeyPatch,
    *,
    broker: FakeBroker | None = None,
    idempotency: FakeIdempotencyStore | None = None,
):
    redis = FakeRedis()
    broker = broker or FakeBroker()
    idempotency = idempotency or FakeIdempotencyStore()
    monkeypatch.setattr(
        routes,
        "_ai_tool_grant_store",
        RedisAiToolGrantStore(redis),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(routes, "_jarvis_execution_broker", broker)
    monkeypatch.setattr(routes, "_jarvis_idempotency_store", idempotency)
    return redis, broker, idempotency


def execution_payload(*, metric: str = "orders"):
    return routes.AiToolExecutionRequest(
        tool="ops_kpi_query",
        arguments={"metric": metric},
        reason="read current orders",
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
        dependency.call for dependency in execution_route.dependant.dependencies
    }
    internal_dependencies = {
        dependency.call for dependency in internal_route.dependant.dependencies
    }
    assert get_current_principal in execution_dependencies
    assert require_fresh_jarvis_service not in execution_dependencies
    assert require_fresh_jarvis_service in internal_dependencies
    assert get_current_principal not in internal_dependencies


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "http_request",
    [
        request_for("/v1/ai/tool-executions", idempotency_key=None),
        request_for(
            "/v1/ai/tool-executions",
            duplicate_key_header=True,
        ),
        request_for(
            "/v1/ai/tool-executions",
            idempotency_key="too-short",
        ),
    ],
)
async def test_execution_requires_exactly_one_valid_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
    http_request: Request,
) -> None:
    _, broker, idempotency = install_execution_fakes(monkeypatch)
    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            http_request,
            principal_with_ops_permission(),
        )
    assert exc_info.value.status_code == 400
    assert broker.calls == []
    assert idempotency.reserve_calls == 0


@pytest.mark.asyncio
async def test_broker_disabled_fails_before_reservation_audit_or_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = FakeBroker(enabled=False)
    redis, _, idempotency = install_execution_fakes(
        monkeypatch,
        broker=broker,
    )
    audit_calls = 0

    async def capture_audit(event):
        nonlocal audit_calls
        audit_calls += 1
        del event

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)
    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )
    assert exc_info.value.status_code == 503
    assert audit_calls == 0
    assert idempotency.reserve_calls == 0
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_safety_denial_happens_before_reservation_audit_grant_or_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, broker, idempotency = install_execution_fakes(monkeypatch)
    audit_calls = 0

    def deny_policy(*args, **kwargs):
        del args, kwargs
        raise routes.JarvisSafetyPolicyDenied("blocked")

    async def capture_audit(event):
        nonlocal audit_calls
        audit_calls += 1
        del event

    monkeypatch.setattr(routes, "execution_envelope", deny_policy)
    monkeypatch.setattr(routes, "write_audit_event", capture_audit)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )

    assert exc_info.value.status_code == 403
    assert audit_calls == 0
    assert idempotency.reserve_calls == 0
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_request_audit_failure_releases_reservation_before_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, broker, idempotency = install_execution_fakes(monkeypatch)

    async def fail_audit(event):
        del event
        raise RuntimeError("audit unavailable")

    monkeypatch.setattr(routes, "write_audit_event", fail_audit)
    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )
    assert exc_info.value.status_code == 503
    assert idempotency.state() is None
    assert redis.values == {}
    assert broker.calls == []


@pytest.mark.asyncio
async def test_happy_path_dispatches_once_and_finishes_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, broker, idempotency = install_execution_fakes(monkeypatch)
    audit_events = []

    async def capture_audit(event):
        audit_events.append(event)

    monkeypatch.setattr(routes, "write_audit_event", capture_audit)
    response = await routes.execute_ai_tool(
        execution_payload(),
        request_for("/v1/ai/tool-executions"),
        principal_with_ops_permission(),
    )
    assert response.execution.status == "executed"
    assert "grant_token" not in response.model_dump(mode="json")
    assert len(broker.calls) == 1
    assert idempotency.state() == "completed"
    assert len(redis.values) == 1
    assert len(audit_events) == 1
    metadata = audit_events[0]["metadata"]
    assert len(metadata["idempotency_request_fingerprint"]) == 64
    assert len(metadata["safety_policy_fingerprint"]) == 64
    assert metadata["safety_policy_version"] == 1
    assert metadata["side_effect_class"] == "read"
    assert broker.calls[0]["execution_policy"].safety_policy_fingerprint == metadata[
        "safety_policy_fingerprint"
    ]
    assert IDEMPOTENCY_KEY not in repr(audit_events)


@pytest.mark.asyncio
async def test_duplicate_same_key_never_issues_second_grant_or_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, broker, idempotency = install_execution_fakes(monkeypatch)

    async def accept_audit(event):
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    principal = principal_with_ops_permission()
    await routes.execute_ai_tool(
        execution_payload(),
        request_for("/v1/ai/tool-executions"),
        principal,
    )
    grants_after_first = len(redis.values)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal,
        )
    assert exc_info.value.status_code == 409
    assert "do not retry automatically" in exc_info.value.detail
    assert len(broker.calls) == 1
    assert len(redis.values) == grants_after_first
    assert idempotency.state() == "completed"


@pytest.mark.asyncio
async def test_same_key_with_changed_request_is_conflict_without_dispatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis, broker, _ = install_execution_fakes(monkeypatch)

    async def accept_audit(event):
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    principal = principal_with_ops_permission()
    await routes.execute_ai_tool(
        execution_payload(),
        request_for("/v1/ai/tool-executions"),
        principal,
    )
    grants_after_first = len(redis.values)

    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(metric="refund"),
            request_for("/v1/ai/tool-executions"),
            principal,
        )
    assert exc_info.value.status_code == 409
    assert len(broker.calls) == 1
    assert len(redis.values) == grants_after_first


@pytest.mark.asyncio
async def test_dispatch_state_failure_prevents_ai_core_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    idempotency = FakeIdempotencyStore(fail_dispatch=True)
    redis, broker, _ = install_execution_fakes(
        monkeypatch,
        idempotency=idempotency,
    )

    async def accept_audit(event):
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )
    assert exc_info.value.status_code == 503
    assert broker.calls == []
    assert len(redis.values) == 1
    assert idempotency.state() == "reserved"


@pytest.mark.asyncio
async def test_indeterminate_broker_marks_key_and_never_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    broker = FakeBroker(
        failure=JarvisExecutionBrokerIndeterminate("unknown")
    )
    _, broker, idempotency = install_execution_fakes(
        monkeypatch,
        broker=broker,
    )

    async def accept_audit(event):
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    with pytest.raises(HTTPException) as exc_info:
        await routes.execute_ai_tool(
            execution_payload(),
            request_for("/v1/ai/tool-executions"),
            principal_with_ops_permission(),
        )
    assert exc_info.value.status_code == 503
    assert len(broker.calls) == 1
    assert idempotency.state() == "indeterminate"


@pytest.mark.asyncio
async def test_internal_authorization_recovers_identity_and_writes_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)
    capability = derive_ai_tool_capability(
        principal_with_ops_permission(),
        tool="ops_kpi_query",
    )
    arguments = {"metric": "orders"}
    reason = "read current orders"
    issued = await store.issue(
        capability,
        arguments=arguments,
        reason=reason,
    )
    audit_events = []

    async def capture_audit(event):
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
    assert len(audit_events) == 1


@pytest.mark.asyncio
async def test_internal_audit_failure_burns_grant(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = RedisAiToolGrantStore(FakeRedis())  # type: ignore[arg-type]
    monkeypatch.setattr(routes, "_ai_tool_grant_store", store)
    capability = derive_ai_tool_capability(
        principal_with_ops_permission(),
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

    async def fail_audit(event):
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

    async def accept_audit(event):
        del event

    monkeypatch.setattr(routes, "write_audit_event", accept_audit)
    with pytest.raises(HTTPException) as replay_info:
        await routes.authorize_internal_ai_tool_execution(
            payload,
            request_for("/internal/ai/tool-executions/authorize"),
            jarvis_service(),
        )
    assert replay_info.value.status_code == 401
