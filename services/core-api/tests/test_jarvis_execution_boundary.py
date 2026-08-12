"""Adversarial tests for the composed Jarvis execution boundary."""

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.core.ai_tool_authorization import SCOPE_PERMISSION_KEYS
from app.core.ai_tool_grants import AiToolGrantBindingMismatch
from app.core.jarvis_execution_boundary import (
    JarvisExecutorUnavailable,
    execute_jarvis_tool,
)
from app.core.jarvis_service_identity import (
    JarvisServiceVerifierSettings,
    VerifiedJarvisService,
)

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")
ACTOR = "user-123"
ASSERTION_ID = "jarvis-assertion-000000000001"
SERVICE_TOKEN = "service.jwt.secret"
GRANT_TOKEN = "grant-bearer-secret-abcdefghijklmnopqrstuvwxyz"
REASON = "Investigate depot KPI variance for the approved dashboard"
ARGUMENTS = {"store": "Dicle", "metric": "nsfr"}


def _principal():
    permission = SCOPE_PERMISSION_KEYS["ops:read"]
    assignment = SimpleNamespace(
        key=permission,
        role_key="super_admin",
        scope={},
    )
    return SimpleNamespace(
        subject=ACTOR,
        tenant_id=TENANT_ID,
        permissions=(permission,),
        permission_assignments=(assignment,),
    )


def _settings():
    return JarvisServiceVerifierSettings(
        jwks_file="/tmp/not-read-because-verifier-is-patched.json"
    )


def _verified():
    return VerifiedJarvisService(
        service_subject="eay-ai-core",
        assertion_id=ASSERTION_ID,
        issued_at=1_000,
        expires_at=1_030,
        replay_ttl_seconds=40,
    )


@pytest.mark.asyncio
async def test_security_boundaries_run_in_required_order(monkeypatch) -> None:
    order: list[str] = []

    async def verify_and_consume(*args, **kwargs):
        order.append("service")
        return _verified()

    monkeypatch.setattr(
        "app.core.jarvis_execution_boundary."
        "verify_and_consume_jarvis_service_assertion",
        verify_and_consume,
    )

    grant_store = SimpleNamespace(consume=AsyncMock())

    async def consume_grant(**kwargs):
        order.append("grant")

    grant_store.consume.side_effect = consume_grant

    async def executor(arguments):
        order.append("execute")
        return {"rows": 3}

    result = await execute_jarvis_tool(
        service_assertion=SERVICE_TOKEN,
        service_settings=_settings(),
        replay_guard=SimpleNamespace(),
        grant_store=grant_store,
        grant_token=GRANT_TOKEN,
        principal=_principal(),
        tool="ops_kpi_query",
        arguments=ARGUMENTS,
        reason=REASON,
        executors={"ops_kpi_query": executor},
    )

    assert order == ["service", "grant", "execute"]
    assert result.result == {"rows": 3}
    assert ASSERTION_ID not in result.service_assertion_id_sha256


@pytest.mark.asyncio
async def test_grant_mismatch_burns_request_before_executor(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.jarvis_execution_boundary."
        "verify_and_consume_jarvis_service_assertion",
        AsyncMock(return_value=_verified()),
    )

    grant_store = SimpleNamespace(
        consume=AsyncMock(
            side_effect=AiToolGrantBindingMismatch(
                "AI tool grant binding does not match"
            )
        )
    )
    executor = AsyncMock()

    with pytest.raises(AiToolGrantBindingMismatch):
        await execute_jarvis_tool(
            service_assertion=SERVICE_TOKEN,
            service_settings=_settings(),
            replay_guard=SimpleNamespace(),
            grant_store=grant_store,
            grant_token=GRANT_TOKEN,
            principal=_principal(),
            tool="ops_kpi_query",
            arguments={"store": "Lara", "metric": "nsfr"},
            reason=REASON,
            executors={"ops_kpi_query": executor},
        )

    executor.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_executor_is_denied_after_single_use_grant(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.jarvis_execution_boundary."
        "verify_and_consume_jarvis_service_assertion",
        AsyncMock(return_value=_verified()),
    )
    grant_store = SimpleNamespace(consume=AsyncMock(return_value=None))
    audit = AsyncMock()

    with pytest.raises(JarvisExecutorUnavailable):
        await execute_jarvis_tool(
            service_assertion=SERVICE_TOKEN,
            service_settings=_settings(),
            replay_guard=SimpleNamespace(),
            grant_store=grant_store,
            grant_token=GRANT_TOKEN,
            principal=_principal(),
            tool="ops_kpi_query",
            arguments=ARGUMENTS,
            reason=REASON,
            executors={},
            audit_sink=audit,
        )

    grant_store.consume.assert_awaited_once()
    event = audit.await_args.args[0]
    assert event["decision"] == "denied"
    assert event["error_type"] == "JarvisExecutorUnavailable"


@pytest.mark.asyncio
async def test_audit_contains_hashes_but_no_bearers_or_raw_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.jarvis_execution_boundary."
        "verify_and_consume_jarvis_service_assertion",
        AsyncMock(return_value=_verified()),
    )
    grant_store = SimpleNamespace(consume=AsyncMock(return_value=None))
    audit = AsyncMock()

    async def executor(arguments):
        return {"secret_result": "must-not-enter-audit"}

    await execute_jarvis_tool(
        service_assertion=SERVICE_TOKEN,
        service_settings=_settings(),
        replay_guard=SimpleNamespace(),
        grant_store=grant_store,
        grant_token=GRANT_TOKEN,
        principal=_principal(),
        tool="ops_kpi_query",
        arguments=ARGUMENTS,
        reason=REASON,
        executors={"ops_kpi_query": executor},
        audit_sink=audit,
    )

    event = audit.await_args.args[0]
    rendered = repr(event)

    assert event["decision"] == "allowed"
    assert len(event["arguments_sha256"]) == 64
    assert len(event["reason_sha256"]) == 64
    assert len(event["service_assertion_id_sha256"]) == 64
    assert SERVICE_TOKEN not in rendered
    assert GRANT_TOKEN not in rendered
    assert REASON not in rendered
    assert "Dicle" not in rendered
    assert "secret_result" not in rendered
    assert ASSERTION_ID not in rendered


@pytest.mark.asyncio
async def test_executor_failure_is_sanitized_and_not_retried(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.core.jarvis_execution_boundary."
        "verify_and_consume_jarvis_service_assertion",
        AsyncMock(return_value=_verified()),
    )
    grant_store = SimpleNamespace(consume=AsyncMock(return_value=None))
    audit = AsyncMock()

    async def executor(arguments):
        raise RuntimeError("warehouse password=do-not-log")

    with pytest.raises(RuntimeError, match="warehouse password"):
        await execute_jarvis_tool(
            service_assertion=SERVICE_TOKEN,
            service_settings=_settings(),
            replay_guard=SimpleNamespace(),
            grant_store=grant_store,
            grant_token=GRANT_TOKEN,
            principal=_principal(),
            tool="ops_kpi_query",
            arguments=ARGUMENTS,
            reason=REASON,
            executors={"ops_kpi_query": executor},
            audit_sink=audit,
        )

    grant_store.consume.assert_awaited_once()
    event = audit.await_args.args[0]
    assert event["decision"] == "error"
    assert event["error_type"] == "RuntimeError"
    assert "password" not in repr(event)
