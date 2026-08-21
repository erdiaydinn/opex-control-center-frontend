import hashlib
from dataclasses import replace

import pytest

from app.voice_measurement_harness import (
    VoiceMeasurementSample,
    aggregate_voice_measurements,
    seal_language_release_evidence_from_measurements,
)


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash(ch: str) -> str:
    return ch * 64


def _sample(index: int, *, language="tr", **overrides) -> VoiceMeasurementSample:
    values = {
        "language": language,
        "case_id_sha256": _hash_text(f"case-{index}"),
        "reference_text_sha256": _hash_text(f"reference-{index}"),
        "hypothesis_text_sha256": _hash_text(f"hypothesis-{index}"),
        "input_lineage_fingerprint": _hash_text(f"input-{index}"),
        "tts_generation_proof_fingerprint": _hash_text(f"tts-proof-{index}"),
        "streaming_result_fingerprint": _hash_text(f"stream-{index}"),
        "reference_word_count": 10,
        "word_error_count": 1 if index in {0, 1} else 0,
        "semantic_consistent": True,
        "naturalness_score": 4.5,
        "citation_checks_count": 2,
        "citation_checks_correct": 2,
        "first_audio_ms": 100 + index,
        "barge_in_ms": 50 + index,
        "interruption_succeeded": True,
        "cancel_propagation_ms": 20 + index,
        "approval_replay_accept_count": 0,
        "human_review_event_sha256": _hash_text(f"human-review-{index}"),
    }
    values.update(overrides)
    return VoiceMeasurementSample(**values)


def test_measurement_harness_computes_release_metrics_from_50_hash_bound_samples():
    aggregate = aggregate_voice_measurements([_sample(index) for index in range(50)])
    evaluation = aggregate.evaluation
    assert aggregate.language == "tr"
    assert evaluation.sample_count == 50
    assert evaluation.stt_word_error_rate == pytest.approx(2 / 500)
    assert evaluation.semantic_consistency_rate == 1.0
    assert evaluation.human_naturalness_score == 4.5
    assert evaluation.citation_readback_accuracy == 1.0
    assert evaluation.p95_first_audio_ms == 147
    assert evaluation.p95_barge_in_ms == 97
    assert evaluation.p95_cancel_propagation_ms == 67
    assert evaluation.interruption_success_rate == 1.0
    assert len(aggregate.raw_measurement_manifest_sha256) == 64
    assert len(aggregate.human_review_manifest_sha256) == 64
    aggregate.validate()


def test_measurement_harness_seals_directly_into_exact_release_evidence():
    aggregate, evidence = seal_language_release_evidence_from_measurements(
        samples=[_sample(index) for index in range(50)],
        deployment_manifest_fingerprint=_hash("1"),
        model_execution_identity_fingerprint=_hash("2"),
        tts_bundle_execution_identity_fingerprint=_hash("3"),
        runtime_attestation_bundle_fingerprint=_hash("4"),
        eval_suite_sha256=_hash("5"),
        measurement_harness_sha256=_hash("6"),
        runtime_environment_fingerprint=_hash("7"),
        reviewer="human-reviewer",
        approval_reference="VOICE-HARNESS-TR-001",
    )
    assert evidence.evaluation.fingerprint == aggregate.evaluation.fingerprint
    assert evidence.raw_measurement_manifest_sha256 == aggregate.raw_measurement_manifest_sha256
    assert evidence.human_review_manifest_sha256 == aggregate.human_review_manifest_sha256
    assert evidence.runtime_attestation_bundle_fingerprint == _hash("4")
    evidence.validate()


def test_measurement_harness_rejects_duplicate_sample_replay():
    sample = _sample(0)
    with pytest.raises(ValueError, match="voice_measurement_duplicate_sample_forbidden"):
        aggregate_voice_measurements([sample, sample])


def test_measurement_harness_rejects_cross_language_mix():
    with pytest.raises(ValueError, match="voice_measurement_mixed_languages_forbidden"):
        aggregate_voice_measurements([_sample(0, language="tr"), _sample(1, language="en")])


def test_measurement_sample_fingerprint_detects_metric_tamper():
    sealed = _sample(0).sealed()
    tampered = replace(sealed, first_audio_ms=1)
    with pytest.raises(ValueError, match="voice_measurement_sample_fingerprint_drift"):
        tampered.validate()


def test_measurement_sample_rejects_invalid_human_naturalness_value():
    with pytest.raises(ValueError, match="voice_measurement_naturalness_invalid"):
        _sample(0, naturalness_score=float("nan")).sealed()
