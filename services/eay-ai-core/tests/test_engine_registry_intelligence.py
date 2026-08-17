from app.engine_registry import build_engine_registry


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


def test_frontier_enable_flag_without_secret_model_and_benchmark_fails_closed():
    state = build_engine_registry({"EAY_OPENAI_ENABLED": "true"})

    assert state.requested_frontier_engines == ("openai-frontier",)
    assert state.active_frontier_engines == ()
    assert "openai-frontier" not in state.by_id()
    assert "eay_openai_model_id_missing" in state.blockers
    assert "eay_openai_secret_missing" in state.blockers
    assert "eay_openai_benchmark_evidence_missing" in state.blockers


def test_frontier_engine_activates_only_with_model_secret_and_benchmark_evidence():
    secret = "do-not-retain-this-secret"
    state = build_engine_registry(
        {
            "EAY_OPENAI_ENABLED": "true",
            "EAY_OPENAI_MODEL": "gpt-5.6",
            "OPENAI_API_KEY": secret,
            "EAY_OPENAI_BENCHMARK_SCORE": "0.94",
            "EAY_OPENAI_BENCHMARK_EVIDENCE_REF": "benchmark://jarvisbench/openai/2026-08-18",
        }
    )

    assert state.active_frontier_engines == ("openai-frontier",)
    frontier = state.by_id()["openai-frontier"]
    assert frontier.profile.production_enabled is True
    assert frontier.profile.benchmark_score == 0.94
    assert frontier.profile.benchmark_evidence_ref == "benchmark://jarvisbench/openai/2026-08-18"
    assert frontier.endpoint.secret_ref == "env:OPENAI_API_KEY"
    assert secret not in state.model_dump_json()


def test_all_three_frontier_families_can_activate_independently():
    env = {
        "EAY_OPENAI_ENABLED": "1",
        "EAY_OPENAI_MODEL": "gpt-5.6",
        "OPENAI_API_KEY": "o",
        "EAY_OPENAI_BENCHMARK_SCORE": "0.94",
        "EAY_OPENAI_BENCHMARK_EVIDENCE_REF": "benchmark://openai",
        "EAY_ANTHROPIC_ENABLED": "1",
        "EAY_ANTHROPIC_MODEL": "claude-opus-4-8",
        "ANTHROPIC_API_KEY": "a",
        "EAY_ANTHROPIC_BENCHMARK_SCORE": "0.93",
        "EAY_ANTHROPIC_BENCHMARK_EVIDENCE_REF": "benchmark://anthropic",
        "EAY_GEMINI_ENABLED": "1",
        "EAY_GEMINI_MODEL": "gemini-3.1-pro-preview",
        "GEMINI_API_KEY": "g",
        "EAY_GEMINI_BENCHMARK_SCORE": "0.92",
        "EAY_GEMINI_BENCHMARK_EVIDENCE_REF": "benchmark://gemini",
    }
    state = build_engine_registry(env)

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


def test_invalid_benchmark_score_does_not_activate_frontier():
    state = build_engine_registry(
        {
            "EAY_GEMINI_ENABLED": "true",
            "EAY_GEMINI_MODEL": "gemini-3.1-pro-preview",
            "GEMINI_API_KEY": "g",
            "EAY_GEMINI_BENCHMARK_SCORE": "eleven-out-of-ten",
            "EAY_GEMINI_BENCHMARK_EVIDENCE_REF": "benchmark://gemini",
        }
    )

    assert "gemini-frontier" not in state.by_id()
    assert "eay_gemini_benchmark_score_invalid" in state.blockers
