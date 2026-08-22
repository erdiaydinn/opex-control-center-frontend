from __future__ import annotations

import threading
from datetime import datetime, timezone

import pytest

from app.agent_budget_ledger import (
    AgentBudgetLedgerPort,
    BudgetAccount,
    BudgetMutationKind,
    BudgetTransaction,
    BudgetTransactionResult,
    BudgetVector,
)
from app.engine_gateway import (
    EngineEndpoint,
    EngineGatewayError,
    EngineInvocationReceipt,
    EngineProvider,
    RegisteredEngine,
)
from app.frontier3_certification_intelligence import FrontierCertificationDomain
from app.frontier_supremacy_intelligence import (
    EngineDomainBenchmark,
    SupremacyDomain,
    SupremacyRequest,
)
from app.governed_frontier_council_runtime import (
    FrontierCouncilBudgetBinding,
    GovernedFrontierCouncilSession,
    execute_governed_frontier_supremacy,
)
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
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
    PaidTokenGrantStatus,
    PaidTokenLedgerSnapshot,
    PlatformRole,
    ProviderRateCard,
)
from app.production_engine_runtime import ProductionEngineRuntime

NOW = datetime(2026, 8, 23, 0, 0, tzinfo=timezone.utc)
TENANT = "tenant-a"
COMPANY = "company-a"
USER = "user-a"
CYCLE = "2026-08"
CERT_REF = "certified-route://frontier-council-current"


class Admission:
    def __init__(self) -> None:
        self.allowed = {"openai", "anthropic", "gemini"}
        self.ref = CERT_REF

    def is_admitted(self, *, task, registration, requested_at, tenant_ref, company_ref):
        return (
            tenant_ref == TENANT
            and company_ref == COMPANY
            and registration.profile.engine_id in self.allowed
        )

    def receipt_ref(self, *, task, requested_at, tenant_ref, company_ref):
        return self.ref if tenant_ref == TENANT and company_ref == COMPANY else None


class FakeLowLevelGateway:
    def __init__(self, *, environ: dict[str, str] | None = None) -> None:
        self._environ = environ or {
            "OPENAI_KEY": "secret-a",
            "ANTHROPIC_KEY": "secret-b",
            "GEMINI_KEY": "secret-c",
        }
        self.calls: list[str] = []
        self.fail_engine: str | None = None

    async def _invoke_registered(self, *, task, prompt, plan, registration):
        engine_id = registration.profile.engine_id
        self.calls.append(engine_id)
        if self.fail_engine == engine_id:
            raise EngineGatewayError("simulated_provider_transport_failure")
        verifier = "FINAL VERIFIER" in prompt or "SECOND-PASS FINAL VERIFIER" in prompt
        text = "VERDICT: PASS\nverified" if verifier else f"answer from {engine_id}"
        return EngineInvocationReceipt(
            task_id=task.task_id,
            engine_id=engine_id,
            provider=registration.endpoint.provider,
            model_id=registration.endpoint.model_id,
            output_text=text,
            input_tokens=10,
            output_tokens=5,
            provider_response_id=f"response-{len(self.calls)}",
            external_processing=True,
            routing_plan=plan,
        )


