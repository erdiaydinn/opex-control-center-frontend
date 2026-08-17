import asyncio

import httpx
import pytest

from app.engine_gateway import EngineEndpoint, EngineGateway, EngineGatewayError, EngineProvider, RegisteredEngine
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)


def _registration():
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id="openai",
            engine_class=EngineClass.FRONTIER,
            modalities=(Modality.TEXT,),
            supports_long_horizon=True,
            local_processing=False,
            maximum_privacy=PrivacyLevel.INTERNAL,
            maximum_risk=TaskRisk.MEDIUM,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=0.95,
            benchmark_evidence_ref="eval://openai",
            independent_provider_key="openai",
        ),
        endpoint=EngineEndpoint(
            engine_id="openai",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY",
        ),
    )


def _task():
    return IntelligenceTask(
        task_id="safe-error",
        complexity=TaskComplexity.STANDARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
    )


def test_http_auth_failure_is_status_only_and_has_no_request_exception_chain():
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer super-secret-key"
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    gateway = EngineGateway(
        [_registration()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "super-secret-key"},
    )

    with pytest.raises(EngineGatewayError) as caught:
        asyncio.run(gateway.invoke_primary(task=_task(), prompt="Safe prompt"))

    assert str(caught.value) == "openai_responses_http_status:401"
    assert caught.value.__cause__ is None
    assert "super-secret-key" not in str(caught.value)
    assert "Safe prompt" not in str(caught.value)


def test_transport_failure_is_sanitized_without_secret_or_prompt():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("provider unavailable; do not include request body", request=request)

    gateway = EngineGateway(
        [_registration()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "another-secret"},
    )

    with pytest.raises(EngineGatewayError) as caught:
        asyncio.run(gateway.invoke_primary(task=_task(), prompt="Confidential-ish internal prompt"))

    assert str(caught.value) == "openai_responses_transport_error:ConnectError"
    assert caught.value.__cause__ is None
    assert "another-secret" not in str(caught.value)
    assert "Confidential-ish" not in str(caught.value)
