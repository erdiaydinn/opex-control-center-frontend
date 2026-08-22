import asyncio
import json
from datetime import datetime, timezone

import httpx
import pytest

from app.benchmark_runner import (
    BenchmarkCaseOutcome,
    BenchmarkEnvironmentManifest,
    BenchmarkTaskCase,
    BenchmarkTaskSuite,
    run_system_benchmark,
)
from app.engine_benchmark_adapter import build_gateway_reasoning_benchmark_adapter
from app.engine_gateway import (
    BenchmarkInvocationContext,
    EngineEndpoint,
    EngineGateway,
    EngineGatewayError,
    EngineInvocationMode,
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


def _candidate(*, exact=True):
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id="openai-candidate",
            engine_class=EngineClass.FRONTIER,
            modalities=(Modality.TEXT,),
            supports_tools=False,
            supports_long_horizon=True,
            local_processing=False,
            maximum_privacy=PrivacyLevel.RESTRICTED,
            maximum_risk=TaskRisk.CRITICAL,
            exact_adapter_verified=exact,
            production_enabled=False,
            benchmark_score=None,
            benchmark_evidence_ref=None,
            independent_provider_key="openai",
        ),
        endpoint=EngineEndpoint(
            engine_id="openai-candidate",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY",
        ),
    )


def _suite():
    return BenchmarkTaskSuite(
        task_set_id="reasoning-bench-v1",
        cases=(
            BenchmarkTaskCase(
                case_id="case-1",
                prompt="Return the governed conclusion from synthetic evidence.",
                category="reasoning",
                side_effect=False,
                expected_evaluator_ref="evaluator://exact-text-v1",
            ),
        ),
    )


def _environment():
    return BenchmarkEnvironmentManifest(
        environment_id="reasoning-fixture-v1",
        components={"fixture": "v1", "network_profile": "mocked"},
    )


def _task(case, *, privacy=PrivacyLevel.INTERNAL, external=False, tools=False):
    return IntelligenceTask(
        task_id=case.case_id,
        complexity=TaskComplexity.STANDARD,
        risk=TaskRisk.MEDIUM,
        privacy=privacy,
        modalities=(Modality.TEXT,),
        requires_tools=tools,
        external_processing_authorized=external,
    )


def _gateway(candidate=None, *, called=None):
    async def handler(request: httpx.Request) -> httpx.Response:
        if called is not None:
            called.append(str(request.url))
        payload = json.loads(request.content)
        assert payload["store"] is False
        return httpx.Response(
            200,
            json={
                "id": "resp-benchmark-1",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "EXPECTED"}],
                    }
                ],
                "usage": {"input_tokens": 8, "output_tokens": 2},
            },
        )

    return EngineGateway(
        [candidate or _candidate()],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "benchmark-secret"},
    )


def test_unpromoted_candidate_cannot_use_normal_route_but_can_run_benchmark_only():
    gateway = _gateway()
    case = _suite().cases[0]

    with pytest.raises(EngineGatewayError, match="engine_routing_plan_not_executable"):
        asyncio.run(gateway.invoke_primary(task=_task(case), prompt=case.prompt))

    receipt = asyncio.run(
        gateway.invoke_for_benchmark(
            engine_id="openai-candidate",
            task=_task(case),
            prompt=case.prompt,
            context=BenchmarkInvocationContext(
                benchmark_run_ref="benchmark-run://candidate-001",
                engine_id="openai-candidate",
                task_set_fingerprint=_suite().fingerprint(),
                environment_fingerprint=_environment().fingerprint(),
                evaluator_ref=case.expected_evaluator_ref,
            ),
        )
    )

    assert receipt.output_text == "EXPECTED"
    assert receipt.invocation_mode is EngineInvocationMode.BENCHMARK
    assert receipt.benchmark_context_ref == "benchmark-run://candidate-001"
    assert receipt.provider_tools_enabled is False
    assert receipt.routing_plan.primary_engine_id == "openai-candidate"


