import asyncio
import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.engine_efficiency_intelligence import (
    append_engine_efficiency_observation,
    build_engine_efficiency_preferences,
    new_engine_efficiency_ledger,
    record_engine_efficiency_observation,
    select_local_model_with_efficiency,
)
from app.engine_gateway import EngineEndpoint, EngineProvider, RegisteredEngine
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
    CommercialUseStatus,
    LocalCapability,
    LocalModelCatalog,
    LocalModelCatalogEntry,
    LocalModelDeployment,
    LocalModelTask,
)
from app.paid_token_engine_gateway import PaidTokenExecutionContext

NOW = datetime(2026, 8, 19, 10, 0, tzinfo=timezone.utc)
TENANT = "tenant:customer-a"


def _entry(family: str) -> LocalModelCatalogEntry:
    return LocalModelCatalogEntry(
        model_family=family,
        recommended_runtime="OLLAMA",
        default_model_id=f"{family}-model",
        license="Apache-2.0",
        commercial_use_status=CommercialUseStatus.PERMISSIVE_LICENSE_REVIEWED,
        capabilities=frozenset({LocalCapability.TEXT, LocalCapability.CODE}),
        preferred_tasks=frozenset({"CODE"}),
        production_candidate=True,
    )


def _catalog() -> LocalModelCatalog:
    return LocalModelCatalog(
        version=1,
        models=(_entry("slow-family"), _entry("fast-family")),
    )


def _deployment(
    deployment_id: str,
    family: str,
    score: float,
) -> LocalModelDeployment:
    return LocalModelDeployment(
        deployment_id=deployment_id,
        model_family=family,
        model_id=f"{family}-model",
        runtime="OLLAMA",
        endpoint_ref=f"runtime://ollama/{deployment_id}",
        enabled=True,
        runtime_reachable=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"benchmark://{deployment_id}/1",
        observed_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.CODE}),
        max_context_tokens=32768,
    )


def _deployments(*, fast_score: float = 0.91) -> tuple[LocalModelDeployment, ...]:
    return (
        _deployment("slow-local", "slow-family", 0.92),
        _deployment("fast-local", "fast-family", fast_score),
    )


def _local_task() -> LocalModelTask:
    return LocalModelTask(
        task_ref="task:code-review",
        task_class="CODE",
        required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.CODE}),
        minimum_benchmark_score=0.80,
    )


def _intelligence_task() -> IntelligenceTask:
    return IntelligenceTask(
        task_id="code-review",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT, Modality.CODE),
    )


def _registration(deployment: LocalModelDeployment) -> RegisteredEngine:
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id=deployment.deployment_id,
            engine_class=EngineClass.LOCAL,
            modalities=(Modality.TEXT, Modality.CODE),
            supports_long_horizon=True,
            local_processing=True,
            maximum_privacy=PrivacyLevel.RESTRICTED,
            maximum_risk=TaskRisk.CRITICAL,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=deployment.benchmark_score,
            benchmark_evidence_ref=deployment.benchmark_evidence_ref,
            independent_provider_key=f"local:{deployment.deployment_id}",
        ),
        endpoint=EngineEndpoint(
            engine_id=deployment.deployment_id,
            provider=EngineProvider.OLLAMA,
            model_id=deployment.model_id,
            base_url="http://127.0.0.1:11434",
        ),
    )


def _context() -> PaidTokenExecutionContext:
    return PaidTokenExecutionContext(
        subject_user_ref="user:42",
        tenant_ref=TENANT,
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )


def _ledger_with_samples(
    *,
    slow_samples: int = 5,
    fast_samples: int = 5,
    fast_observed_after_cutoff: bool = False,
):
    ledger = new_engine_efficiency_ledger(
        tenant_id=TENANT,
        generated_at=NOW - timedelta(hours=2),
    )
    for engine_id, count, latency in (
        ("slow-local", slow_samples, 420),
        ("fast-local", fast_samples, 90),
    ):
        for index in range(count):
            base_time = NOW - timedelta(minutes=30 - index)
            if engine_id == "fast-local" and fast_observed_after_cutoff:
                base_time = NOW + timedelta(minutes=10 + index)
            observation = record_engine_efficiency_observation(
                tenant_id=TENANT,
                engine_id=engine_id,
                task_class="CODE",
                observed_at=base_time,
                recorded_at=base_time + timedelta(seconds=5),
                succeeded=True,
                latency_ms=latency,
                invocation_evidence_ref=f"engine-run://{engine_id}/{index}",
                cost_observed=True,
            )
            ledger = append_engine_efficiency_observation(
                ledger=ledger,
                observation=observation,
            )
    return ledger


