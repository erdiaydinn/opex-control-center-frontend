import asyncio
from datetime import datetime, timedelta, timezone

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
from app.paid_token_engine_gateway import PaidTokenExecutionContext
from app.paid_token_governance import PaidTokenGrant, PlatformRole, ProviderRateCard
from app.production_engine_runtime import build_production_engine_runtime

NOW = datetime(2026, 8, 18, 9, 50, tzinfo=timezone.utc)


def _profile(engine_id: str, *, local: bool, score: float) -> IntelligenceEngine:
    return IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.LOCAL if local else EngineClass.FRONTIER,
        modalities=(Modality.TEXT,),
        supports_tools=False,
        supports_long_horizon=True,
        supports_parallel_delegation=True,
        local_processing=local,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"eval://{engine_id}",
        independent_provider_key=engine_id,
    )


def _frontier() -> RegisteredEngine:
    return RegisteredEngine(
        profile=_profile("openai", local=False, score=0.99),
        endpoint=EngineEndpoint(
            engine_id="openai",
            provider=EngineProvider.OPENAI_RESPONSES,
            model_id="gpt-5.6",
            base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY",
            max_output_tokens=1000,
        ),
    )


def _local() -> RegisteredEngine:
    return RegisteredEngine(
        profile=_profile("local", local=True, score=0.80),
        endpoint=EngineEndpoint(
            engine_id="local",
            provider=EngineProvider.OLLAMA,
            model_id="eay-local",
            base_url="http://127.0.0.1:11434",
        ),
    )


def _task(*, privacy: PrivacyLevel = PrivacyLevel.INTERNAL) -> IntelligenceTask:
    return IntelligenceTask(
        task_id="production-runtime-test",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=privacy,
        modalities=(Modality.TEXT,),
    )


def _context(user: str = "user:42") -> PaidTokenExecutionContext:
    return PaidTokenExecutionContext(
        subject_user_ref=user,
        tenant_ref="tenant:customer-a",
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )


def _grant() -> PaidTokenGrant:
    return PaidTokenGrant(
        grant_id="grant:user-42",
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        billing_account_ref="billing:customer-a:user-42",
        allowed_providers=frozenset({"openai_responses"}),
        allowed_model_ids=frozenset({"gpt-5.6"}),
        valid_from=NOW - timedelta(days=1),
        valid_until=NOW + timedelta(days=30),
        max_output_tokens_per_request=2000,
        max_total_tokens_per_request=10000,
        monthly_provider_cost_limit_microunits=100_000_000,
        monthly_billable_limit_microunits=150_000_000,
        chargeback_multiplier_basis_points=15000,
        approved_by_principal_ref="user:platform-owner",
        approver_role=PlatformRole.PLATFORM_ADMIN,
        admin_approval_ref="approval://token/42",
    )


def _rate_card() -> ProviderRateCard:
    return ProviderRateCard(
        rate_card_ref="rate-card:openai:gpt-5.6:2026-08",
        provider="openai_responses",
        model_id="gpt-5.6",
        currency="USD",
        input_cost_microunits_per_million_tokens=2_000_000,
        output_cost_microunits_per_million_tokens=8_000_000,
        effective_from=NOW - timedelta(days=1),
        effective_until=NOW + timedelta(days=30),
        approved_by_principal_ref="user:platform-owner",
        approver_role=PlatformRole.PLATFORM_ADMIN,
        admin_approval_ref="approval://rate-card/openai",
    )


def test_production_runtime_exposes_only_governed_user_entrypoint_and_denies_ungranted_network():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    runtime = build_production_engine_runtime(
        registrations=(_frontier(),),
        grants=(),
        rate_cards=(_rate_card(),),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=lambda usage: None,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "provider-secret"},
    )

    assert runtime.raw_gateway_exposed is False
    assert not hasattr(runtime, "engine_gateway")
    with pytest.raises(EngineGatewayError, match="paid_token_active_platform_admin_grant_missing"):
        asyncio.run(
            runtime.invoke_primary(
                task=_task(),
                prompt="No admin grant should mean no provider request",
                context=_context(user="user:not-approved"),
            )
        )
    assert calls == []


def test_production_runtime_keeps_sensitive_unauthorized_external_processing_local_and_free():
    calls = []
    writes = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.host == "127.0.0.1":
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Local confidential answer"},
                    "prompt_eval_count": 10,
                    "eval_count": 4,
                },
            )
        raise AssertionError("frontier endpoint must not be called")

    runtime = build_production_engine_runtime(
        registrations=(_local(), _frontier()),
        grants=(),
        rate_cards=(),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=writes.append,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "provider-secret"},
    )

    result = asyncio.run(
        runtime.invoke_primary(
            task=_task(privacy=PrivacyLevel.CONFIDENTIAL),
            prompt="Sensitive company context",
            context=_context(),
        )
    )
    assert result.local_free_execution is True
    assert result.paid_usage is None
    assert result.engine_receipt.engine_id == "local"
    assert calls == ["http://127.0.0.1:11434/api/chat"]
    assert writes == []


def test_admin_granted_frontier_usage_is_metered_through_production_runtime():
    writes = []

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.openai.com"
        return httpx.Response(
            200,
            json={
                "id": "resp_prod_paid_1",
                "output": [
                    {"type": "message", "content": [{"type": "output_text", "text": "Approved answer"}]}
                ],
                "usage": {"input_tokens": 18, "output_tokens": 6},
            },
        )

    runtime = build_production_engine_runtime(
        registrations=(_frontier(),),
        grants=(_grant(),),
        rate_cards=(_rate_card(),),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=writes.append,
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "provider-secret"},
    )

    result = asyncio.run(
        runtime.invoke_primary(
            task=_task(),
            prompt="Use the explicitly approved frontier model",
            context=_context(),
        )
    )
    assert result.local_free_execution is False
    assert result.paid_usage is not None
    assert result.paid_usage.input_tokens == 18
    assert result.paid_usage.output_tokens == 6
    assert result.paid_usage.billing_account_ref == "billing:customer-a:user-42"
    assert writes == [result.paid_usage]
    serialized = result.model_dump_json()
    assert "provider-secret" not in serialized
    assert "Use the explicitly approved frontier model" not in serialized