class AtomicBudgetPort(AgentBudgetLedgerPort):
    def __init__(self, *, amount: int = 1_000_000) -> None:
        self.account = BudgetAccount(
            account_id="budget://frontier",
            tenant_id=TENANT,
            root_account_id="budget://frontier",
            allocation=BudgetVector(
                tokens=amount,
                cost_units=amount,
                wall_time_seconds=amount,
                tool_calls=amount,
                transitions=amount,
                descendants=amount,
            ),
            version=0,
        )
        self.reservations: dict[str, BudgetVector] = {}
        self.replays: dict[str, tuple[str, BudgetTransactionResult]] = {}
        self.lock = threading.Lock()

    def get_account(self, *, tenant_id: str, account_id: str):
        if tenant_id != TENANT or account_id != self.account.account_id:
            return None
        return self.account

    def transact(self, transaction: BudgetTransaction) -> BudgetTransactionResult:
        with self.lock:
            prior = self.replays.get(transaction.idempotency_key)
            if prior is not None:
                fingerprint, result = prior
                if fingerprint != transaction.request_fingerprint:
                    raise ValueError("agent_budget_idempotency_conflict")
                return result.model_copy(update={"replayed": True})
            mutation = transaction.mutations[0]
            if transaction.tenant_id != TENANT:
                raise ValueError("agent_budget_account_not_found")
            if mutation.account_id != self.account.account_id:
                raise ValueError("agent_budget_account_not_found")
            if mutation.expected_version != self.account.version:
                raise ValueError("agent_budget_version_conflict")
            ref = mutation.reservation_ref or ""
            changes = {"version": self.account.version + 1}
            held = self.reservations.get(ref)
            if mutation.kind is BudgetMutationKind.RESERVE:
                if not mutation.amount.fits_within(self.account.available()):
                    raise ValueError("agent_budget_insufficient")
                changes["reserved"] = self.account.reserved.plus(mutation.amount)
                self.reservations[ref] = mutation.amount
            elif mutation.kind is BudgetMutationKind.CONSUME:
                if held is None or not mutation.amount.fits_within(held):
                    raise ValueError("agent_budget_reservation_missing")
                changes["reserved"] = self.account.reserved.minus(mutation.amount)
                changes["consumed"] = self.account.consumed.plus(mutation.amount)
                self.reservations[ref] = held.minus(mutation.amount)
            elif mutation.kind is BudgetMutationKind.RELEASE:
                if held is None or not mutation.amount.fits_within(held):
                    raise ValueError("agent_budget_reservation_missing")
                if not mutation.amount.fits_within(
                    self.account.reserved.minus(self.account.unknown_effect_held)
                ):
                    raise ValueError("agent_budget_unknown_effect_release_forbidden")
                changes["reserved"] = self.account.reserved.minus(mutation.amount)
                self.reservations[ref] = held.minus(mutation.amount)
            elif mutation.kind is BudgetMutationKind.HOLD_UNKNOWN_EFFECT:
                if held is None or not mutation.amount.fits_within(held):
                    raise ValueError("agent_budget_reservation_missing")
                changes["unknown_effect_held"] = self.account.unknown_effect_held.plus(
                    mutation.amount
                )
            else:
                raise AssertionError(f"unexpected budget mutation: {mutation.kind}")
            self.account = self.account.model_copy(update=changes)
            result = BudgetTransactionResult(
                transaction_id=transaction.transaction_id,
                idempotency_key=transaction.idempotency_key,
                request_fingerprint=transaction.request_fingerprint,
                accounts=(self.account,),
            )
            self.replays[transaction.idempotency_key] = (
                transaction.request_fingerprint,
                result,
            )
            return result


def registration(
    engine_id: str,
    provider: EngineProvider,
    provider_key: str,
    score: float,
    secret_ref: str,
) -> RegisteredEngine:
    host = {
        EngineProvider.OPENAI_RESPONSES: "https://api.openai.com",
        EngineProvider.ANTHROPIC_MESSAGES: "https://api.anthropic.com",
        EngineProvider.GEMINI_GENERATE_CONTENT: "https://generativelanguage.googleapis.com",
    }[provider]
    return RegisteredEngine(
        profile=IntelligenceEngine(
            engine_id=engine_id,
            engine_class=EngineClass.FRONTIER,
            local_processing=False,
            maximum_privacy=PrivacyLevel.PUBLIC,
            maximum_risk=TaskRisk.CRITICAL,
            exact_adapter_verified=True,
            production_enabled=True,
            benchmark_score=score,
            benchmark_evidence_ref=f"benchmark://{engine_id}",
            independent_provider_key=provider_key,
            runtime_release_ref=f"release://{engine_id}/2026-08",
        ),
        endpoint=EngineEndpoint(
            engine_id=engine_id,
            provider=provider,
            model_id=f"model-{engine_id}",
            base_url=host,
            secret_ref=secret_ref,
            max_output_tokens=256,
            timeout_seconds=30,
        ),
    )


