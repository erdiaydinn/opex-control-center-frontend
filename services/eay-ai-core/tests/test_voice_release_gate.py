import math

import pytest

from app.voice_release_gate import VoiceLanguageEval, evaluate_voice_release
from app.voice_runtime import CORE_LANGUAGES


def _case(language: str, **overrides):
    values = {
        "language": language,
        "sample_count": 100,
        "stt_word_error_rate": 0.05,
        "semantic_consistency_rate": 0.995,
        "human_naturalness_score": 4.4,
        "citation_readback_accuracy": 1.0,
        "p95_first_audio_ms": 650,
        "p95_barge_in_ms": 180,
        "interruption_success_rate": 1.0,
        "p95_cancel_propagation_ms": 120,
        "approval_replay_accept_count": 0,
    }
    values.update(overrides)
    return VoiceLanguageEval(**values)


def test_voice_release_requires_all_core_languages():
    decision = evaluate_voice_release([_case("tr"), _case("en")])
    assert decision.approved is False
    assert any(item.startswith("voice_eval_missing_languages:") for item in decision.violations)


def test_voice_release_passes_only_when_every_language_meets_quality_bar():
    decision = evaluate_voice_release([_case(language) for language in CORE_LANGUAGES])
    assert decision.approved is True
    assert decision.violations == ()
    assert len(decision.language_fingerprints) == 5
    assert len(decision.fingerprint) == 64


def test_low_naturalness_in_one_language_blocks_multilingual_ready():
    cases = [_case(language) for language in CORE_LANGUAGES]
    cases[-1] = _case("fa", human_naturalness_score=3.9)
    decision = evaluate_voice_release(cases)
    assert decision.approved is False
    assert "voice_eval_fa:naturalness_below_target" in decision.violations


def test_slow_barge_in_blocks_release_even_if_stt_is_good():
    cases = [_case(language) for language in CORE_LANGUAGES]
    cases[1] = _case("en", p95_barge_in_ms=450)
    decision = evaluate_voice_release(cases)
    assert decision.approved is False
    assert "voice_eval_en:barge_in_latency_too_high" in decision.violations


def test_interruption_failure_or_slow_cancel_blocks_release():
    cases = [_case(language) for language in CORE_LANGUAGES]
    cases[0] = _case("tr", interruption_success_rate=0.99)
    cases[1] = _case("en", p95_cancel_propagation_ms=300)
    decision = evaluate_voice_release(cases)
    assert decision.approved is False
    assert "voice_eval_tr:interruption_success_too_low" in decision.violations
    assert "voice_eval_en:cancel_propagation_too_slow" in decision.violations


def test_any_accepted_approval_replay_blocks_voice_release():
    cases = [_case(language) for language in CORE_LANGUAGES]
    cases[-1] = _case("fa", approval_replay_accept_count=1)
    decision = evaluate_voice_release(cases)
    assert decision.approved is False
    assert "voice_eval_fa:approval_replay_accepted" in decision.violations


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("semantic_consistency_rate", math.nan, "voice_eval_semantic_consistency_invalid"),
        ("human_naturalness_score", math.inf, "voice_eval_naturalness_invalid"),
        ("citation_readback_accuracy", -0.1, "voice_eval_citation_accuracy_invalid"),
        ("p95_first_audio_ms", -1, "voice_eval_first_audio_latency_invalid"),
        ("p95_barge_in_ms", -1, "voice_eval_barge_in_latency_invalid"),
        ("approval_replay_accept_count", -1, "voice_eval_approval_replay_count_invalid"),
    ],
)
def test_invalid_or_nonfinite_measurement_values_fail_closed(field, value, code):
    cases = [_case(language) for language in CORE_LANGUAGES]
    cases[0] = _case("tr", **{field: value})
    with pytest.raises(ValueError, match=code):
        evaluate_voice_release(cases)
