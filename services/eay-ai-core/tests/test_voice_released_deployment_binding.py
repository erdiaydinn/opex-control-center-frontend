from types import SimpleNamespace

import pytest

import app.voice_deployment_binding as binding
from app.voice_deployment_binding import (
    VoiceDeploymentExecutionBindings,
    _VerifiedDeploymentBuild,
    _VerifiedDeploymentSource,
    clear_voice_deployment_bindings,
    configure_released_voice_deployment,
    require_voice_deployment_bindings,
)
from app.voice_deployment_manifest import VoiceRuntimeDeploymentManifest
from app.voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity
from app.voice_release_evidence import VoiceReleaseEvidenceRegistry, seal_voice_language_measurement_evidence
from app.voice_release_gate import VoiceLanguageEval
from app.voice_runtime import CORE_LANGUAGES
from app.voice_tts_bundle import VoiceTtsBundleExecutionIdentity, VoiceTtsLanguageExecutionIdentity


def _hash(ch: str) -> str:
    return ch * 64


def _tts_bundle_identity():
    artifacts = tuple(
        VoiceTtsLanguageExecutionIdentity(
            language=language,
            voice_id_sha256=_hash("1"),
            model_sha256=_hash(ch),
            config_sha256=_hash("2"),
            tokens_sha256=_hash("3"),
            model_card_sha256=_hash("4"),
            artifact_license_id_sha256=_hash("5"),
            artifact_fingerprint=_hash("6"),
            fingerprint=_hash(ch),
        )
        for language, ch in zip(CORE_LANGUAGES, ("a", "b", "c", "d", "e"))
    )
    result = VoiceTtsBundleExecutionIdentity(
        bundle_fingerprint=_hash("7"),
        bundle_promotion_fingerprint=_hash("8"),
        runtime_adapter_id="tts-prod-v1",
        runtime_adapter_promotion_fingerprint=_hash("9"),
        profile_fingerprint=_hash("a"),
        phonemizer_data_manifest_fingerprint=_hash("b"),
        phonemizer_license_id_sha256=_hash("c"),
        phonemizer_source_sha256=_hash("d"),
        language_artifacts=artifacts,
        fingerprint=_hash("e"),
    )
    result.validate()
    return result


def _build():
    tts_bundle = _tts_bundle_identity()
    model = VoiceModelExecutionIdentity(
        artifact_sha256=_hash("1"),
        artifact_provenance_fingerprint=_hash("2"),
        training_job_fingerprint=_hash("3"),
        artifact_format="gguf",
        build_reference_sha256=_hash("4"),
        fingerprint=_hash("5"),
    )
    tts = VoiceTtsExecutionIdentity(
        adapter_id="tts-prod-v1",
        implementation="sherpa-onnx-vits",
        license_id="apache-2.0",
        license_id_sha256=_hash("6"),
        artifact_sha256=_hash("7"),
        adapter_fingerprint=_hash("8"),
        promotion_fingerprint=_hash("9"),
        profile_fingerprint=_hash("a"),
        language_capability_fingerprints=(_hash("b"),),
        fingerprint=_hash("c"),
    )
    manifest = VoiceRuntimeDeploymentManifest(
        model_record_id="model-prod",
        model_production_promotion_fingerprint=_hash("1"),
        model_release_proof_fingerprint=_hash("2"),
        model_execution_identity_fingerprint=model.fingerprint,
        model_artifact_sha256=model.artifact_sha256,
        profile_fingerprint=_hash("a"),
        adapter_identity_fingerprints=(_hash("d"), _hash("e"), _hash("f"), _hash("1")),
        wakeword_identity_fingerprint=_hash("d"),
        vad_identity_fingerprint=_hash("e"),
        stt_identity_fingerprint=_hash("f"),
        tts_identity_fingerprint=_hash("1"),
        tts_bundle_execution_identity_fingerprint=tts_bundle.fingerprint,
        tts_bundle_fingerprint=tts_bundle.bundle_fingerprint,
        tts_bundle_promotion_fingerprint=tts_bundle.bundle_promotion_fingerprint,
        tts_language_artifact_fingerprints=tuple(item.fingerprint for item in tts_bundle.language_artifacts),
        fingerprint=_hash("0"),
    )
    bindings = VoiceDeploymentExecutionBindings(
        model=model,
        tts=tts,
        deployment_manifest_fingerprint=manifest.fingerprint,
        wakeword_identity_fingerprint=manifest.wakeword_identity_fingerprint,
        vad_identity_fingerprint=manifest.vad_identity_fingerprint,
        stt_identity_fingerprint=manifest.stt_identity_fingerprint,
        model_record_id="model-prod",
        tts_bundle=tts_bundle,
    )
    bindings.validate()
    source = _VerifiedDeploymentSource(
        db_path=SimpleNamespace(),
        model_record_id="model-prod",
        profile=SimpleNamespace(),
        capabilities=(),
        tts_bundle=SimpleNamespace(),
    )
    return _VerifiedDeploymentBuild(manifest=manifest, bindings=bindings, source=source)


