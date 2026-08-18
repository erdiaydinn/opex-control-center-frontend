import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest

from app.engine_gateway import EngineEndpoint, EngineGatewayError, EngineProvider, RegisteredEngine
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
)
from app.local_first_engine_runtime import LocalFirstProductionRuntime
from app.local_model_pool import (
    LocalCapability,
    LocalModelDeployment,
    LocalModelTask,
    load_local_model_catalog,
)
from app.paid_token_engine_gateway import PaidTokenExecutionContext

CATALOG_PATH = Path(__file__).parents[1] / "config" / "local_model_catalog.json"
NOW = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)


def _task():
    return IntelligenceTask(
        task_id="local-first-code",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT, Modality.CODE),
    )


def _local_task():
    return LocalModelTask(
        task_ref="task:local-first-code",
        task_class="CODE",
        required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.CODE}),
        minimum_benchmark_score=0.80,
    )


def _deployment(**updates):
    payload = dict(
        deployment_id="qwen-local",
        model_family="qwen3-coder",
        model_id="qwen3-coder",
        runtime="OLLAMA",
        endpoint_ref="runtime://ollama/qwen-local",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=0.92,
        benchmark_evidence_ref="benchmark://local/qwen/1",
        observed_capabilities=frozenset(
            {
                LocalCapability.TEXT,
                LocalCapability.CODE,
                LocalCapability.REASONING,
                LocalCapability.AGENTIC,
            }
        ),
        max_context_tokens=65536,
    )
    payload.update(updates)
    return LocalModelDeployment(**payload)


def _registration(model_id="qwen3-coder"):
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id="qwen-local",
            engine_class=EngineClass.LOCAL,
            modalities=(Modality.TEXT, Modality.CODE),
            supports_tools=False,
            supports_long_horizon=True,
            supports_parallel_delegation=False,
            local_processing=True,
            maximum_privacy=PrivacyLevel.RESTRICTED,
            maximum_risk=TaskRisk.CRITICAL,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=0.92,
            benchmark_evidence_ref="benchmark://local/qwen/1",
            independent_provider_key="local:qwen3-coder",
        ),
        endpoint=EngineEndpoint(
            engine_id="qwen-local",
            provider=EngineProvider.OLLAMA,
            model_id=model_id,
            base_url="http://127.0.0.1:11434",
        ),
    )


def _context():
    return PaidTokenExecutionContext(
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )


class _FrontierMustNotRun:
    async def invoke_primary(self, **kwargs):
        raise AssertionError("paid frontier must not run when qualified local model exists")


class _AdminDeniedFrontier:
    def __init__(self):
        self.calls = 0

    async def invoke_primary(self, **kwargs):
        self.calls += 1
        raise EngineGatewayError("paid_token_not_authorized:paid_token_active_platform_admin_grant_missing")


def test_qualified_local_specialist_executes_before_any_paid_frontier_call():
    captured = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"content": "Local specialist answer"},
                "prompt_eval_count": 18,
                "eval_count": 9,
            },
        )

    runtime = LocalFirstProductionRuntime(
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(_deployment(),),
        local_registrations=(_registration(),),
        frontier_runtime=_FrontierMustNotRun(),
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={},
    )
    result = asyncio.run(
        runtime.invoke_primary(
            local_task=_local_task(),
            task=_task(),
            prompt="Review this repository code locally",
            context=_context(),
        )
    )

    assert result.paid_frontier_used is False
    assert result.frontier_receipt is None
    assert result.local_receipt is not None
    assert result.local_receipt.engine_id == "qwen-local"
    assert result.local_receipt.model_id == "qwen3-coder"
    assert result.local_receipt.external_processing is False
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "qwen3-coder"


def test_no_qualified_local_model_does_not_bypass_platform_admin_paid_token_gate():
    frontier = _AdminDeniedFrontier()
    runtime = LocalFirstProductionRuntime(
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(_deployment(enabled=False, runtime_reachable=False, benchmark_score=None, benchmark_evidence_ref=None, observed_capabilities=frozenset()),),
        local_registrations=(_registration(),),
        frontier_runtime=frontier,
        environ={},
    )

    with pytest.raises(
        EngineGatewayError,
        match="paid_token_active_platform_admin_grant_missing",
    ):
        asyncio.run(
            runtime.invoke_primary(
                local_task=_local_task(),
                task=_task(),
                prompt="Escalate only if admin allows paid usage",
                context=_context(),
            )
        )
    assert frontier.calls == 1


def test_selected_local_model_identity_must_match_runtime_registration():
    runtime = LocalFirstProductionRuntime(
        catalog=load_local_model_catalog(CATALOG_PATH),
        deployments=(_deployment(),),
        local_registrations=(_registration(model_id="different-local-model"),),
        frontier_runtime=_FrontierMustNotRun(),
        environ={},
    )

    with pytest.raises(ValueError, match="local_first_runtime_model_identity_mismatch"):
        asyncio.run(
            runtime.invoke_primary(
                local_task=_local_task(),
                task=_task(),
                prompt="Do not silently swap local model identity",
                context=_context(),
            )
        )
