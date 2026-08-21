from dataclasses import replace

import pytest

from app.voice_release_evidence import VoiceReleaseEvidenceRegistry, seal_voice_language_measurement_evidence
from app.voice_release_gate import VoiceLanguageEval
from app.voice_runtime import CORE_LANGUAGES


def _hash(ch: str) -> str:
    return ch * 64


def _eval(language: str, **overrides) -> VoiceLanguageEval:
    values = {
        "language": language,
        "sample_count": 100,
        "stt_word_error_rate": 0.05,
        "semantic_consistency_rate": 0.995,
        "human_naturalness_score": 4.5,
        "citation_readback_accuracy": 1.0,
        "p95_first_audio_ms": 500,
        "p95_barge_in_ms": 150,
        "interruption_success_rate": 1.0,
        "p95_cancel_propagation_ms": 100,
        "approval_replay_accept_count": 0,
    }
    values.update(overrides)
    return VoiceLanguageEval(**values)


def _evidence(language: str, **overrides):
    values = {
        "evaluation": _eval(language),
        "deployment_manifest_fingerprint": _hash("1"),
        "model_execution_identity_fingerprint": _hash("2"),
        "tts_bundle_execution_identity_fingerprint": _hash("3"),
        "runtime_attestation_bundle_fingerprint": _hash("4"),
        "eval_suite_sha256": _hash("5"),
        "measurement_harness_sha256": _hash("6"),
        "runtime_environment_fingerprint": _hash("7"),
        "raw_measurement_manifest_sha256": _hash("8"),
        "human_review_manifest_sha256": _hash("9"),
        "reviewer": "voice-human-reviewer",
        "approval_reference": f"VOICE-MEASURE-{language}",
    }
    values.update(overrides)
    return seal_voice_language_measurement_evidence(**values)


def _record_core(registry: VoiceReleaseEvidenceRegistry, **overrides):
    records = []
    for language in CORE_LANGUAGES:
        language_overrides = dict(overrides)
        evaluation = language_overrides.pop("evaluation", _eval(language))
        records.append(registry.record_language(_evidence(language, evaluation=evaluation, **language_overrides)))
    return records


def test_release_evidence_binds_metrics_to_exact_runtime_and_human_review(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    evidence = registry.record_language(_evidence("tr"))
    loaded = registry.require_language(evidence.fingerprint)
    assert loaded.evaluation.fingerprint == evidence.evaluation.fingerprint
    assert loaded.deployment_manifest_fingerprint == _hash("1")
    assert loaded.runtime_attestation_bundle_fingerprint == _hash("4")
    assert loaded.human_review_manifest_sha256 == _hash("9")


def test_release_evidence_is_immutable_and_metric_tamper_breaks_fingerprint(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    evidence = registry.record_language(_evidence("tr"))
    with pytest.raises(ValueError, match="voice_release_evidence_already_recorded"):
        registry.record_language(evidence)

    changed_eval = replace(evidence.evaluation, p95_first_audio_ms=100)
    tampered = replace(evidence, evaluation=changed_eval)
    with pytest.raises(ValueError, match="voice_release_evidence_fingerprint_drift"):
        tampered.validate()


def test_governed_release_requires_exact_five_languages_and_same_lineage(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    records = _record_core(registry)
    decision = registry.record_release(
        language_evidence_fingerprints=[item.fingerprint for item in records],
        reviewer="release-reviewer",
        approval_reference="VOICE-RELEASE-001",
    )
    assert decision.approved is True
    assert decision.violations == ()
    assert len(decision.language_evidence_fingerprints) == 5
    assert registry.require_release(
        decision.fingerprint,
        deployment_manifest_fingerprint=_hash("1"),
        model_execution_identity_fingerprint=_hash("2"),
        tts_bundle_execution_identity_fingerprint=_hash("3"),
        runtime_attestation_bundle_fingerprint=_hash("4"),
    ).fingerprint == decision.fingerprint


def test_governed_release_rejects_cross_deployment_measurement_mix(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    records = []
    for language in CORE_LANGUAGES:
        deployment = _hash("a") if language == "fa" else _hash("1")
        records.append(
            registry.record_language(
                _evidence(language, deployment_manifest_fingerprint=deployment)
            )
        )
    with pytest.raises(ValueError, match="voice_release_decision_deployment_drift"):
        registry.record_release(
            language_evidence_fingerprints=[item.fingerprint for item in records],
            reviewer="release-reviewer",
            approval_reference="VOICE-RELEASE-002",
        )


def test_failed_metric_set_is_recorded_but_cannot_authorize_release(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    records = []
    for language in CORE_LANGUAGES:
        evaluation = _eval(language, p95_barge_in_ms=450) if language == "en" else _eval(language)
        records.append(registry.record_language(_evidence(language, evaluation=evaluation)))
    decision = registry.record_release(
        language_evidence_fingerprints=[item.fingerprint for item in records],
        reviewer="release-reviewer",
        approval_reference="VOICE-RELEASE-003",
    )
    assert decision.approved is False
    assert "voice_eval_en:barge_in_latency_too_high" in decision.violations
    with pytest.raises(ValueError, match="voice_release_decision_not_approved"):
        registry.require_release(decision.fingerprint)


def test_governed_release_lookup_rejects_runtime_attestation_drift(tmp_path):
    registry = VoiceReleaseEvidenceRegistry(tmp_path / "voice.db")
    records = _record_core(registry)
    decision = registry.record_release(
        language_evidence_fingerprints=[item.fingerprint for item in records],
        reviewer="release-reviewer",
        approval_reference="VOICE-RELEASE-004",
    )
    with pytest.raises(ValueError, match="voice_release_decision_runtime_attestation_mismatch"):
        registry.require_release(
            decision.fingerprint,
            runtime_attestation_bundle_fingerprint=_hash("f"),
        )
