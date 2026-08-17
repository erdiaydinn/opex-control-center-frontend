import asyncio
import json

import httpx

from app.engine_gateway import EngineEndpoint, EngineGateway, EngineProvider, RegisteredEngine
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)


def _profile(engine_id: str, score: float) -> IntelligenceEngine:
    return IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.FRONTIER,
        modalities=(Modality.TEXT,),
        supports_tools=False,
        supports_long_horizon=True,
        supports_parallel_delegation=True,
        local_processing=False,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"eval://{engine_id}",
        independent_provider_key=engine_id,
    )


def _openai(score: float = 0.99) -> RegisteredEngine:
    return RegisteredEngine(
        profile=_profile("openai", score),
        endpoint=EngineEndpoint(
            engine_id="openai",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY",
            max_output_tokens=512,
        ),
    )


def _anthropic(score: float = 0.98) -> RegisteredEngine:
    return RegisteredEngine(
        profile=_profile("anthropic", score),
        endpoint=EngineEndpoint(
            engine_id="anthropic",
            provider=EngineProvider.ANTHROPIC_MESSAGES,
            model_id="claude-opus-4-8",
            base_url="https://api.anthropic.com",
            secret_ref="env:ANTHROPIC_API_KEY",
            max_output_tokens=512,
        ),
    )


def _gemini(score: float = 0.97) -> RegisteredEngine:
    return RegisteredEngine(
        profile=_profile("gemini", score),
        endpoint=EngineEndpoint(
            engine_id="gemini",
            provider=EngineProvider.GEMINI_GENERATE_CONTENT,
            model_id="gemini-3.1-pro-preview",
            base_url="https://generativelanguage.googleapis.com",
            secret_ref="env:GEMINI_API_KEY",
            max_output_tokens=512,
        ),
    )


def _task(*, risk: TaskRisk = TaskRisk.MEDIUM) -> IntelligenceTask:
    return IntelligenceTask(
        task_id="cross-provider-reasoning",
        complexity=TaskComplexity.HARD,
        risk=risk,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
    )


def test_anthropic_messages_adapter_is_secret_safe_and_tool_free():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-api-key")
        captured["version"] = request.headers.get("anthropic-version")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "id": "msg_123",
                "type": "message",
                "content": [{"type": "text", "text": "Independent Claude analysis."}],
                "usage": {"input_tokens": 21, "output_tokens": 8},
            },
        )

    gateway = EngineGateway(
        [_anthropic()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"ANTHROPIC_API_KEY": "anthropic-secret"},
    )
    receipt = asyncio.run(gateway.invoke_primary(task=_task(), prompt="Analyze the operation"))

    assert captured["url"] == "https://api.anthropic.com/v1/messages"
    assert captured["key"] == "anthropic-secret"
    assert captured["version"] == "2023-06-01"
    assert captured["payload"]["model"] == "claude-opus-4-8"
    assert captured["payload"]["max_tokens"] == 512
    assert "tools" not in captured["payload"]
    assert receipt.provider is EngineProvider.ANTHROPIC_MESSAGES
    assert receipt.output_text == "Independent Claude analysis."
    assert receipt.input_tokens == 21
    assert receipt.output_tokens == 8
    serialized = receipt.model_dump_json()
    assert "anthropic-secret" not in serialized
    assert "Analyze the operation" not in serialized


def test_gemini_generate_content_adapter_is_secret_safe_and_tool_free():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["key"] = request.headers.get("x-goog-api-key")
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "responseId": "gemini-response-1",
                "candidates": [
                    {"content": {"parts": [{"text": "Independent Gemini analysis."}]}}
                ],
                "usageMetadata": {"promptTokenCount": 19, "candidatesTokenCount": 7},
            },
        )

    gateway = EngineGateway(
        [_gemini()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"GEMINI_API_KEY": "gemini-secret"},
    )
    receipt = asyncio.run(gateway.invoke_primary(task=_task(), prompt="Analyze the operation"))

    assert captured["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-3.1-pro-preview:generateContent"
    )
    assert captured["key"] == "gemini-secret"
    assert captured["payload"]["generationConfig"]["maxOutputTokens"] == 512
    assert "tools" not in captured["payload"]
    assert receipt.provider is EngineProvider.GEMINI_GENERATE_CONTENT
    assert receipt.output_text == "Independent Gemini analysis."
    assert receipt.input_tokens == 19
    assert receipt.output_tokens == 7
    serialized = receipt.model_dump_json()
    assert "gemini-secret" not in serialized
    assert "Analyze the operation" not in serialized


def test_high_risk_router_invokes_primary_and_independent_frontier_critic():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        host = request.url.host
        if host == "api.openai.com":
            return httpx.Response(
                200,
                json={
                    "id": "resp_1",
                    "output": [
                        {"type": "message", "content": [{"type": "output_text", "text": "Primary."}]}
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 2},
                },
            )
        if host == "api.anthropic.com":
            return httpx.Response(
                200,
                json={
                    "id": "msg_1",
                    "content": [{"type": "text", "text": "Critic."}],
                    "usage": {"input_tokens": 11, "output_tokens": 2},
                },
            )
        raise AssertionError(f"unexpected provider host: {host}")

    transport = httpx.MockTransport(handler)
    gateway = EngineGateway(
        [_openai(), _anthropic(), _gemini()],
        transport_factory=lambda endpoint: transport,
        environ={
            "OPENAI_API_KEY": "openai-secret",
            "ANTHROPIC_API_KEY": "anthropic-secret",
            "GEMINI_API_KEY": "gemini-secret",
        },
    )
    receipts = asyncio.run(
        gateway.invoke_routed_engines(
            task=_task(risk=TaskRisk.HIGH),
            prompt="Challenge this executive decision",
        )
    )

    assert [receipt.engine_id for receipt in receipts] == ["openai", "anthropic"]
    assert receipts[0].routing_plan.primary_engine_id == "openai"
    assert receipts[0].routing_plan.critic_engine_ids == ("anthropic",)
    assert calls == [
        "https://api.openai.com/v1/responses",
        "https://api.anthropic.com/v1/messages",
    ]
