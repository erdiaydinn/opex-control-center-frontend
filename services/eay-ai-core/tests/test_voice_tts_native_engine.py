import hashlib
from types import SimpleNamespace

import pytest

from app.voice_execution_identity import VoiceTtsExecutionIdentity
from app.voice_response_lineage import VoiceResponseGenerationProof, seal_tts_generation_proof
from app.voice_runtime_attestation import VoiceRuntimeArtifactSeal, seal_runtime_directory_manifest
from app.voice_tts_bundle import VoiceTtsBundleExecutionIdentity, VoiceTtsLanguageExecutionIdentity
from app.voice_tts_native_engine import SherpaOnnxVitsTtsEngine


def _hash(ch: str) -> str:
    return ch * 64


def _digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeSherpa:
    class OfflineTtsVitsModelConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class OfflineTtsModelConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    class OfflineTtsConfig:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

        def validate(self):
            return True

    class GenerationConfig:
        pass

    class OfflineTts:
        def __init__(self, config):
            self.config = config

        def generate(self, text, gen_config):
            return SimpleNamespace(samples=[0.0, 0.5, -0.5, 1.0, -1.0], sample_rate=22050)


def _fixtures(tmp_path):
    model = tmp_path / "voice.onnx"
    config = tmp_path / "voice.onnx.json"
    tokens = tmp_path / "tokens.txt"
    model_card = tmp_path / "MODEL_CARD"
    model.write_bytes(b"voice-model")
    config.write_bytes(b"voice-config")
    tokens.write_bytes(b"voice-tokens")
    model_card.write_bytes(b"voice-license-card")

    data_dir = tmp_path / "espeak-ng-data"
    (data_dir / "lang").mkdir(parents=True)
    (data_dir / "phontab").write_bytes(b"phoneme-table")
    (data_dir / "lang" / "tr").write_bytes(b"turkish-phoneme-data")
    resource_manifest = seal_runtime_directory_manifest(data_dir, logical_name="espeak-ng-data")

    tr = VoiceTtsLanguageExecutionIdentity(
        language="tr",
        voice_id_sha256=_hash("1"),
        model_sha256=_digest(model),
        config_sha256=_digest(config),
        tokens_sha256=_digest(tokens),
        model_card_sha256=_digest(model_card),
        artifact_license_id_sha256=_hash("2"),
        artifact_fingerprint=_hash("3"),
        fingerprint=_hash("4"),
    )
    others = tuple(
        VoiceTtsLanguageExecutionIdentity(
            language=language,
            voice_id_sha256=_hash("1"),
            model_sha256=_hash(ch),
            config_sha256=_hash("5"),
            tokens_sha256=_hash("6"),
            model_card_sha256=_hash("7"),
            artifact_license_id_sha256=_hash("2"),
            artifact_fingerprint=_hash("3"),
            fingerprint=_hash(ch),
        )
        for language, ch in zip(("en", "de", "ar", "fa"), ("a", "b", "c", "d"))
    )
    bundle = VoiceTtsBundleExecutionIdentity(
        bundle_fingerprint=_hash("e"),
        bundle_promotion_fingerprint=_hash("f"),
        runtime_adapter_id="tts-local-v1",
        runtime_adapter_promotion_fingerprint=_hash("9"),
        profile_fingerprint=_hash("8"),
        phonemizer_data_manifest_fingerprint=resource_manifest.fingerprint,
        phonemizer_license_id_sha256=_hash("7"),
        phonemizer_source_sha256=_hash("6"),
        language_artifacts=(tr,) + others,
        fingerprint=_hash("5"),
    )
    bundle.validate()

    runtime = VoiceRuntimeArtifactSeal(
        candidate_id="sherpa-onnx-piper-vits",
        adapter_id="tts-local-v1",
        kind="tts",
        implementation="sherpa-onnx-vits",
        runtime_license_id="apache-2.0",
        artifact_license_id="mit",
        runtime_artifact_sha256=_hash("1"),
        runtime_artifact_size_bytes=100,
        model_or_voice_artifact_sha256=_hash("2"),
        adapter_fingerprint=_hash("3"),
        promotion_fingerprint=_hash("9"),
        deployment_manifest_fingerprint=_hash("0"),
        fingerprint=_hash("4"),
    )
    runtime.validate()

    tts_identity = VoiceTtsExecutionIdentity(
        adapter_id="tts-local-v1",
        implementation="sherpa-onnx-vits",
        license_id="apache-2.0",
        license_id_sha256=_hash("1"),
        artifact_sha256=_hash("2"),
        adapter_fingerprint=_hash("3"),
        promotion_fingerprint=_hash("9"),
        profile_fingerprint=_hash("8"),
        language_capability_fingerprints=(_hash("4"),),
        fingerprint=_hash("5"),
    )
    response = VoiceResponseGenerationProof(
        session_id="session-tts",
        turn_epoch=1,
        user_input_sha256=_hash("a"),
        input_lineage_fingerprint=_hash("b"),
        accepted_tool_result_fingerprints=(),
        governed_tool_provenance_fingerprints=(),
        legal_context_fingerprint=None,
        kpi_context_fingerprint=None,
        deployment_manifest_fingerprint=_hash("0"),
        model_execution_identity_fingerprint=_hash("c"),
        model_artifact_sha256=_hash("d"),
        fingerprint=_hash("e"),
    )
    text = "Merhaba, EAY ses testi."
    proof = seal_tts_generation_proof(
        response_proof=response,
        current_turn_epoch=1,
        language="tr",
        deployment_manifest_fingerprint=_hash("0"),
        response_text_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        voice_profile_fingerprint=_hash("8"),
        tts_execution_identity=tts_identity,
        tts_bundle_execution_identity=bundle,
    )
    return runtime, bundle, proof, text, model, config, tokens, model_card, data_dir