def test_gateway_benchmark_adapter_feeds_measured_runner_without_retaining_prompt_or_secret():
    seen = {}
    suite = _suite()
    environment = _environment()
    gateway = _gateway()

    def evidence_writer(case, receipt):
        seen["mode"] = receipt.invocation_mode
        seen["text"] = receipt.output_text
        return f"provider-evidence://{receipt.provider_response_id}"

    def evaluator(case, receipt):
        return BenchmarkCaseOutcome(
            task_success=receipt.output_text == "EXPECTED",
            evidence_refs=("evaluator-evidence://case-1",),
        )

    adapter = build_gateway_reasoning_benchmark_adapter(
        gateway=gateway,
        engine_id="openai-candidate",
        system_version="gpt-5.6-candidate",
        suite=suite,
        environment=environment,
        benchmark_run_ref="benchmark-run://candidate-002",
        task_factory=_task,
        evaluator=evaluator,
        receipt_evidence_writer=evidence_writer,
    )
    result = asyncio.run(
        run_system_benchmark(
            adapter=adapter,
            suite=suite,
            environment=environment,
            measured_at=datetime(2026, 8, 18, 6, 40, tzinfo=timezone.utc),
        )
    )

    assert result.run.system_id == "openai-candidate"
    assert result.evidence.records[0].task_success is True
    assert "provider-evidence://resp-benchmark-1" in result.evidence.records[0].evidence_refs
    assert "evaluator-evidence://case-1" in result.evidence.records[0].evidence_refs
    assert seen["mode"] is EngineInvocationMode.BENCHMARK
    serialized = result.model_dump_json()
    assert suite.cases[0].prompt not in serialized
    assert "benchmark-secret" not in serialized


def test_confidential_external_candidate_requires_explicit_external_processing_authorization():
    called = []
    gateway = _gateway(called=called)
    case = _suite().cases[0]
    context = BenchmarkInvocationContext(
        benchmark_run_ref="benchmark-run://candidate-003",
        engine_id="openai-candidate",
        task_set_fingerprint=_suite().fingerprint(),
        environment_fingerprint=_environment().fingerprint(),
        evaluator_ref=case.expected_evaluator_ref,
    )

    with pytest.raises(EngineGatewayError, match="benchmark_engine_does_not_satisfy_task_boundary"):
        asyncio.run(
            gateway.invoke_for_benchmark(
                engine_id="openai-candidate",
                task=_task(case, privacy=PrivacyLevel.CONFIDENTIAL, external=False),
                prompt=case.prompt,
                context=context,
            )
        )
    assert called == []

    receipt = asyncio.run(
        gateway.invoke_for_benchmark(
            engine_id="openai-candidate",
            task=_task(case, privacy=PrivacyLevel.CONFIDENTIAL, external=True),
            prompt=case.prompt,
            context=context,
        )
    )
    assert receipt.external_processing is True
    assert len(called) == 1


def test_benchmark_mode_forbids_provider_tools_even_if_task_requests_them():
    called = []
    gateway = _gateway(called=called)
    case = _suite().cases[0]

    with pytest.raises(EngineGatewayError, match="benchmark_engine_invocation_forbids_provider_tools"):
        asyncio.run(
            gateway.invoke_for_benchmark(
                engine_id="openai-candidate",
                task=_task(case, tools=True),
                prompt=case.prompt,
                context=BenchmarkInvocationContext(
                    benchmark_run_ref="benchmark-run://candidate-004",
                    engine_id="openai-candidate",
                    task_set_fingerprint=_suite().fingerprint(),
                    environment_fingerprint=_environment().fingerprint(),
                    evaluator_ref=case.expected_evaluator_ref,
                ),
            )
        )
    assert called == []


def test_unverified_adapter_cannot_be_benchmarked():
    called = []
    gateway = _gateway(_candidate(exact=False), called=called)
    case = _suite().cases[0]

    with pytest.raises(EngineGatewayError, match="benchmark_engine_does_not_satisfy_task_boundary"):
        asyncio.run(
            gateway.invoke_for_benchmark(
                engine_id="openai-candidate",
                task=_task(case),
                prompt=case.prompt,
                context=BenchmarkInvocationContext(
                    benchmark_run_ref="benchmark-run://candidate-005",
                    engine_id="openai-candidate",
                    task_set_fingerprint=_suite().fingerprint(),
                    environment_fingerprint=_environment().fingerprint(),
                    evaluator_ref=case.expected_evaluator_ref,
                ),
            )
        )
    assert called == []
