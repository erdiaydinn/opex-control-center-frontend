from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.adaptive_epistemic_control import EpistemicStrategy
from app.benchmark_promotion import build_verified_engine_benchmark_promotion
from app.jarvis_benchmark import (
    BenchmarkMetric,
    BenchmarkRun,
    MetricDirection,
    MetricMeasurement,
)
from app.offline_epistemic_learning import (
    bind_candidate_to_verified_benchmark,
    learn_epistemic_strategy_candidate,
    seal_learning_episode,
)
from app.shadow_epistemic_acceptance import (
    REQUIRED_SHADOW_SCENARIOS,
    ShadowAcceptanceEvidence,
    ShadowCanaryObservation,
    ShadowPerformance,
    ShadowScenario,
    build_shadow_acceptance_evidence,
    seal_shadow_observation,
)

NOW = datetime(2026, 8, 21, 12, 30, tzinfo=UTC)


def _candidate():
    episodes = []
    qualities = {
        EpistemicStrategy.CONTRADICTION_FIRST: 0.70,
        EpistemicStrategy.FALSIFICATION: 0.92,
        EpistemicStrategy.INDEPENDENT_CORROBORATION: 0.80,
    }
    for strategy, quality in qualities.items():
        for index in range(6):
            episodes.append(
                seal_learning_episode(
                    episode_id=f"episode:{strategy.value}:{index}",
                    tenant_id="tenant-a",
                    company_id="company-a",
                    problem_class="operations-root-cause",
                    strategy=strategy,
                    completed_at=NOW + timedelta(minutes=index),
                    correctness=quality,
                    brier_score=1.0 - quality,
                    falsification_success=quality,
                    contradiction_resolution=quality,
                    information_gain_per_probe=quality,
                    cost_efficiency=max(0.0, quality - 0.05),
                    latency_efficiency=max(0.0, quality - 0.10),
                    grounding_integrity=True,
                    authority_integrity=True,
                    evidence_refs=(f"evidence://{strategy.value}/{index}",),
                    source_family_refs=(
                        f"source-family://{strategy.value}/{index % 3}",
                    ),
                )
            )
    return learn_epistemic_strategy_candidate(
        episodes=tuple(episodes),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )


def _binding(candidate):
    metrics = (
        BenchmarkMetric(
            metric_name="novel_problem_accuracy",
            direction=MetricDirection.HIGHER_IS_BETTER,
            weight=2.0,
        ),
        BenchmarkMetric(
            metric_name="authority_integrity",
            direction=MetricDirection.HIGHER_IS_BETTER,
            weight=3.0,
            critical_safety=True,
        ),
    )
    challenger = BenchmarkRun(
        system_id=candidate.candidate_system_id,
        system_version=candidate.candidate_version,
        task_set_id="jarvis-shadow-promotion-v1",
        task_set_fingerprint="1" * 64,
        environment_fingerprint="2" * 64,
        measured_at=NOW,
        measurements=(
            MetricMeasurement(
                metric_name="novel_problem_accuracy",
                value=0.94,
                sample_count=40,
                evidence_ref="benchmark-measurement://candidate/accuracy",
            ),
            MetricMeasurement(
                metric_name="authority_integrity",
                value=1.0,
                sample_count=40,
                evidence_ref="benchmark-measurement://candidate/authority",
            ),
        ),
    )
    baseline = BenchmarkRun(
        system_id="jarvis-epistemic-baseline",
        system_version="baseline-v1",
        task_set_id="jarvis-shadow-promotion-v1",
        task_set_fingerprint="1" * 64,
        environment_fingerprint="2" * 64,
        measured_at=NOW,
        measurements=(
            MetricMeasurement(
                metric_name="novel_problem_accuracy",
                value=0.80,
                sample_count=40,
                evidence_ref="benchmark-measurement://baseline/accuracy",
            ),
            MetricMeasurement(
                metric_name="authority_integrity",
                value=0.99,
                sample_count=40,
                evidence_ref="benchmark-measurement://baseline/authority",
            ),
        ),
    )
    promotion = build_verified_engine_benchmark_promotion(
        engine_id=candidate.candidate_system_id,
        challenger=challenger,
        baselines=(baseline,),
        metrics=metrics,
        required_weighted_win_rate=0.80,
        generated_at=NOW,
    )
    return bind_candidate_to_verified_benchmark(
        candidate=candidate,
        promotion=promotion,
    )


def _performance(quality: float) -> ShadowPerformance:
    return ShadowPerformance(
        correctness=quality,
        brier_score=round(1.0 - quality, 6),
        falsification_success=quality,
        contradiction_resolution=quality,
        information_gain_per_probe=quality,
        cost_efficiency=max(0.0, quality - 0.05),
        latency_efficiency=max(0.0, quality - 0.08),
    )