def registrations() -> tuple[RegisteredEngine, ...]:
    return (
        registration("openai", EngineProvider.OPENAI_RESPONSES, "provider-openai", .99, "env:OPENAI_KEY"),
        registration("anthropic", EngineProvider.ANTHROPIC_MESSAGES, "provider-anthropic", .98, "env:ANTHROPIC_KEY"),
        registration("gemini", EngineProvider.GEMINI_GENERATE_CONTENT, "provider-gemini", .97, "env:GEMINI_KEY"),
    )


def grants(regs: tuple[RegisteredEngine, ...]) -> tuple[PaidTokenGrant, ...]:
    return tuple(
        PaidTokenGrant(
            grant_id=f"grant-{item.profile.engine_id}",
            subject_user_ref=USER,
            tenant_ref=TENANT,
            billing_account_ref=f"billing-{item.profile.engine_id}",
            allowed_providers=frozenset({item.endpoint.provider.value}),
            allowed_model_ids=frozenset({item.endpoint.model_id}),
            valid_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            valid_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
            status=PaidTokenGrantStatus.ACTIVE,
            max_output_tokens_per_request=512,
            max_total_tokens_per_request=2_000,
            monthly_provider_cost_limit_microunits=10_000_000,
            monthly_billable_limit_microunits=10_000_000,
            approved_by_principal_ref="platform-admin",
            approver_role=PlatformRole.PLATFORM_ADMIN,
            admin_approval_ref=f"approval://{item.profile.engine_id}",
        )
        for item in regs
    )


def rate_cards(regs: tuple[RegisteredEngine, ...]) -> tuple[ProviderRateCard, ...]:
    return tuple(
        ProviderRateCard(
            rate_card_ref=f"rate://{item.profile.engine_id}",
            provider=item.endpoint.provider.value,
            model_id=item.endpoint.model_id,
            currency="USD",
            input_cost_microunits_per_million_tokens=1_000_000,
            output_cost_microunits_per_million_tokens=2_000_000,
            effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc),
            effective_until=datetime(2027, 1, 1, tzinfo=timezone.utc),
            approved_by_principal_ref="platform-admin",
            approver_role=PlatformRole.PLATFORM_ADMIN,
            admin_approval_ref=f"rate-approval://{item.profile.engine_id}",
        )
        for item in regs
    )


def task() -> IntelligenceTask:
    return IntelligenceTask(
        task_id="frontier-production-council",
        complexity=TaskComplexity.EXTREME,
        risk=TaskRisk.CRITICAL,
        privacy=PrivacyLevel.PUBLIC,
        external_processing_authorized=True,
        requires_independent_critique=True,
        certification_domain=FrontierCertificationDomain.GENERAL_REASONING,
        requires_fresh_certification=True,
    )


def request() -> SupremacyRequest:
    return SupremacyRequest(
        domain=SupremacyDomain.GENERAL_REASONING,
        task=task(),
        problem="Solve a production critical reasoning problem with independent falsification.",
        benchmarks=tuple(
            EngineDomainBenchmark(
                engine_id=item.profile.engine_id,
                provider_key=item.profile.independent_provider_key,
                domain=SupremacyDomain.GENERAL_REASONING,
                normalized_frontier_score=1.0,
                sample_count=200,
                measured_at=NOW,
                evidence_ref=f"evidence://{item.profile.engine_id}",
                independent_evaluator=True,
            )
            for item in registrations()
        ),
    )


def context() -> PaidTokenExecutionContext:
    return PaidTokenExecutionContext(
        subject_user_ref=USER,
        tenant_ref=TENANT,
        company_ref=COMPANY,
        billing_cycle_ref=CYCLE,
        requested_at=NOW,
    )


