from datetime import datetime, timezone

import pytest

from app.benchmark_promotion import (
    VerifiedEngineBenchmarkPromotion,
    build_engine_benchmark_attestation,
    build_verified_engine_benchmark_promotion,
)
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


def _source_runs():
    return (
        _run("openai-frontier", success=0.96, wrong=0.001, latency=1.8),
        (
            _run("baseline-a", success=0.88, wrong=0.010, latency=2.6),
            _run("baseline-b", success=0.90, wrong=0.008, latency=2.2),
        ),
    )


def _promotable_openai_attestation():
    challenger, baselines = _source_runs()
    return build_engine_benchmark_attestation(
        engine_id="openai-frontier",
        challenger=challenger,
        baselines=baselines,
        metrics=METRICS,
        generated_at=datetime(2026, 8, 18, 6, 5, tzinfo=timezone.utc),
    )


def _verified_openai_promotion():
    challenger, baselines = _source_runs()
    return build_verified_engine_benchmark_promotion(
        engine_id="openai-frontier",
        challenger=challenger,
        baselines=baselines,
        metrics=METRICS,
        generated_at=datetime(2026, 8, 18, 6, 5, tzinfo=timezone.utc),
    )


def _environment(**extra):
    payload = {
        "EAY_OPENAI_ENABLED": "true",
        "EAY_OPENAI_MODEL": "gpt-5.6",
        "OPENAI_API_KEY": "super-secret-value",
    }
    payload.update(extra)
    return payload


def test_promotion_artifact_is_fingerprinted_and_evidence_bound():
    artifact = _promotable_openai_attestation()

    assert artifact.promotion_allowed is True
    assert artifact.blockers == ()
    assert artifact.benchmark_score == 1.0
    assert artifact.evidence_ref == f"benchmark://{artifact.artifact_fingerprint}"
    assert artifact.minimum_sample_count == 30
    assert "evidence://openai-frontier/success" in artifact.measurement_evidence_refs
    assert artifact.baseline_system_ids == ("baseline-a", "baseline-b")


def test_verified_promotion_replays_source_runs_and_has_own_fingerprint():
    promotion = _verified_openai_promotion()

    assert promotion.attestation.promotion_allowed is True
    assert promotion.challenger.system_id == "openai-frontier"
    assert len(promotion.baselines) == 2
    assert len(promotion.verification_fingerprint) == 64


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


def test_frontier_engine_cannot_activate_from_environment_score_without_verified_promotion():
    state = build_engine_registry(
        _environment(
            EAY_OPENAI_BENCHMARK_SCORE="1.0",
            EAY_OPENAI_BENCHMARK_EVIDENCE_REF="benchmark://" + "c" * 64,
        )
    )

    assert "openai-frontier" in state.requested_frontier_engines
    assert "openai-frontier" not in state.active_frontier_engines
    assert "eay_openai_verified_benchmark_promotion_missing" in state.blockers
    assert state.secret_values_retained is False


def test_plain_shape_valid_attestation_is_not_a_registry_promotion_receipt():
    artifact = _promotable_openai_attestation()
    state = build_engine_registry(
        _environment(),
        benchmark_promotions={"openai-frontier": artifact},  # runtime misuse on purpose
    )

    assert "openai-frontier" not in state.active_frontier_engines
    assert "eay_openai_verified_benchmark_promotion_required" in state.blockers


def test_replay_verified_promotion_activates_frontier_engine_without_storing_secret():
    promotion = _verified_openai_promotion()
    state = build_engine_registry(
        _environment(),
        benchmark_promotions={"openai-frontier": promotion},
    )

    assert "openai-frontier" in state.active_frontier_engines
    registration = state.by_id()["openai-frontier"]
    assert registration.profile.benchmark_score == promotion.attestation.benchmark_score
    assert registration.profile.benchmark_evidence_ref == promotion.attestation.evidence_ref
    assert registration.endpoint.secret_ref == "env:OPENAI_API_KEY"
    assert "super-secret-value" not in state.model_dump_json()


def test_environment_cannot_tamper_with_verified_score_or_evidence_reference():
    promotion = _verified_openai_promotion()
    state = build_engine_registry(
        _environment(
            EAY_OPENAI_BENCHMARK_SCORE="0.51",
            EAY_OPENAI_BENCHMARK_EVIDENCE_REF="benchmark://" + "d" * 64,
        ),
        benchmark_promotions={"openai-frontier": promotion},
    )

    assert "openai-frontier" not in state.active_frontier_engines
    assert "eay_openai_benchmark_score_promotion_mismatch" in state.blockers
    assert "eay_openai_benchmark_evidence_ref_promotion_mismatch" in state.blockers


def test_verified_bundle_rejects_attestation_score_tampering_even_with_valid_source_runs():
    promotion = _verified_openai_promotion()
    forged_attestation = promotion.attestation.model_copy(update={"benchmark_score": 0.99})

    with pytest.raises(ValueError, match="verified_benchmark_promotion_attestation_not_reproducible"):
        VerifiedEngineBenchmarkPromotion(
            attestation=forged_attestation,
            challenger=promotion.challenger,
            baselines=promotion.baselines,
            metrics=promotion.metrics,
            required_weighted_win_rate=promotion.required_weighted_win_rate,
            verification_fingerprint=promotion.verification_fingerprint,
        )


def test_attestation_engine_id_must_match_measured_challenger():
    challenger, baselines = _source_runs()
    with pytest.raises(ValueError, match="benchmark_attestation_challenger_engine_mismatch"):
        build_engine_benchmark_attestation(
            engine_id="anthropic-frontier",
            challenger=challenger,
            baselines=baselines,
            metrics=METRICS,
        )