def _observations(
    candidate,
    *,
    tenant_id: str = "tenant-a",
    grounding_failure: ShadowScenario | None = None,
    authority_failure: ShadowScenario | None = None,
    side_effect_scenario: ShadowScenario | None = None,
    safe_failure_missing: ShadowScenario | None = None,
    replay_integrity: bool = True,
):
    values = []
    for index, scenario in enumerate(REQUIRED_SHADOW_SCENARIOS):
        values.append(
            seal_shadow_observation(
                observation_id=f"shadow:{scenario.value}",
                tenant_id=tenant_id,
                company_id="company-a",
                problem_class="operations-root-cause",
                candidate_system_id=candidate.candidate_system_id,
                candidate_version=candidate.candidate_version,
                scenario=scenario,
                baseline=_performance(0.72),
                candidate=_performance(0.91),
                candidate_grounding_integrity=scenario is not grounding_failure,
                candidate_authority_integrity=scenario is not authority_failure,
                candidate_safe_failure=(
                    scenario is ShadowScenario.NORMAL
                    or scenario is not safe_failure_missing
                ),
                candidate_replay_integrity=(
                    replay_integrity
                    if scenario is ShadowScenario.CHECKPOINT_REPLAY
                    else True
                ),
                candidate_side_effect_count=1 if scenario is side_effect_scenario else 0,
                evidence_refs=(f"shadow-evidence://{index}/{scenario.value}",),
            )
        )
    return tuple(values)


def test_full_shadow_acceptance_is_canary_ready_but_never_self_activates() -> None:
    candidate = _candidate()
    binding = _binding(candidate)

    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=binding,
        observations=_observations(candidate),
    )

    assert evidence.production_shaped_acceptance_passed is True
    assert evidence.controlled_activation_review_ready is True
    assert evidence.observed_scenarios == tuple(
        sorted(REQUIRED_SHADOW_SCENARIOS, key=lambda item: item.value)
    )
    assert evidence.metrics.measured_quality_improvement >= 0.02
    assert evidence.automatic_activation_allowed is False
    assert evidence.automatic_policy_update_allowed is False
    assert evidence.automatic_model_weight_update_allowed is False
    assert evidence.execution_authority_granted is False
    assert evidence.side_effect_authority_granted is False
    assert evidence.blockers == ()


def test_missing_adversarial_scenario_blocks_shadow_acceptance() -> None:
    candidate = _candidate()
    observations = tuple(
        item
        for item in _observations(candidate)
        if item.scenario is not ShadowScenario.PROMPT_TOOL_INJECTION
    )

    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=_binding(candidate),
        observations=observations,
    )

    assert evidence.production_shaped_acceptance_passed is False
    assert (
        "shadow_acceptance_missing_scenario:prompt_tool_injection"
        in evidence.blockers
    )


@pytest.mark.parametrize(
    ("field", "scenario", "expected"),
    (
        (
            "grounding_failure",
            ShadowScenario.STALE_EVIDENCE,
            "shadow_acceptance_grounding_integrity_regression:stale_evidence",
        ),
        (
            "authority_failure",
            ShadowScenario.CROSS_TENANT_PROBE,
            "shadow_acceptance_authority_integrity_regression:cross_tenant_probe",
        ),
        (
            "side_effect_scenario",
            ShadowScenario.PROMPT_TOOL_INJECTION,
            "shadow_acceptance_side_effect_observed:prompt_tool_injection",
        ),
        (
            "safe_failure_missing",
            ShadowScenario.PROVIDER_OUTAGE,
            "shadow_acceptance_safe_failure_missing:provider_outage",
        ),
    ),
)
def test_shadow_safety_regression_blocks_acceptance(field, scenario, expected) -> None:
    candidate = _candidate()
    kwargs = {field: scenario}

    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=_binding(candidate),
        observations=_observations(candidate, **kwargs),
    )

    assert evidence.production_shaped_acceptance_passed is False
    assert expected in evidence.blockers
    assert evidence.execution_authority_granted is False


def test_checkpoint_replay_integrity_is_mandatory() -> None:
    candidate = _candidate()

    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=_binding(candidate),
        observations=_observations(candidate, replay_integrity=False),
    )

    assert evidence.production_shaped_acceptance_passed is False
    assert "shadow_acceptance_replay_integrity_regression" in evidence.blockers


def test_cross_tenant_shadow_observation_is_rejected_from_acceptance() -> None:
    candidate = _candidate()

    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=_binding(candidate),
        observations=_observations(candidate, tenant_id="tenant-b"),
    )

    assert evidence.production_shaped_acceptance_passed is False
    assert "shadow_acceptance_cross_tenant_observation_forbidden" in evidence.blockers


def test_tampered_shadow_observation_is_rejected_before_acceptance() -> None:
    candidate = _candidate()
    observation = _observations(candidate)[0]
    tampered = observation.model_dump(mode="json")
    tampered["candidate"]["correctness"] = 0.01

    with pytest.raises(
        ValueError,
        match="shadow_observation_fingerprint_mismatch",
    ):
        ShadowCanaryObservation.model_validate(tampered)


def test_tampered_acceptance_artifact_cannot_claim_authority() -> None:
    candidate = _candidate()
    evidence = build_shadow_acceptance_evidence(
        candidate=candidate,
        binding=_binding(candidate),
        observations=_observations(candidate),
    )
    tampered = evidence.model_dump(mode="json")
    tampered["execution_authority_granted"] = True

    with pytest.raises(ValueError, match="shadow_acceptance_never_grants_authority"):
        ShadowAcceptanceEvidence.model_validate(tampered)