def _engine(tmp_path):
    runtime, bundle, proof, text, model, config, tokens, model_card, data_dir = _fixtures(tmp_path)
    engine = SherpaOnnxVitsTtsEngine(
        runtime_seal=runtime,
        bundle_identity=bundle,
        language="tr",
        model_path=model,
        config_path=config,
        tokens_path=tokens,
        model_card_path=model_card,
        phonemizer_data_dir=data_dir,
        sherpa_module=FakeSherpa,
    )
    return engine, proof, text, tokens, data_dir


def test_sherpa_tts_builds_pinned_vits_config_and_returns_ram_only_pcm(tmp_path):
    engine, proof, text, _, _ = _engine(tmp_path)
    vits = engine._tts.config.model.vits
    assert vits.model.endswith("voice.onnx")
    assert vits.tokens.endswith("tokens.txt")
    assert vits.data_dir.endswith("espeak-ng-data")

    output = engine.synthesize(text=text, proof=proof)
    assert output.language == "tr"
    assert output.sample_rate_hz == 22050
    assert output.sample_count == 5
    assert len(output.pcm_sha256) == 64
    assert output.audio_duration_ms > 0
    assert output.real_time_factor >= 0
    view = output.view()
    assert view.nbytes == 10
    view.release()
    output.close()
    assert output.closed is True
    assert output._pcm == bytearray(10)
    with pytest.raises(ValueError, match="voice_tts_pcm_closed"):
        output.view()


def test_sherpa_tts_rejects_tokens_drift_before_engine_creation(tmp_path):
    runtime, bundle, _, _, model, config, tokens, model_card, data_dir = _fixtures(tmp_path)
    tokens.write_bytes(b"tampered-tokens")
    with pytest.raises(ValueError, match="voice_sherpa_tts_tokens_hash_mismatch"):
        SherpaOnnxVitsTtsEngine(
            runtime_seal=runtime,
            bundle_identity=bundle,
            language="tr",
            model_path=model,
            config_path=config,
            tokens_path=tokens,
            model_card_path=model_card,
            phonemizer_data_dir=data_dir,
            sherpa_module=FakeSherpa,
        )


def test_sherpa_tts_rejects_phonemizer_resource_drift(tmp_path):
    runtime, bundle, _, _, model, config, tokens, model_card, data_dir = _fixtures(tmp_path)
    (data_dir / "phontab").write_bytes(b"tampered-phoneme-table")
    with pytest.raises(ValueError, match="voice_sherpa_tts_phonemizer_manifest_mismatch"):
        SherpaOnnxVitsTtsEngine(
            runtime_seal=runtime,
            bundle_identity=bundle,
            language="tr",
            model_path=model,
            config_path=config,
            tokens_path=tokens,
            model_card_path=model_card,
            phonemizer_data_dir=data_dir,
            sherpa_module=FakeSherpa,
        )


def test_sherpa_tts_rejects_text_not_bound_to_proof(tmp_path):
    engine, proof, _, _, _ = _engine(tmp_path)
    with pytest.raises(ValueError, match="voice_sherpa_tts_text_hash_mismatch"):
        engine.synthesize(text="different response", proof=proof)


def test_sherpa_tts_rejects_deployment_manifest_mismatch(tmp_path):
    engine, proof, text, _, _ = _engine(tmp_path)
    drifted = VoiceRuntimeArtifactSeal(
        **{**engine.runtime_seal.__dict__, "deployment_manifest_fingerprint": _hash("1")}
    )
    drifted.validate()
    engine.runtime_seal = drifted
    with pytest.raises(ValueError, match="voice_sherpa_tts_deployment_manifest_mismatch"):
        engine.synthesize(text=text, proof=proof)
