import asyncio
from datetime import datetime, timedelta, timezone

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
from app.paid_token_engine_gateway import (
    AdminGovernedEngineGateway,
    PaidTokenExecutionContext,
)
from app.paid_token_governance import (
    PaidTokenGrant,
    PaidTokenLedgerSnapshot,
    PlatformRole,
    ProviderRateCard,
)

NOW = datetime(2026, 8, 18, 9, 30, tzinfo=timezone.utc)


def _profile(engine_id, *, local, score):
    return IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.LOCAL if local else EngineClass.FRONTIER,
        modalities=(Modality.TEXT,),
        supports_long_horizon=True,
        local_processing=local,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.MEDIUM,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"eval://{engine_id}",
        independent_provider_key=engine_id,
    )


def _frontier():
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


def _local():
    return RegisteredEngine(
        profile=_profile("local", local=True, score=0.80),
        endpoint=EngineEndpoint(
            engine_id="local",
            provider=EngineProvider.OLLAMA,
            model_id="eay-local",
            base_url="http://127.0.0.1:11434",
        ),
    )


def _task(*, confidential=False):
    return IntelligenceTask(
        task_id="paid-token-test",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.CONFIDENTIAL if confidential else PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
    )


def _context(user="user:42"):
    return PaidTokenExecutionContext(
        subject_user_ref=user,
        tenant_ref="tenant:customer-a",
        billing_cycle_ref="2026-08",
        requested_at=NOW,
    )


def _grant():
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


def _card():
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


def test_user_without_admin_grant_cannot_trigger_frontier_network_call():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    registration = _frontier()
    base = EngineGateway(
        [registration],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "secret"},
    )
    gateway = AdminGovernedEngineGateway(
        engine_gateway=base,
        registrations=(registration,),
        grants=(),
        rate_cards=(_card(),),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=lambda usage: None,
    )

    with pytest.raises(EngineGatewayError, match="paid_token_active_platform_admin_grant_missing"):
        asyncio.run(
            gateway.invoke_primary(
                task=_task(),
                prompt="Do expensive reasoning",
                context=_context(user="user:not-approved"),
            )
        )
    assert calls == []


def test_admin_granted_frontier_call_is_metered_and_written_to_chargeback_ledger():
    writes = []

    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "resp_paid_1",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "Paid answer"}],
                    }
                ],
                "usage": {"input_tokens": 20, "output_tokens": 10},
            },
        )

    registration = _frontier()
    base = EngineGateway(
        [registration],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "secret"},
    )
    gateway = AdminGovernedEngineGateway(
        engine_gateway=base,
        registrations=(registration,),
        grants=(_grant(),),
        rate_cards=(_card(),),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=writes.append,
    )

    result = asyncio.run(
        gateway.invoke_primary(
            task=_task(),
            prompt="Use the approved frontier model",
            context=_context(),
        )
    )

    assert result.engine_receipt.output_text == "Paid answer"
    assert result.paid_usage is not None
    assert result.paid_usage.input_tokens == 20
    assert result.paid_usage.output_tokens == 10
    assert result.paid_usage.billing_account_ref == "billing:customer-a:user-42"
    assert result.paid_usage.billable_microunits > result.paid_usage.provider_cost_microunits
    assert writes == [result.paid_usage]
    serialized = result.model_dump_json()
    assert result.engine_receipt.secret_retained is False
    assert result.paid_usage.provider_secret_retained is False
    assert "sk-test-super-secret" not in serialized
    assert "Use the approved frontier model" not in serialized


def test_executable_local_plan_wins_before_frontier_grant_or_ledger_is_consulted():
    calls = []
    ledger_reads = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if request.url.path == "/api/chat":
            return httpx.Response(
                200,
                json={
                    "message": {"content": "Local first answer"},
                    "prompt_eval_count": 14,
                    "eval_count": 5,
                },
            )
        return httpx.Response(500)

    def read_ledger(context, engine_id):
        ledger_reads.append((context.subject_user_ref, engine_id))
        raise AssertionError("frontier ledger must not be read while local plan is executable")

    local = _local()
    frontier = _frontier()
    base = EngineGateway(
        [local, frontier],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "secret"},
    )
    gateway = AdminGovernedEngineGateway(
        engine_gateway=base,
        registrations=(local, frontier),
        grants=(_grant(),),
        rate_cards=(_card(),),
        ledger_reader=read_ledger,
        usage_writer=lambda usage: (_ for _ in ()).throw(
            AssertionError("local execution must not create paid usage")
        ),
    )

    result = asyncio.run(
        gateway.invoke_primary(
            task=_task(),
            prompt="Prefer zero paid tokens when local is sufficient",
            context=_context(),
        )
    )

    assert result.local_free_execution is True
    assert result.paid_usage is None
    assert result.engine_receipt.engine_id == "local"
    assert ledger_reads == []
    assert calls == ["http://127.0.0.1:11434/api/chat"]


def test_budget_exhausted_frontier_is_filtered_before_any_provider_network_call():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(500)

    registration = _frontier()
    base = EngineGateway(
        [registration],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "secret"},
    )
    exhausted = PaidTokenLedgerSnapshot(
        subject_user_ref="user:42",
        tenant_ref="tenant:customer-a",
        billing_account_ref="billing:customer-a:user-42",
        billing_cycle_ref="2026-08",
        provider_cost_microunits=100_000_000,
        billable_microunits=150_000_000,
    )
    gateway = AdminGovernedEngineGateway(
        engine_gateway=base,
        registrations=(registration,),
        grants=(_grant(),),
        rate_cards=(_card(),),
        ledger_reader=lambda context, engine_id: exhausted,
        usage_writer=lambda usage: None,
    )

    with pytest.raises(EngineGatewayError, match="paid_token_monthly_provider_cost_limit_exceeded"):
        asyncio.run(
            gateway.invoke_primary(
                task=_task(),
                prompt="This must be rejected before provider I/O",
                context=_context(),
            )
        )
    assert calls == []


def test_sensitive_task_without_external_processing_authorization_stays_local_and_free():
    calls = []

    async def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(
            200,
            json={
                "message": {"content": "Local answer"},
                "prompt_eval_count": 12,
                "eval_count": 4,
            },
        )

    local = _local()
    frontier = _frontier()
    base = EngineGateway(
        [local, frontier],
        transport_factory=lambda endpoint: httpx.MockTransport(handler),
        environ={"OPENAI_API_KEY": "secret"},
    )
    gateway = AdminGovernedEngineGateway(
        engine_gateway=base,
        registrations=(local, frontier),
        grants=(),
        rate_cards=(),
        ledger_reader=lambda context, engine_id: None,
        usage_writer=lambda usage: (_ for _ in ()).throw(AssertionError("local must not bill")),
    )

    result = asyncio.run(
        gateway.invoke_primary(
            task=_task(confidential=True),
            prompt="Sensitive company context",
            context=_context(),
        )
    )

    assert result.local_free_execution is True
    assert result.paid_usage is None
    assert result.engine_receipt.engine_id == "local"
    assert calls == ["http://127.0.0.1:11434/api/chat"]
