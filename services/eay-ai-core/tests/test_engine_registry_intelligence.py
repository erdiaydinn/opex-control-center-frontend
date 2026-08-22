from datetime import datetime, timezone

from app.benchmark_promotion import build_verified_engine_benchmark_promotion
from app.engine_registry import build_engine_registry
from app.jarvis_benchmark import (
    BenchmarkMetric,
    BenchmarkRun,
    MetricDirection,
    MetricMeasurement,
)


_METRICS = (
    BenchmarkMetric(
        metric_name="task_success",
        direction=MetricDirection.HIGHER_IS_BETTER,
        weight=4.0,
    ),
    BenchmarkMetric(
        metric_name="silent_wrong_action_rate",
        direction=MetricDirection.LOWER_IS_BETTER,
        weight=10.0,
        critical_safety=True,
    ),
)


def _run(system_id: str, *, success: float, wrong: float) -> BenchmarkRun:
    return BenchmarkRun(
        system_id=system_id,
        system_version="verified-v1",
        task_set_id="eay-enterprise-agent-bench-v1",
        task_set_fingerprint="1" * 64,
        environment_fingerprint="2" * 64,
        measured_at=datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc),
        measurements=(
            MetricMeasurement(
                metric_name="task_success",
                value=success,
                sample_count=30,
                evidence_ref=f"benchmark-evidence://{system_id}/success",
            ),
            MetricMeasurement(
                metric_name="silent_wrong_action_rate",
                value=wrong,
                sample_count=30,
                evidence_ref=f"benchmark-evidence://{system_id}/wrong",
            ),
        ),
    )


def _promotion(engine_id: str):
    return build_verified_engine_benchmark_promotion(
        engine_id=engine_id,
        challenger=_run(engine_id, success=0.96, wrong=0.001),
        baselines=(_run(f"{engine_id}-baseline", success=0.88, wrong=0.010),),
        metrics=_METRICS,
        generated_at=datetime(2026, 8, 18, 6, 5, tzinfo=timezone.utc),
    )


def test_default_registry_keeps_existing_ollama_local_first_and_frontier_off():
    state = build_engine_registry({})

    assert [item.profile.engine_id for item in state.registrations] == ["ollama-local"]
    assert state.active_frontier_engines == ()
    assert state.requested_frontier_engines == ()
    assert state.secret_values_retained is False
    local = state.by_id()["ollama-local"]
    assert local.endpoint.base_url == "http://ollama:11434"
    assert local.endpoint.model_id == "eay-ops:0.1"
    assert local.profile.local_processing is True


def test_frontier_enable_flag_without_secret_model_and_verified_promotion_fails_closed():
    state = build_engine_registry({"EAY_OPENAI_ENABLED": "true"})

    assert state.requested_frontier_engines == ("openai-frontier",)
    assert state.active_frontier_engines == ()
    assert "openai-frontier" not in state.by_id()
    assert "eay_openai_model_id_missing" in state.blockers
    assert "eay_openai_secret_missing" in state.blockers
    assert "eay_openai_verified_benchmark_promotion_missing" in state.blockers


def test_frontier_engine_activates_only_with_model_secret_and_verified_benchmark_promotion():
    secret = "do-not-retain-this-secret"
    promotion = _promotion("openai-frontier")
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": secret,
        },
        benchmark_promotions={"openai-frontier": promotion},
    )

    assert state.active_frontier_engines == ("openai-frontier",)
    frontier = state.by_id()["openai-frontier"]
    assert frontier.profile.production_enabled is True
    assert frontier.profile.benchmark_score == promotion.attestation.benchmark_score
    assert frontier.profile.benchmark_evidence_ref == promotion.attestation.evidence_ref
    assert frontier.endpoint.secret_ref == "env:OPENAI_API_KEY"
    assert secret not in state.model_dump_json()


def test_all_three_frontier_families_can_activate_independently_with_verified_promotions():
    env = {
        "EAY_OPENAI_ENABLED": "1",
        "EAY_OPENAI_MODEL": "gpt-5.6",
        "OPENAI_API_KEY": "o",
        "EAY_ANTHROPIC_ENABLED": "1",
        "EAY_ANTHROPIC_MODEL": "claude-opus-4-8",
        "ANTHROPIC_API_KEY": "a",
        "EAY_GEMINI_ENABLED": "1",
        "EAY_GEMINI_MODEL": "gemini-3.1-pro-preview",
        "GEMINI_API_KEY": "g",
    }
    promotions = {
        "openai-frontier": _promotion("openai-frontier"),
        "anthropic-frontier": _promotion("anthropic-frontier"),
        "gemini-frontier": _promotion("gemini-frontier"),
    }
    state = build_engine_registry(env, benchmark_promotions=promotions)

    assert state.blockers == ()
    assert state.active_frontier_engines == (
        "openai-frontier",
        "anthropic-frontier",
        "gemini-frontier",
    )
    assert {item.profile.independent_provider_key for item in state.registrations} >= {
        "openai",
        "anthropic",
        "google-gemini",
    }


def test_invalid_configured_benchmark_score_cannot_override_verified_promotion():
    promotion = _promotion("gemini-frontier")
    state = build_engine_registry(
        {
            "EAY_GEMINI_ENABLED": "true",
            "EAY_GEMINI_MODEL": "gemini-3.1-pro-preview",
            "GEMINI_API_KEY": "g",
            "EAY_GEMINI_BENCHMARK_SCORE": "eleven-out-of-ten",
        },
        benchmark_promotions={"gemini-frontier": promotion},
    )

    assert "gemini-frontier" not in state.by_id()
    assert "eay_gemini_benchmark_score_invalid" in state.blockers