class _FrontierMustNotRun:
    async def invoke_primary(self, **kwargs):
        raise AssertionError("frontier must not run while qualified local models exist")


def test_complete_near_equal_quality_band_prefers_measured_faster_local_engine():
    selection = select_local_model_with_efficiency(
        task=_local_task(),
        deployments=_deployments(),
        catalog=_catalog(),
        ledger=_ledger_with_samples(),
        tenant_id=TENANT,
        as_of=NOW,
    )

    assert selection.deployment_id == "fast-local"
    assert selection.benchmark_score == 0.91
    assert selection.local_execution_available is True
    assert selection.paid_frontier_escalation_required is False


def test_efficiency_never_overrides_model_outside_benchmark_quality_band():
    selection = select_local_model_with_efficiency(
        task=_local_task(),
        deployments=_deployments(fast_score=0.85),
        catalog=_catalog(),
        ledger=_ledger_with_samples(),
        tenant_id=TENANT,
        as_of=NOW,
    )

    assert selection.deployment_id == "slow-local"
    assert selection.benchmark_score == 0.92


def test_incomplete_comparison_remains_neutral_instead_of_rewarding_under_sampled_model():
    selection = select_local_model_with_efficiency(
        task=_local_task(),
        deployments=_deployments(),
        catalog=_catalog(),
        ledger=_ledger_with_samples(slow_samples=5, fast_samples=4),
        tenant_id=TENANT,
        as_of=NOW,
    )

    assert selection.deployment_id == "slow-local"


def test_future_recorded_efficiency_cannot_leak_into_historical_routing():
    ledger = _ledger_with_samples(fast_observed_after_cutoff=True)
    preferences = build_engine_efficiency_preferences(
        ledger=ledger,
        tenant_id=TENANT,
        task_class="CODE",
        engine_ids=("slow-local", "fast-local"),
        as_of=NOW,
        min_samples=5,
    )
    by_engine = {item.engine_id: item for item in preferences}

    assert by_engine["slow-local"].sample_count == 5
    assert by_engine["slow-local"].enough_samples is True
    assert by_engine["fast-local"].sample_count == 0
    assert by_engine["fast-local"].enough_samples is False

    selection = select_local_model_with_efficiency(
        task=_local_task(),
        deployments=_deployments(),
        catalog=_catalog(),
        ledger=ledger,
        tenant_id=TENANT,
        as_of=NOW,
    )
    assert selection.deployment_id == "slow-local"


def test_tampered_efficiency_ledger_is_rejected_before_routing():
    ledger = _ledger_with_samples()
    tampered = ledger.model_copy(
        update={"generated_at": ledger.generated_at + timedelta(seconds=1)}
    )

    with pytest.raises(ValueError, match="engine_efficiency_ledger_fingerprint_mismatch"):
        select_local_model_with_efficiency(
            task=_local_task(),
            deployments=_deployments(),
            catalog=_catalog(),
            ledger=tampered,
            tenant_id=TENANT,
            as_of=NOW,
        )


def test_secret_bearing_invocation_reference_is_rejected():
    with pytest.raises(ValueError, match="engine_efficiency_secret_bearing_reference_forbidden"):
        record_engine_efficiency_observation(
            tenant_id=TENANT,
            engine_id="fast-local",
            task_class="CODE",
            observed_at=NOW - timedelta(minutes=1),
            recorded_at=NOW,
            succeeded=True,
            latency_ms=80,
            invocation_evidence_ref="trace://run?token=should-not-be-stored",
            cost_observed=True,
        )


def test_local_first_runtime_consumes_efficiency_snapshot_without_touching_frontier():
    captured = {}
    deployments = _deployments()

    async def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["payload"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "message": {"content": "Fast local answer"},
                "prompt_eval_count": 12,
                "eval_count": 4,
            },
        )

    runtime = LocalFirstProductionRuntime(
        catalog=_catalog(),
        deployments=deployments,
        local_registrations=tuple(_registration(item) for item in deployments),
        frontier_runtime=_FrontierMustNotRun(),
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={},
        efficiency_snapshot=_ledger_with_samples(),
    )
    result = asyncio.run(
        runtime.invoke_primary(
            local_task=_local_task(),
            task=_intelligence_task(),
            prompt="Use measured local efficiency only inside the quality band",
            context=_context(),
        )
    )

    assert result.selection.deployment_id == "fast-local"
    assert result.local_receipt is not None
    assert result.local_receipt.engine_id == "fast-local"
    assert result.paid_frontier_used is False
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["payload"]["model"] == "fast-family-model"
