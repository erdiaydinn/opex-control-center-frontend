from datetime import datetime, timezone

from app.benchmark_promotion import build_engine_benchmark_attestation
from app.engine_registry import build_engine_registry
from app.jarvis_benchmark import (
    BenchmarkMetric,
    BenchmarkRun,
    MetricDirection,
    MetricMeasurement,
)


TASK_FP = "a" * 64
ENV_FP = "b" * 64


METRICS = (
    BenchmarkMetric(
        metric_name="task_success",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=3.0,
    ),
    BenchmarkMetric(
        metric_name="silent_wrong_action_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=5.0,
        critical_safety=True,
    ),
    BenchmarkMetric(
        metric_name="latency_seconds",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=1.0,
    ),
)


def _run(system_id: str, *, success: float, wrong: float, latency: float, version: str = "v1") -> BenchmarkRun:
    return BenchmarkRun(
        system_id=system_id,
        system_version=version,
        task_set_id="eay-enterprise-agent-bench-v1",
        task_set_fingerprint=TASK_FP,
        environment_fingerprint=ENV_FP,
        measured_at=datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc),
        measurements=(
            MetricMeasurement(
                metric_name="task_success",
                value=success,
                sample_count=30,
                evidence_ref=f"evidence://{system_id}/success",
            ),
            MetricMeasurement(
                metric_name="silent_wrong_action_rate",
                value=wrong,
                sample_count=30,
                evidence_ref=f"evidence://{system_id}/wrong-action",
            ),
            MetricMeasurement(
                metric_name="latency_seconds",
                value=latency,
                sample_count=30,
                evidence_ref=f"evidence://{system_id}/latency",
            ),
        ),
    )


def _promotable_openai_attestation():
    return build_engine_benchmark_attestation(
        engine_id="openai-frontier",
        challenger=_run("openai-frontier", success=0.96, wrong=0.001, latency=1.8),
        baselines=(
            _run("baseline-a", success=0.88, wrong=0.010, latency=2.6),
            _run("baseline-b", success=0.90, wrong=0.008, latency=2.2),
        ),
        metrics=METRICS,
        generated_at=datetime(2026, 8, 18, 6, 5, tzinfo=timezone.utc),
    )


def test_promotion_artifact_is_fingerprinted_and_evidence_bound():
    artifact = _promotable_openai_attestation()

    assert artifact.promotion_allowed is True
    assert artifact.blockers == ()
    assert artifact.benchmark_score == 1.0
    assert artifact.evidence_ref == f"benchmark://{artifact.artifact_fingerprint}"
    assert artifact.minimum_sample_count == 30
    assert "evidence://openai-frontier/success" in artifact.measurement_evidence_refs
    assert artifact.baseline_system_ids == ("baseline-a", "baseline-b")


def test_critical_safety_regression_blocks_promotion_even_when_other_metrics_win():
    challenger = _run("openai-frontier", success=0.99, wrong=0.020, latency=1.0)
    baseline = _run("baseline", success=0.90, wrong=0.005, latency=2.5)

    artifact = build_engine_benchmark_attestation(
        engine_id="openai-frontier",
        challenger=challenger,
        baselines=(baseline,),
        metrics=METRICS,
    )

    assert artifact.promotion_allowed is False
    assert artifact.critical_safety_regression is True
    assert "benchmark_attestation_critical_safety_regression" in artifact.blockers


def test_frontier_engine_cannot_activate_from_environment_score_without_attestation():
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": "secret",
            "EAY_OPENAI_BENCHMARK_SCORE": "1.0",
            "EAY_OPENAI_BENCHMARK_EVIDENCE_REF": "benchmark://" + "c" * 64,
        }
    )

    assert "openai-frontier" in state.requested_frontier_engines
    assert "openai-frontier" not in state.active_frontier_engines
    assert "eay_openai_verified_benchmark_attestation_missing" in state.blockers
    assert state.secret_values_retained is False


def test_promotable_attestation_activates_frontier_engine_without_storing_secret():
    artifact = _promotable_openai_attestation()
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": "super-secret-value",
        },
        benchmark_attestations={"openai-frontier": artifact},
    )

    assert "openai-frontier" in state.active_frontier_engines
    registration = state.by_id()["openai-frontier"]
    assert registration.profile.benchmark_score == artifact.benchmark_score
    assert registration.profile.benchmark_evidence_ref == artifact.evidence_ref
    assert registration.endpoint.secret_ref == "env:OPENAI_API_KEY"
    assert "super-secret-value" not in state.model_dump_json()


def test_environment_cannot_tamper_with_attested_score_or_evidence_reference():
    artifact = _promotable_openai_attestation()
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": "secret",
            "EAY_OPENAI_BENCHMARK_SCORE": "0.51",
            "EAY_OPENAI_BENCHMARK_EVIDENCE_REF": "benchmark://" + "d" * 64,
        },
        benchmark_attestations={"openai-frontier": artifact},
    )

    assert "openai-frontier" not in state.active_frontier_engines
    assert "eay_openai_benchmark_score_attestation_mismatch" in state.blockers
    assert "eay_openai_benchmark_evidence_ref_attestation_mismatch" in state.blockers
