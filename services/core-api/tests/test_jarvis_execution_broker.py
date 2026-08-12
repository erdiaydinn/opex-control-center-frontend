from __future__ import annotations

import json

import httpx
import pytest

from app.core.jarvis_execution_broker import (
    AI_CORE_EXECUTION_PATH,
    JarvisExecutionBroker,
    JarvisExecutionBrokerContractError,
    JarvisExecutionBrokerIndeterminate,
    JarvisExecutionBrokerSettings,
    JarvisExecutionBrokerUnavailable,
)
from app.core.jarvis_safety_policy import execution_envelope


def valid_response(*, maximum_bytes_billed: int) -> dict[str, object]:
    return {
        "tool": "ops_kpi_query",
        "query_id": "ops.orders.v1",
        "required_scope": ["ops:read"],
        "execution": {
            "execution_id": "execution-1",
            "status": "executed",
            "dry_run_bytes": 100,
            "maximum_bytes_billed": maximum_bytes_billed,
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


def settings(**updates) -> JarvisExecutionBrokerSettings:
    values = {
        "enabled": True,
        "ai_core_base_url": "http://eay-ai-core:8030",
        "request_timeout_seconds": 30,
        "tool_timeout_ms": 20_000,
        "maximum_bytes_billed": 250 * 1024 * 1024,
        "max_rows": 500,
        "max_response_bytes": 2 * 1024 * 1024,
    }
    values.update(updates)
    return JarvisExecutionBrokerSettings(**values)


def ops_policy():
    return execution_envelope(
        "ops_kpi_query",
        arguments={"metric": "orders"},
    )


def test_broker_settings_reject_unsafe_or_ambiguous_base_urls() -> None:
    for invalid in (
        "",
        "ftp://eay-ai-core:8030",
        "http://user:pass@eay-ai-core:8030",
        "http://eay-ai-core:8030/path",
        "http://eay-ai-core:8030?x=1",
        "http://eay-ai-core:8030#fragment",
    ):
        with pytest.raises(ValueError):
            settings(ai_core_base_url=invalid)


def test_broker_timeout_must_cover_server_owned_tool_timeout() -> None:
    with pytest.raises(ValueError, match="must cover"):
        settings(
            request_timeout_seconds=20,
            tool_timeout_ms=20_000,
        )


@pytest.mark.asyncio
async def test_disabled_broker_fails_before_network() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(
        base_url="http://eay-ai-core:8030",
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(
            settings(enabled=False),
            client=client,
        )
        with pytest.raises(JarvisExecutionBrokerUnavailable):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=ops_policy(),
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_broker_sends_grant_once_with_server_owned_execution_policy() -> None:
    seen: dict[str, object] = {}
    broker_settings = settings()
    policy = ops_policy()

    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json=valid_response(
                maximum_bytes_billed=policy.maximum_bytes_billed
            ),
        )

    async with httpx.AsyncClient(
        base_url=broker_settings.ai_core_base_url,
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(
            broker_settings,
            client=client,
        )
        result = await broker.execute(
            grant_token="g" * 43,
            tool="ops_kpi_query",
            arguments={"metric": "orders"},
            reason="read orders",
            execution_policy=policy,
        )

    assert seen["path"] == AI_CORE_EXECUTION_PATH
    body = seen["body"]
    assert isinstance(body, dict)
    assert body == {
        "tool": "ops_kpi_query",
        "arguments": {"metric": "orders"},
        "grant_token": "g" * 43,
        "reason": "read orders",
        "execute": True,
        "maximum_bytes_billed": policy.maximum_bytes_billed,
        "timeout_ms": policy.timeout_ms,
        "max_rows": policy.max_rows,
    }
    assert "tenant_id" not in body
    assert "actor_subject" not in body
    assert "granted_scopes" not in body
    assert "permissions" not in body
    assert result.execution.status == "executed"


@pytest.mark.asyncio
async def test_safety_envelope_cannot_exceed_broker_ceiling() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(500)

    async with httpx.AsyncClient(
        base_url="http://eay-ai-core:8030",
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(
            settings(max_rows=100),
            client=client,
        )
        with pytest.raises(JarvisExecutionBrokerContractError, match="row budget"):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=ops_policy(),
            )

    assert calls == 0


@pytest.mark.asyncio
async def test_transport_failure_is_indeterminate_and_never_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("network failure", request=request)

    async with httpx.AsyncClient(
        base_url="http://eay-ai-core:8030",
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(settings(), client=client)
        with pytest.raises(JarvisExecutionBrokerIndeterminate):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=ops_policy(),
            )

    assert calls == 1


@pytest.mark.asyncio
async def test_503_is_indeterminate_and_never_retried() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    async with httpx.AsyncClient(
        base_url="http://eay-ai-core:8030",
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(settings(), client=client)
        with pytest.raises(JarvisExecutionBrokerIndeterminate):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=ops_policy(),
            )

    assert calls == 1


@pytest.mark.asyncio
async def test_oversized_success_response_is_indeterminate() -> None:
    broker_settings = settings(max_response_bytes=64 * 1024)
    policy = ops_policy()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        payload = valid_response(
            maximum_bytes_billed=policy.maximum_bytes_billed
        )
        payload["execution"]["rows"] = [  # type: ignore[index]
            {"value": "x" * (70 * 1024)}
        ]
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        base_url=broker_settings.ai_core_base_url,
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(broker_settings, client=client)
        with pytest.raises(JarvisExecutionBrokerIndeterminate):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=policy,
            )


@pytest.mark.asyncio
async def test_response_scope_tampering_is_rejected() -> None:
    broker_settings = settings()
    policy = ops_policy()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        payload = valid_response(
            maximum_bytes_billed=policy.maximum_bytes_billed
        )
        payload["required_scope"] = ["ops:read", "legal:read"]
        return httpx.Response(200, json=payload)

    async with httpx.AsyncClient(
        base_url=broker_settings.ai_core_base_url,
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(broker_settings, client=client)
        with pytest.raises(JarvisExecutionBrokerContractError):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=policy,
            )


@pytest.mark.asyncio
async def test_response_cannot_change_server_owned_byte_budget() -> None:
    broker_settings = settings()

    def handler(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(
            200,
            json=valid_response(maximum_bytes_billed=123),
        )

    async with httpx.AsyncClient(
        base_url=broker_settings.ai_core_base_url,
        transport=httpx.MockTransport(handler),
    ) as client:
        broker = JarvisExecutionBroker(broker_settings, client=client)
        with pytest.raises(JarvisExecutionBrokerContractError):
            await broker.execute(
                grant_token="g" * 43,
                tool="ops_kpi_query",
                arguments={"metric": "orders"},
                reason="read orders",
                execution_policy=ops_policy(),
            )