def binding(session: str = "frontier-session-1") -> FrontierCouncilBudgetBinding:
    return FrontierCouncilBudgetBinding(
        session_ref=session,
        tenant_id=TENANT,
        company_id=COMPANY,
        root_account_id="budget://frontier",
        account_id="budget://frontier",
    )


def governed(*, environ=None, budget_amount=1_000_000):
    regs = registrations()
    low = FakeLowLevelGateway(environ=environ)
    usage = []
    grant_set = grants(regs)
    billing_by_engine = {
        item.profile.engine_id: f"billing-{item.profile.engine_id}" for item in regs
    }

    def ledger_reader(ctx, engine_id):
        return PaidTokenLedgerSnapshot(
            subject_user_ref=ctx.subject_user_ref,
            tenant_ref=ctx.tenant_ref,
            billing_account_ref=billing_by_engine[engine_id],
            billing_cycle_ref=ctx.billing_cycle_ref,
        )

    gateway = AdminGovernedEngineGateway(
        engine_gateway=low,
        registrations=regs,
        grants=grant_set,
        rate_cards=rate_cards(regs),
        ledger_reader=ledger_reader,
        usage_writer=usage.append,
        candidate_admission=Admission(),
    )
    return gateway, low, usage, AtomicBudgetPort(amount=budget_amount)


@pytest.mark.asyncio
async def test_production_governed_council_reserves_before_calls_and_settles_actual_usage():
    gateway, low, usage, budget = governed()
    result = await execute_governed_frontier_supremacy(
        gateway=gateway,
        request=request(),
        context=context(),
        budget_ledger=budget,
        budget=binding(),
        clock=lambda: NOW,
    )
    assert result.result.decision_ready is True
    assert len(result.result.selected_engine_ids) == 3
    assert len(low.calls) == 8
    assert len(usage) == 8
    assert result.runtime.finalized is True
    assert result.runtime.reserved_budget.tokens > result.runtime.consumed_budget.tokens
    assert result.runtime.consumed_budget.tokens == 8 * 15
    assert budget.account.reserved.is_zero()
    assert budget.account.unknown_effect_held.is_zero()
    assert not result.runtime.execution_authority_granted
    assert not result.runtime.company_truth_promoted


