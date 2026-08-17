from datetime import datetime, timezone

from app.jarvis_benchmark import (
    BenchmarkMetric,
    BenchmarkRun,
    MetricDirection,
    MetricMeasurement,
    compare_benchmark_runs,
)

UTC = timezone.utc
NOW = datetime(2026, 8, 18, 2, 0, tzinfo=UTC)
FINGERPRINT = "a" * 64
ENVIRONMENT = "b" * 64

METRICS = (
    BenchmarkMetric(
        metric_name="task_success_rate",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=4,
    ),
    BenchmarkMetric(
        metric_name="wrong_action_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=4,
        critical_safety=True,
    ),
    BenchmarkMetric(
        metric_name="evidence_accuracy",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=2,
        critical_safety=True,
    ),
)


def _run(system_id, success, wrong, evidence, *, samples=50, task_set="executive-v1", env=ENVIRONMENT):
    return BenchmarkRun(
        system_id=system_id,
        system_version="2026-08",
        task_set_id=task_set,
        task_set_fingerprint=FINGERPRINT,
        environment_fingerprint=env,
        measured_at=NOW,
        measurements=(
            MetricMeasurement(
                metric_name="task_success_rate",
                value=success,
                sample_count=samples,
                evidence_ref=f"bench://{system_id}/success",
            ),
            MetricMeasurement(
                metric_name="wrong_action_rate",
                value=wrong,
                sample_count=samples,
                evidence_ref=f"bench://{system_id}/wrong",
            ),
            MetricMeasurement(
                metric_name="evidence_accuracy",
                value=evidence,
                sample_count=samples,
                evidence_ref=f"bench://{system_id}/evidence",
            ),
        ),
    )


def test_superiority_claim_requires_actual_same_task_win_without_safety_regression():
    comparison = compare_benchmark_runs(
        challenger=_run("eay-jarvis", 0.96, 0.002, 0.995),
        baseline=_run("frontier-baseline", 0.90, 0.010, 0.980),
        metrics=METRICS,
    )

    assert comparison.comparable is True
    assert comparison.weighted_win_rate == 1.0
    assert comparison.critical_safety_regression is False
    assert comparison.superiority_claim_allowed is True


def test_safety_regression_blocks_claim_even_when_task_success_is_higher():
    comparison = compare_benchmark_runs(
        challenger=_run("eay-jarvis", 0.99, 0.020, 0.995),
        baseline=_run("frontier-baseline", 0.90, 0.010, 0.980),
        metrics=METRICS,
    )

    assert comparison.superiority_claim_allowed is False
    assert comparison.critical_safety_regression is True
    assert "benchmark_critical_safety_regression" in comparison.blockers


def test_different_environment_cannot_support_superiority_claim():
    comparison = compare_benchmark_runs(
        challenger=_run("eay-jarvis", 0.96, 0.002, 0.995),
        baseline=_run("frontier-baseline", 0.90, 0.010, 0.980, env="c" * 64),
        metrics=METRICS,
    )

    assert comparison.comparable is False
    assert comparison.superiority_claim_allowed is False
    assert "benchmark_environment_not_comparable" in comparison.blockers


def test_small_sample_demo_cannot_be_promoted_to_superiority_claim():
    comparison = compare_benchmark_runs(
        challenger=_run("eay-jarvis", 1.0, 0.0, 1.0, samples=3),
        baseline=_run("frontier-baseline", 0.5, 0.2, 0.5, samples=3),
        metrics=METRICS,
    )

    assert comparison.superiority_claim_allowed is False
    assert any(blocker.startswith("benchmark_sample_count_insufficient") for blocker in comparison.blockers)
