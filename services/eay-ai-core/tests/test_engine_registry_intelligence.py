from datetime import datetime, timezone

from app.benchmark_promotion import EngineBenchmarkAttestation
from app.engine_registry import build_engine_registry


def _attestation(engine_id: str, *, score: float, marker: str) -> EngineBenchmarkAttestation:
    fingerprint = marker * 64
    return EngineBenchmarkAttestation(
        engine_id=engine_id,
        system_version="verified-v1",
        task_set_id="eay-enterprise-agent-bench-v1",
        task_set_fingerprint="1" * 64,
        environment_fingerprint="2" * 64,
        benchmark_score=score,
        evidence_ref=f"benchmark://{fingerprint}",
        artifact_fingerprint=fingerprint,
        generated_at=datetime(2026, 8, 18, 6, 0, tzinfo=timezone.utc),
        baseline_system_ids=("peer-baseline",),
        measurement_evidence_refs=(f"evidence://{engine_id}/measured-run",),
        minimum_sample_count=30,
        critical_safety_regression=False,
        promotion_allowed=True,
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


def test_frontier_enable_flag_without_secret_model_and_verified_attestation_fails_closed():
    state = build_engine_registry({"EAY_OPENAI_ENABLED": "true"})

    assert state.requested_frontier_engines == ("openai-frontier",)
    assert state.active_frontier_engines == ()
    assert "openai-frontier" not in state.by_id()
    assert "eay_openai_model_id_missing" in state.blockers
    assert "eay_openai_secret_missing" in state.blockers
    assert "eay_openai_verified_benchmark_attestation_missing" in state.blockers


def test_frontier_engine_activates_only_with_model_secret_and_verified_benchmark_attestation():
    secret = "do-not-retain-this-secret"
    attestation = _attestation("openai-frontier", score=0.94, marker="a")
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": secret,
        },
        benchmark_attestations={"openai-frontier": attestation},
    )

    assert state.active_frontier_engines == ("openai-frontier",)
    frontier = state.by_id()["openai-frontier"]
    assert frontier.profile.production_enabled is True
    assert frontier.profile.benchmark_score == 0.94
    assert frontier.profile.benchmark_evidence_ref == attestation.evidence_ref
    assert frontier.endpoint.secret_ref == "env:OPENAI_API_KEY"
    assert secret not in state.model_dump_json()


def test_all_three_frontier_families_can_activate_independently_with_attestations():
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
    attestations = {
        "openai-frontier": _attestation("openai-frontier", score=0.94, marker="a"),
        "anthropic-frontier": _attestation("anthropic-frontier", score=0.93, marker="b"),
        "gemini-frontier": _attestation("gemini-frontier", score=0.92, marker="c"),
    }
    state = build_engine_registry(env, benchmark_attestations=attestations)

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


def test_invalid_configured_benchmark_score_cannot_override_attestation():
    attestation = _attestation("gemini-frontier", score=0.92, marker="c")
    state = build_engine_registry(
        {
            "EAY_GEMINI_ENABLED": "true",
            "EAY_GEMINI_MODEL": "gemini-3.1-pro-preview",
            "GEMINI_API_KEY": "g",
            "EAY_GEMINI_BENCHMARK_SCORE": "eleven-out-of-ten",
        },
        benchmark_attestations={"gemini-frontier": attestation},
    )

    assert "gemini-frontier" not in state.by_id()
    assert "eay_gemini_benchmark_score_invalid" in state.blockers
