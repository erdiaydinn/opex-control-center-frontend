import asyncio
import json

import httpx
import pytest

from app.engine_gateway import (
    EngineEndpoint,
    EngineGateway,
    EngineGatewayError,
    EngineProvider,
    RegisteredEngine,
)
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)


def _profile(engine_id, *, local, score, privacy=PrivacyLevel.RESTRICTED):
    return IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.LOCAL if local else EngineClass.FRONTIER,
        modalities=(Modality.TEXT,),
        supports_tools=False,
        supports_long_horizon=True,
        supports_parallel_delegation=True,
        local_processing=local,
        maximum_privacy=privacy,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"eval://{engine_id}",
        independent_provider_key=engine_id,
    )


def _local():
    return RegisteredEngine(
        profile=_profile("ollama-local", local=True, score=0.80),
        endpoint=EngineEndpoint(
            engine_id="ollama-local",
            provider=EngineProvider.OLLAMA,
            model_id="eay-ops:0.1",
            base_url="http://127.0.0.1:11434",
        ),
    )


def _frontier():
    return RegisteredEngine(
        profile=_profile("openai-frontier", local=False, score=0.99),
        endpoint=EngineEndpoint(
            engine_id="openai-frontier",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY",
            max_output_tokens=1024,
        ),
    )


def _task(**overrides):
    payload = dict(
        task_id="executive-analysis",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=False,
    )
    payload.update(overrides)
    return IntelligenceTask(**payload)


def test_frontier_openai_adapter_uses_responses_api_store_false_and_retains_no_secret():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["authorization"] = request.headers.get("authorization")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "resp_123",
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": "Capacity risk is material.", "annotations": []}
                        ],
                    }
                ],
                "usage": {"input_tokens": 12, "output_tokens": 6},
            },
        )

    transport = httpx.MockTransport(handler)
    gateway = EngineGateway(
        [_local(), _frontier()],
        transport_factory=lambda endpoint: transport,
        environ={"OPENAI_API_KEY": "sk-test-super-secret"},
    )
    receipt = asyncio.run(gateway.invoke_primary(task=_task(), prompt="Analyze capacity risk"))

    assert receipt.engine_id == "openai-frontier"
    assert receipt.provider is EngineProvider.OPENAI_RESPONSES
    assert receipt.output_text == "Capacity risk is material."
    assert receipt.input_tokens == 12
    assert receipt.output_tokens == 6
    assert receipt.external_processing is True
    assert captured["url"] == "https://api.openai.com/v1/responses"
    assert captured["authorization"] == "Bearer sk-test-super-secret"
    assert captured["payload"]["model"] == "gpt-5.6"
    assert captured["payload"]["store"] is False
    assert "tools" not in captured["payload"]
    assert "background" not in captured["payload"]
    serialized = receipt.model_dump_json()
    assert "sk-test-super-secret" not in serialized
    assert "Analyze capacity risk" not in serialized
    assert receipt.prompt_retained is False
    assert receipt.secret_retained is False


def test_confidential_task_stays_local_without_external_authorization():
    called_urls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        called_urls.append(str(request.url))
        if "11434" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Local confidential answer"},
                    "prompt_eval_count": 10,
                    "eval_count": 4,
                },
            )
        raise AssertionError("frontier endpoint must not be called")

    transport = httpx.MockTransport(handler)
    gateway = EngineGateway(
        [_local(), _frontier()],
        transport_factory=lambda endpoint: transport,
        environ={"OPENAI_API_KEY": "sk-test"},
    )
    receipt = asyncio.run(
        gateway.invoke_primary(
            task=_task(privacy=PrivacyLevel.CONFIDENTIAL),
            prompt="Sensitive company analysis",
        )
    )

    assert receipt.engine_id == "ollama-local"
    assert receipt.external_processing is False
    assert called_urls == ["http://127.0.0.1:11434/api/chat"]


def test_explicit_authorization_can_route_confidential_task_to_frontier():
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_authorized",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Authorized frontier answer"}]}
                ],
                "usage": {"input_tokens": 5, "output_tokens": 3},
            },
        )

    gateway = EngineGateway(
        [_local(), _frontier()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "sk-test"},
    )
    receipt = asyncio.run(
        gateway.invoke_primary(
            task=_task(
                privacy=PrivacyLevel.CONFIDENTIAL,
                external_processing_authorized=True,
            ),
            prompt="Authorized confidential analysis",
        )
    )

    assert receipt.engine_id == "openai-frontier"


def test_missing_frontier_secret_fails_before_network_call():
    called = False

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    gateway = EngineGateway(
        [_frontier()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={},
    )
    with pytest.raises(EngineGatewayError, match="engine_secret_not_available"):
        asyncio.run(gateway.invoke_primary(task=_task(), prompt="Analyze"))
    assert called is False


def test_local_ollama_adapter_preserves_existing_api_chat_shape():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"content": "Local answer"},
                "prompt_eval_count": 20,
                "eval_count": 7,
            },
        )

    gateway = EngineGateway(
        [_local()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
    )
    receipt = asyncio.run(gateway.invoke_primary(task=_task(), prompt="Local reasoning"))

    assert receipt.engine_id == "ollama-local"
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "eay-ops:0.1"
    assert captured["payload"]["messages"] == [{"role": "user", "content": "Local reasoning"}]
    assert captured["payload"]["stream"] is False
    assert receipt.input_tokens == 20
    assert receipt.output_tokens == 7


def test_openai_endpoint_is_locked_to_official_https_host():
    with pytest.raises(ValueError, match="openai_endpoint_host_must_be_official"):
        EngineEndpoint(
            engine_id="bad",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://proxy.example.com",
            secret_ref="env:OPENAI_API_KEY",
        )


def test_remote_ollama_requires_explicit_authorization():
    with pytest.raises(ValueError, match="ollama_remote_endpoint_requires_explicit_authorization"):
        EngineEndpoint(
            engine_id="remote-local",
            provider=EngineProvider.OLLAMA,
            model_id="eay-ops:0.1",
            base_url="https://ollama.internal.example.com",
        )