def _evaluation(language):
    return VoiceLanguageEval(
        language=language,
        sample_count=100,
        stt_word_error_rate=0.05,
        semantic_consistency_rate=0.995,
        human_naturalness_score=4.5,
        citation_readback_accuracy=1.0,
        p95_first_audio_ms=500,
        p95_barge_in_ms=150,
        interruption_success_rate=1.0,
        p95_cancel_propagation_ms=100,
        approval_replay_accept_count=0,
    )


def _release(db_path, build, runtime_fp):
    registry = VoiceReleaseEvidenceRegistry(db_path)
    records = []
    for language in CORE_LANGUAGES:
        evidence = seal_voice_language_measurement_evidence(
            evaluation=_evaluation(language),
            deployment_manifest_fingerprint=build.manifest.fingerprint,
            model_execution_identity_fingerprint=build.bindings.model.fingerprint,
            tts_bundle_execution_identity_fingerprint=build.bindings.tts_bundle.fingerprint,
            runtime_attestation_bundle_fingerprint=runtime_fp,
            eval_suite_sha256=_hash("1"),
            measurement_harness_sha256=_hash("2"),
            runtime_environment_fingerprint=_hash("3"),
            raw_measurement_manifest_sha256=_hash("4"),
            human_review_manifest_sha256=_hash("5"),
            reviewer="human-reviewer",
            approval_reference=f"MEASURE-{language}",
        )
        records.append(registry.record_language(evidence))
    return registry.record_release(
        language_evidence_fingerprints=[item.fingerprint for item in records],
        reviewer="release-reviewer",
        approval_reference="VOICE-RELEASE-PROD",
    )


@pytest.fixture(autouse=True)
def _reset_bindings():
    clear_voice_deployment_bindings()
    yield
    clear_voice_deployment_bindings()


def test_released_deployment_installs_only_after_exact_approved_evidence(tmp_path, monkeypatch):
    build = _build()
    runtime_fp = _hash("f")
    decision = _release(tmp_path / "voice.db", build, runtime_fp)
    runtime_bundle = SimpleNamespace(
        fingerprint=runtime_fp,
        assert_matches_deployment=lambda **kwargs: None,
    )
    monkeypatch.setattr(binding, "_build_verified_deployment", lambda **kwargs: build)

    manifest, verified = configure_released_voice_deployment(
        db_path=tmp_path / "voice.db",
        model_record_id="model-prod",
        profile=SimpleNamespace(),
        capabilities=(),
        tts_bundle=SimpleNamespace(),
        runtime_attestation_bundle=runtime_bundle,
        governed_release_decision_fingerprint=decision.fingerprint,
    )
    installed = require_voice_deployment_bindings(require_production_release=True)
    assert manifest.fingerprint == build.manifest.fingerprint
    assert verified.fingerprint == decision.fingerprint
    assert installed.production_released is True
    assert installed.governed_release_decision_fingerprint == decision.fingerprint
    assert installed.runtime_attestation_bundle_fingerprint == runtime_fp


def test_failed_release_verification_never_installs_partial_global_binding(tmp_path, monkeypatch):
    build = _build()
    runtime_bundle = SimpleNamespace(
        fingerprint=_hash("f"),
        assert_matches_deployment=lambda **kwargs: None,
    )
    monkeypatch.setattr(binding, "_build_verified_deployment", lambda **kwargs: build)

    with pytest.raises(KeyError, match="voice_release_decision_not_found"):
        configure_released_voice_deployment(
            db_path=tmp_path / "voice.db",
            model_record_id="model-prod",
            profile=SimpleNamespace(),
            capabilities=(),
            tts_bundle=SimpleNamespace(),
            runtime_attestation_bundle=runtime_bundle,
            governed_release_decision_fingerprint=_hash("a"),
        )
    with pytest.raises(ValueError, match="voice_execution_identity_unconfigured"):
        require_voice_deployment_bindings()


def test_staging_verified_binding_cannot_claim_production_release(tmp_path, monkeypatch):
    build = _build()
    monkeypatch.setattr(binding, "_build_verified_deployment", lambda **kwargs: build)
    binding.configure_verified_voice_deployment(
        db_path=tmp_path / "voice.db",
        model_record_id="model-prod",
        profile=SimpleNamespace(),
        capabilities=(),
        tts_bundle=SimpleNamespace(),
    )
    with pytest.raises(ValueError, match="voice_deployment_production_release_required"):
        require_voice_deployment_bindings(require_production_release=True)
