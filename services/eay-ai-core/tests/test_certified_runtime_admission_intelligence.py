from datetime import UTC, datetime

import pytest

from app.engine_gateway import EngineEndpoint, EngineGateway, EngineGatewayError, EngineProvider, RegisteredEngine
from app.frontier3_certification_intelligence import FrontierCertificationDomain
from app.intelligence_router import (
    EngineClass, IntelligenceEngine, IntelligenceTask, PrivacyLevel,
    TaskComplexity, TaskRisk, route_intelligence,
)
from app.local_first_engine_runtime import LocalFirstProductionRuntime
from app.local_model_pool import (
    CommercialUseStatus, LocalCapability, LocalModelCatalog, LocalModelCatalogEntry,
    LocalModelDeployment, LocalModelTask,
)
from app.paid_token_engine_gateway import AdminGovernedEngineGateway, PaidTokenExecutionContext

NOW = datetime(2026, 8, 22, 18, tzinfo=UTC)
DOMAIN = FrontierCertificationDomain.GENERAL_REASONING


def profile(engine_id: str, provider: str, *, score: float, local: bool = False):
    return IntelligenceEngine(engine_id=engine_id,
        engine_class=EngineClass.LOCAL if local else EngineClass.FRONTIER,
        local_processing=local, production_enabled=True, exact_adapter_verified=True,
        maximum_privacy=PrivacyLevel.RESTRICTED if local else PrivacyLevel.PUBLIC,
        maximum_risk=TaskRisk.CRITICAL, benchmark_score=score,
        benchmark_evidence_ref=f"legacy://{engine_id}", independent_provider_key=provider)


def strict_task(*, critical=False):
    return IntelligenceTask(task_id="strict", complexity=TaskComplexity.EXTREME if critical else TaskComplexity.HARD,
        risk=TaskRisk.CRITICAL if critical else TaskRisk.HIGH, privacy=PrivacyLevel.PUBLIC,
        requires_independent_critique=critical, certification_domain=DOMAIN,
        requires_fresh_certification=True)


def context():
    return PaidTokenExecutionContext(subject_user_ref="user-a", tenant_ref="tenant-a",
        company_ref="company-a", billing_cycle_ref="2026-08", requested_at=NOW)


def registration(engine_id="frontier-a", provider="provider-a", score=1.0):
    return RegisteredEngine(profile=profile(engine_id, provider, score=score),
        endpoint=EngineEndpoint(engine_id=engine_id, provider=EngineProvider.OPENAI_RESPONSES,
            model_id=f"model-{engine_id}", base_url="https://api.openai.com",
            secret_ref="env:OPENAI_API_KEY"))


class Admission:
    def __init__(self, allowed: set[str]): self.allowed = allowed
    def is_admitted(self, *, registration, **_): return registration.profile.engine_id in self.allowed
    def receipt_ref(self, **_): return "capability-cert://fresh"


def test_strict_router_requires_fresh_admission_receipt():
    plan = route_intelligence(strict_task(), [profile("old", "p1", score=1.0)])
    assert not plan.execution_permitted
    assert plan.blockers == ("fresh_capability_certification_admission_missing",)


def test_legacy_perfect_score_cannot_beat_fresh_lower_score():
    engines = [profile("legacy", "p1", score=1.0), profile("fresh", "p2", score=.91)]
    plan = route_intelligence(strict_task(), engines, certified_engine_ids={"fresh"},
        certification_admission_ref="capability-cert://fresh")
    assert plan.execution_permitted
    assert plan.primary_engine_id == "fresh"


def test_critical_council_cannot_use_uncertified_provider_for_quorum():
    engines = [profile("fresh", "p1", score=.95), profile("stale", "p2", score=1.0)]
    plan = route_intelligence(strict_task(critical=True), engines, certified_engine_ids={"fresh"},
        certification_admission_ref="capability-cert://fresh")
    assert not plan.execution_permitted
    assert plan.critic_engine_ids == ()
    assert "independent_critic_unavailable" in plan.blockers
    assert "council_provider_diversity_insufficient" in plan.blockers


@pytest.mark.asyncio
async def test_unadmitted_paid_frontier_hits_no_ledger_or_provider_transport():
    reg = registration()
    ledger_calls, transport_calls, usage_calls = [], [], []
    gateway = AdminGovernedEngineGateway(engine_gateway=EngineGateway([reg],
            transport_factory=lambda endpoint: transport_calls.append(endpoint.engine_id)),
        registrations=(reg,), grants=(), rate_cards=(),
        ledger_reader=lambda ctx, engine: ledger_calls.append(engine),
        usage_writer=lambda receipt: usage_calls.append(receipt), candidate_admission=Admission(set()))
    with pytest.raises(EngineGatewayError, match="routing_plan_not_executable"):
        await gateway.invoke_primary(task=strict_task(), prompt="analyze", context=context())
    assert ledger_calls == []
    assert transport_calls == []
    assert usage_calls == []


def test_fresh_certification_requires_explicit_domain():
    with pytest.raises(ValueError, match="certification_domain"):
        IntelligenceTask(task_id="bad", complexity=TaskComplexity.HARD, risk=TaskRisk.HIGH,
            privacy=PrivacyLevel.PUBLIC, requires_fresh_certification=True)


def test_local_first_filters_uncertified_local_before_efficiency_or_score_selection():
    catalog = LocalModelCatalog(version=1, models=(LocalModelCatalogEntry(model_family="family",
        recommended_runtime="ollama", license="Apache-2.0",
        commercial_use_status=CommercialUseStatus.PERMISSIVE_LICENSE_REVIEWED,
        capabilities=frozenset({LocalCapability.TEXT, LocalCapability.REASONING}),
        preferred_tasks=frozenset({"reasoning"}), supported_languages=frozenset({"en"}),
        production_candidate=True),))
    deployments = tuple(LocalModelDeployment(deployment_id=e, model_family="family", model_id=f"model-{e}",
        runtime="ollama", endpoint_ref=f"ollama://{e}", enabled=True, runtime_reachable=True,
        benchmark_score=score, benchmark_evidence_ref=f"bench://{e}",
        observed_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.REASONING}))
        for e, score in (("legacy-local", 1.0), ("fresh-local", .91)))
    regs = tuple(RegisteredEngine(profile=profile(e, f"provider-{e}", score=score, local=True),
        endpoint=EngineEndpoint(engine_id=e, provider=EngineProvider.OLLAMA, model_id=f"model-{e}",
            base_url="http://localhost:11434")) for e, score in (("legacy-local", 1.0), ("fresh-local", .91)))
    runtime = LocalFirstProductionRuntime(catalog=catalog, deployments=deployments,
        local_registrations=regs, frontier_runtime=object(), candidate_admission=Admission({"fresh-local"}))
    selected = runtime._select_local(local_task=LocalModelTask(task_ref="l", task_class="reasoning",
        required_capabilities=frozenset({LocalCapability.TEXT, LocalCapability.REASONING}),
        language_code="en"), task=strict_task(), context=context())
    assert selected.deployment_id == "fresh-local"