@pytest.mark.asyncio
async def test_missing_credential_holds_before_any_provider_call_or_budget_reservation():
    gateway, low, usage, budget = governed(
        environ={"OPENAI_KEY": "a", "ANTHROPIC_KEY": "b"}
    )
    result = await execute_governed_frontier_supremacy(
        gateway=gateway,
        request=request(),
        context=context(),
        budget_ledger=budget,
        budget=binding("missing-credential"),
        clock=lambda: NOW,
    )
    assert result.result.decision_ready is False
    assert low.calls == []
    assert usage == []
    assert budget.account.version == 0
    assert budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_insufficient_atomic_budget_holds_whole_council_before_first_provider():
    gateway, low, usage, budget = governed(budget_amount=1)
    result = await execute_governed_frontier_supremacy(
        gateway=gateway,
        request=request(),
        context=context(),
        budget_ledger=budget,
        budget=binding("insufficient-budget"),
        clock=lambda: NOW,
    )
    assert result.result.decision_ready is False
    assert any("frontier_council_budget_reservation_failed" in item for item in result.result.blockers)
    assert low.calls == []
    assert usage == []
    assert budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_certification_revocation_after_plan_blocks_before_provider_and_releases_budget():
    gateway, low, _, budget = governed()
    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context(),
        budget_ledger=budget,
        budget=binding("cert-revoked"),
        clock=lambda: NOW,
    )
    plan = session.plan(task())
    assert plan.execution_permitted
    gateway._candidate_admission.allowed.remove(plan.primary_engine_id)
    with pytest.raises(EngineGatewayError, match="certification_revoked_after_binding"):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    assert low.calls == []
    session.finalize()
    assert budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_registration_release_drift_after_plan_cannot_silently_reroute():
    gateway, low, _, budget = governed()
    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context(),
        budget_ledger=budget,
        budget=binding("registration-drift"),
        clock=lambda: NOW,
    )
    plan = session.plan(task())
    primary = plan.primary_engine_id
    current = gateway._registrations[primary]
    gateway._registrations[primary] = current.model_copy(
        update={
            "profile": current.profile.model_copy(
                update={"runtime_release_ref": "release://drifted"}
            )
        }
    )
    with pytest.raises(EngineGatewayError, match="engine_registration_drift"):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    assert low.calls == []
    session.finalize()
    assert budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_paid_grant_revocation_after_binding_blocks_before_provider_call():
    gateway, low, _, budget = governed()
    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context(),
        budget_ledger=budget,
        budget=binding("grant-revoked"),
        clock=lambda: NOW,
    )
    plan = session.plan(task())
    primary = plan.primary_engine_id
    gateway._grants = tuple(
        item.model_copy(update={"status": PaidTokenGrantStatus.REVOKED})
        if primary in item.allowed_model_ids or item.grant_id == f"grant-{primary}"
        else item
        for item in gateway._grants
    )
    with pytest.raises(EngineGatewayError, match="paid_authority_changed_after_binding"):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    assert low.calls == []
    session.finalize()
    assert budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_provider_failure_keeps_remaining_budget_in_unknown_effect_hold():
    gateway, low, usage, budget = governed()
    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context(),
        budget_ledger=budget,
        budget=binding("provider-failure"),
        clock=lambda: NOW,
    )
    plan = session.plan(task())
    low.fail_engine = plan.primary_engine_id
    with pytest.raises(EngineGatewayError, match="simulated_provider_transport_failure"):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    receipt = session.finalize()
    assert len(low.calls) == 1
    assert usage == []
    assert receipt.uncertain_effect_held is True
    assert not budget.account.unknown_effect_held.is_zero()
    assert not budget.account.reserved.is_zero()


@pytest.mark.asyncio
async def test_bound_task_change_and_call_envelope_fail_closed():
    gateway, low, _, budget = governed()
    session = GovernedFrontierCouncilSession(
        gateway=gateway,
        context=context(),
        budget_ledger=budget,
        budget=binding("envelope"),
        clock=lambda: NOW,
    )
    session.plan(task())
    changed = task().model_copy(update={"task_id": "different-task"})
    with pytest.raises(EngineGatewayError, match="task_changed_after_binding"):
        await session.invoke_primary(task=changed, prompt="critical prompt")
    assert low.calls == []
    for _ in range(3):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    with pytest.raises(EngineGatewayError, match="primary_call_envelope_exceeded"):
        await session.invoke_primary(task=task(), prompt="critical prompt")
    session.finalize()


@pytest.mark.asyncio
async def test_production_runtime_refuses_frontier_council_without_budget_ledger():
    gateway, low, _, _ = governed()
    runtime = ProductionEngineRuntime(_governed_gateway=gateway)
    with pytest.raises(EngineGatewayError, match="budget_ledger_required"):
        await runtime.execute_frontier_council(
            request=request(),
            context=context(),
            budget=binding("missing-ledger"),
        )
    assert runtime.raw_gateway_exposed is False
    assert runtime.governed_frontier_council_enabled is False
    assert low.calls == []


def test_cross_company_budget_binding_is_rejected_at_session_boundary():
    gateway, _, _, budget = governed()
    with pytest.raises(ValueError, match="budget_company_mismatch"):
        GovernedFrontierCouncilSession(
            gateway=gateway,
            context=context(),
            budget_ledger=budget,
            budget=binding().model_copy(update={"company_id": "company-b"}),
            clock=lambda: NOW,
        )
