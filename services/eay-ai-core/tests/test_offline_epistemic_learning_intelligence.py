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
    EpistemicLearningEpisode,
    LearningDisposition,
    bind_candidate_to_verified_benchmark,
    learn_epistemic_strategy_candidate,
    seal_learning_episode,
)

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def _episode(
    index: int,
    *,
    strategy: EpistemicStrategy,
    quality: float,
    tenant_id: str = "tenant-a",
    company_id: str = "company-a",
    problem_class: str = "operations-root-cause",
    grounding_integrity: bool = True,
    authority_integrity: bool = True,
):
    return seal_learning_episode(
        episode_id=f"episode:{strategy.value}:{index}",
        tenant_id=tenant_id,
        company_id=company_id,
        problem_class=problem_class,
        strategy=strategy,
        completed_at=NOW + timedelta(minutes=index),
        correctness=quality,
        brier_score=round(1.0 - quality, 6),
        falsification_success=quality,
        contradiction_resolution=quality,
        information_gain_per_probe=quality,
        cost_efficiency=max(0.0, quality - 0.05),
        latency_efficiency=max(0.0, quality - 0.10),
        grounding_integrity=grounding_integrity,
        authority_integrity=authority_integrity,
        evidence_refs=(f"evidence://{strategy.value}/{index}",),
        source_family_refs=(
            f"source-family://{strategy.value}/{index % 3}",
        ),
    )


def _episodes() -> tuple[EpistemicLearningEpisode, ...]:
    values = []
    for index in range(6):
        values.append(
            _episode(
                index,
                strategy=EpistemicStrategy.CONTRADICTION_FIRST,
                quality=0.70,
            )
        )
        values.append(
            _episode(
                index,
                strategy=EpistemicStrategy.FALSIFICATION,
                quality=0.92,
            )
        )
        values.append(
            _episode(
                index,
                strategy=EpistemicStrategy.INDEPENDENT_CORROBORATION,
                quality=0.80,
            )
        )
    return tuple(values)


def _promotion(candidate):
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
    task_fingerprint = "1" * 64
    environment_fingerprint = "2" * 64
    challenger = BenchmarkRun(
        system_id=candidate.candidate_system_id,
        system_version=candidate.candidate_version,
        task_set_id="jarvis-epistemic-promotion-v1",
        task_set_fingerprint=task_fingerprint,
        environment_fingerprint=environment_fingerprint,
        measured_at=NOW,
        measurements=(
            MetricMeasurement(
                metric_name="novel_problem_accuracy",
                value=0.92,
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
        task_set_id="jarvis-epistemic-promotion-v1",
        task_set_fingerprint=task_fingerprint,
        environment_fingerprint=environment_fingerprint,
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
    return build_verified_engine_benchmark_promotion(
        engine_id=candidate.candidate_system_id,
        challenger=challenger,
        baselines=(baseline,),
        metrics=metrics,
        required_weighted_win_rate=0.80,
        generated_at=NOW,
    )


def test_offline_learning_selects_measured_strategy_without_self_activation() -> None:
    candidate = learn_epistemic_strategy_candidate(
        episodes=_episodes(),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )

    assert candidate.disposition is LearningDisposition.CANDIDATE
    assert candidate.recommended_strategy_order[0] is EpistemicStrategy.FALSIFICATION
    assert candidate.measured_improvement >= 0.03
    assert candidate.sample_count == 18
    assert candidate.source_family_count >= 9
    assert candidate.automatic_policy_update_allowed is False
    assert candidate.automatic_model_weight_update_allowed is False
    assert candidate.automatic_research_execution_allowed is False
    assert candidate.direct_provider_call_allowed is False
    assert candidate.execution_authority_granted is False


def test_cross_tenant_learning_evidence_is_rejected() -> None:
    episodes = list(_episodes())
    episodes[-1] = _episode(
        99,
        strategy=EpistemicStrategy.INDEPENDENT_CORROBORATION,
        quality=0.80,
        tenant_id="tenant-b",
    )

    with pytest.raises(
        ValueError,
        match="epistemic_learning_cross_tenant_evidence_forbidden",
    ):
        learn_epistemic_strategy_candidate(
            episodes=tuple(episodes),
            baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
            candidate_version="candidate-v1",
        )


def test_tampered_learning_episode_is_rejected_before_optimization() -> None:
    episode = _episode(
        0,
        strategy=EpistemicStrategy.FALSIFICATION,
        quality=0.92,
    )
    tampered = episode.model_dump(mode="json")
    tampered["correctness"] = 0.01

    with pytest.raises(
        ValueError,
        match="epistemic_learning_episode_fingerprint_mismatch",
    ):
        EpistemicLearningEpisode.model_validate(tampered)


def test_grounding_or_authority_regression_blocks_candidate_promotion() -> None:
    episodes = list(_episodes())
    episodes[0] = _episode(
        100,
        strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        quality=0.70,
        grounding_integrity=False,
    )

    candidate = learn_epistemic_strategy_candidate(
        episodes=tuple(episodes),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )

    assert candidate.disposition is LearningDisposition.HOLD
    assert "epistemic_learning_grounding_integrity_regression" in candidate.blockers


def test_candidate_with_no_measured_strategy_gain_is_held() -> None:
    episodes = tuple(
        _episode(
            index,
            strategy=strategy,
            quality=0.80,
        )
        for strategy in (
            EpistemicStrategy.CONTRADICTION_FIRST,
            EpistemicStrategy.FALSIFICATION,
            EpistemicStrategy.INDEPENDENT_CORROBORATION,
        )
        for index in range(6)
    )

    candidate = learn_epistemic_strategy_candidate(
        episodes=episodes,
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )

    assert candidate.disposition is LearningDisposition.HOLD
    assert "epistemic_learning_improvement_below_floor" in candidate.blockers


def test_verified_benchmark_binding_requires_canary_and_never_self_activates() -> None:
    candidate = learn_epistemic_strategy_candidate(
        episodes=_episodes(),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )
    promotion = _promotion(candidate)

    binding = bind_candidate_to_verified_benchmark(
        candidate=candidate,
        promotion=promotion,
    )

    assert binding.benchmark_promotion_allowed is True
    assert binding.canary_required is True
    assert binding.automatic_activation_allowed is False
    assert binding.execution_authority_granted is False
    assert binding.blockers == ()


def test_benchmark_for_different_candidate_cannot_promote_profile() -> None:
    candidate = learn_epistemic_strategy_candidate(
        episodes=_episodes(),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v1",
    )
    promotion = _promotion(candidate)
    mismatched = learn_epistemic_strategy_candidate(
        episodes=_episodes(),
        baseline_strategy=EpistemicStrategy.CONTRADICTION_FIRST,
        candidate_version="candidate-v2",
    )

    binding = bind_candidate_to_verified_benchmark(
        candidate=mismatched,
        promotion=promotion,
    )

    assert binding.benchmark_promotion_allowed is False
    assert "epistemic_promotion_candidate_version_mismatch" in binding.blockers
    assert binding.automatic_activation_allowed is False
