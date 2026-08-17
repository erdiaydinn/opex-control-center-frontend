import pytest

from app.intelligence_router import (
    EngineClass,
    IntelligenceEngine,
    IntelligenceTask,
    Modality,
    PrivacyLevel,
    TaskComplexity,
    TaskRisk,
    route_intelligence,
)


def _engine(**overrides):
    payload = dict(
        engine_id="local-strong",
        engine_class=EngineClass.LOCAL,
        modalities=(Modality.TEXT, Modality.CODE),
        supports_tools=True,
        supports_long_horizon=True,
        supports_parallel_delegation=True,
        local_processing=True,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        exact_adapter_verified=True,
        production_enabled=True,
        benchmark_score=0.80,
        benchmark_evidence_ref="eval://local-strong/2026-08",
        independent_provider_key="local-runtime",
    )
    payload.update(overrides)
    return IntelligenceEngine(**payload)


def _task(**overrides):
    payload = dict(
        task_id="executive-analysis",
        complexity=TaskComplexity.HARD,
        risk=TaskRisk.MEDIUM,
        privacy=PrivacyLevel.INTERNAL,
        modalities=(Modality.TEXT,),
        requires_tools=True,
    )
    payload.update(overrides)
    return IntelligenceTask(**payload)


def _frontier(**overrides):
    payload = dict(
        engine_id="frontier",
        engine_class=EngineClass.FRONTIER,
        local_processing=False,
        maximum_privacy=PrivacyLevel.RESTRICTED,
        maximum_risk=TaskRisk.CRITICAL,
        benchmark_score=0.99,
        benchmark_evidence_ref="eval://frontier",
        independent_provider_key="frontier-provider",
    )
    payload.update(overrides)
    return _engine(**payload)


def test_restricted_company_data_stays_local_without_external_authorization():
    plan = route_intelligence(
        _task(privacy=PrivacyLevel.RESTRICTED),
        [_frontier(), _engine()],
    )

    assert plan.primary_engine_id == "local-strong"
    assert plan.execution_permitted is True


def test_confidential_company_data_stays_local_without_external_authorization():
    plan = route_intelligence(
        _task(privacy=PrivacyLevel.CONFIDENTIAL),
        [_frontier(), _engine()],
    )

    assert plan.primary_engine_id == "local-strong"
    assert plan.execution_permitted is True


def test_explicit_external_processing_authorization_can_unlock_frontier_for_confidential_task():
    plan = route_intelligence(
        _task(
            privacy=PrivacyLevel.CONFIDENTIAL,
            external_processing_authorized=True,
        ),
        [_frontier(), _engine()],
    )

    assert plan.primary_engine_id == "frontier"
    assert plan.execution_permitted is True


def test_high_risk_task_requires_independent_critic():
    primary = _engine(engine_id="primary", benchmark_score=0.95)
    same_provider = _engine(
        engine_id="same-provider",
        benchmark_score=0.90,
        independent_provider_key="local-runtime",
    )
    plan = route_intelligence(
        _task(risk=TaskRisk.HIGH),
        [primary, same_provider],
    )

    assert plan.execution_permitted is False
    assert "independent_critic_unavailable" in plan.blockers


def test_high_risk_task_uses_independent_critic_when_available():
    primary = _engine(engine_id="primary", benchmark_score=0.95)
    critic = _engine(
        engine_id="critic",
        engine_class=EngineClass.FRONTIER,
        local_processing=False,
        maximum_privacy=PrivacyLevel.INTERNAL,
        benchmark_score=0.90,
        benchmark_evidence_ref="eval://critic",
        independent_provider_key="frontier-provider",
    )
    plan = route_intelligence(_task(risk=TaskRisk.HIGH), [primary, critic])

    assert plan.primary_engine_id == "primary"
    assert plan.critic_engine_ids == ("critic",)
    assert plan.execution_permitted is True


def test_unverified_or_disabled_engines_never_route():
    plan = route_intelligence(
        _task(),
        [
            _engine(exact_adapter_verified=False),
            _engine(engine_id="disabled", production_enabled=False),
        ],
    )

    assert plan.execution_permitted is False
    assert plan.primary_engine_id is None
    assert plan.blockers == ("no_verified_engine_satisfies_task_boundary",)


def test_multimodal_task_requires_matching_engine_capability():
    text_only = _engine(modalities=(Modality.TEXT,))
    vision = _engine(
        engine_id="vision",
        engine_class=EngineClass.SPECIALIST,
        modalities=(Modality.TEXT, Modality.IMAGE, Modality.SCREEN),
        benchmark_score=0.85,
        benchmark_evidence_ref="eval://vision",
        independent_provider_key="vision-provider",
    )
    plan = route_intelligence(
        _task(modalities=(Modality.TEXT, Modality.SCREEN)),
        [text_only, vision],
    )

    assert plan.primary_engine_id == "vision"


def test_benchmark_score_without_evidence_is_rejected():
    with pytest.raises(ValueError, match="engine_benchmark_score_requires_evidence"):
        _engine(benchmark_evidence_ref=None)
