from app.frontier3_certification_intelligence import FrontierCertificationDomain
from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
    route_intelligence,
)

DOMAIN = FrontierCertificationDomain.GENERAL_REASONING
CERT_REF = "capability-cert://fresh-certified-snapshot"


def engine(engine_id: str, provider: str, score: float) -> IntelligenceEngine:
    return IntelligenceEngine(
        engine_id=engine_id,
        engine_class=EngineClass.FRONTIER,
        local_processing=False,
        maximum_privacy=PrivacyLevel.PUBLIC,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=score,
        benchmark_evidence_ref=f"benchmark://{engine_id}",
        independent_provider_key=provider,
    )


def critical_task() -> IntelligenceTask:
    return IntelligenceTask(
        task_id="critical-frontier-council",
        complexity=TaskComplexity.EXTREME,
        risk=TaskRisk.CRITICAL,
        privacy=PrivacyLevel.PUBLIC,
        requires_independent_critique=True,
        certification_domain=DOMAIN,
        requires_fresh_certification=True,
    )


def test_two_certified_provider_families_cannot_execute_critical_council():
    engines = [
        engine("primary", "provider-a", .98),
        engine("critic-one", "provider-b", .97),
    ]
    plan = route_intelligence(
        critical_task(),
        engines,
        certified_engine_ids={"primary", "critic-one"},
        certification_admission_ref=CERT_REF,
    )

    assert plan.primary_engine_id == "primary"
    assert plan.critic_engine_ids == ("critic-one",)
    assert not plan.execution_permitted
    assert "council_independent_critics_insufficient" in plan.blockers
    assert "council_provider_diversity_insufficient" in plan.blockers


def test_three_certified_provider_families_execute_bounded_critical_council():
    engines = [
        engine("primary", "provider-a", .98),
        engine("critic-one", "provider-b", .97),
        engine("critic-two", "provider-c", .96),
    ]
    plan = route_intelligence(
        critical_task(),
        engines,
        certified_engine_ids={"primary", "critic-one", "critic-two"},
        certification_admission_ref=CERT_REF,
    )

    assert plan.primary_engine_id == "primary"
    assert plan.critic_engine_ids == ("critic-one", "critic-two")
    assert plan.execution_permitted
    assert plan.blockers == ()
    assert plan.certification_admission_ref == CERT_REF
    assert not plan.external_side_effects_authorized


def test_duplicate_provider_family_cannot_fake_three_way_council():
    engines = [
        engine("primary", "provider-a", .99),
        engine("same-family", "provider-a", .985),
        engine("critic-one", "provider-b", .98),
        engine("critic-two-same-family", "provider-b", .97),
    ]
    plan = route_intelligence(
        critical_task(),
        engines,
        certified_engine_ids={item.engine_id for item in engines},
        certification_admission_ref=CERT_REF,
    )

    assert not plan.execution_permitted
    assert plan.critic_engine_ids == ("critic-one",)
    assert "council_independent_critics_insufficient" in plan.blockers
    assert "council_provider_diversity_insufficient" in plan.blockers


def test_uncertified_third_provider_cannot_complete_critical_quorum():
    engines = [
        engine("primary", "provider-a", .98),
        engine("critic-one", "provider-b", .97),
        engine("uncertified-third", "provider-c", 1.0),
    ]
    plan = route_intelligence(
        critical_task(),
        engines,
        certified_engine_ids={"primary", "critic-one"},
        certification_admission_ref=CERT_REF,
    )

    assert not plan.execution_permitted
    assert "uncertified-third" not in plan.critic_engine_ids
    assert "council_provider_diversity_insufficient" in plan.blockers
