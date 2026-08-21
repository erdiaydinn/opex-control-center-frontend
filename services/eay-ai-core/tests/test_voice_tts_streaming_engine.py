import hashlib
from pathlib import Path

import pytest

from app.voice_async_runtime import CancellationToken
from app.voice_execution_identity import VoiceTtsExecutionIdentity
from app.voice_response_lineage import VoiceResponseGenerationProof, seal_tts_generation_proof
from app.voice_runtime_attestation import VoiceRuntimeArtifactSeal, seal_runtime_directory_manifest
from app.voice_tts_bundle import VoiceTtsBundleExecutionIdentity, VoiceTtsLanguageExecutionIdentity
from app.voice_tts_streaming_engine import SherpaOnnxStreamingVitsTtsEngine


def _hash(ch: str) -> str:
    return ch * 64


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeStreamingShim:
    def __init__(self):
        self.destroyed = False
        self.create_args = None
        self.callback_count = 0

    def abi_version(self):
        return 1

    def create(self, **kwargs):
        self.create_args = kwargs
        return object()

    def sample_rate(self, handle):
        return 22050

    def generate(self, *, handle, text, sid, speed, silence_scale, on_chunk):
        for samples, progress in (
            ((0.0, 0.5, -0.5), 0.5),
            ((1.0, -1.0, 0.25), 1.0),
        ):
            self.callback_count += 1
            if not on_chunk(samples, progress):
                return 1
        return 0

    def destroy(self, handle):
        self.destroyed = True


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
        session_id="session-stream-tts",
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
    text = "Merhaba, akışlı EAY ses testi."
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


def _engine(tmp_path, shim=None):
    runtime, bundle, proof, text, model, config, tokens, model_card, data_dir = _fixtures(tmp_path)
    shim = shim or FakeStreamingShim()
    engine = SherpaOnnxStreamingVitsTtsEngine(
        runtime_seal=runtime,
        bundle_identity=bundle,
        language="tr",
        model_path=model,
        config_path=config,
        tokens_path=tokens,
        model_card_path=model_card,
        phonemizer_data_dir=data_dir,
        shim=shim,
    )
    return engine, shim, proof, text


def test_streaming_tts_emits_ephemeral_pcm_chunks_and_hash_only_result(tmp_path):
    engine, shim, proof, text = _engine(tmp_path)
    retained = []
    observed_hashes = []

    def consume(chunk):
        retained.append(chunk)
        view = chunk.view()
        observed_hashes.append(hashlib.sha256(view).hexdigest())
        view.release()
        return True

    result = engine.stream_synthesize(text=text, proof=proof, on_pcm_chunk=consume)
    assert result.language == "tr"
    assert result.sample_rate_hz == 22050
    assert result.chunk_count == 2
    assert result.sample_count == 6
    assert result.first_audio_latency_ms >= 0
    assert result.audio_duration_ms > 0
    assert result.real_time_factor >= 0
    assert len(result.audio_chain_fingerprint) == 64
    assert observed_hashes == [chunk.pcm_sha256 for chunk in retained]
    assert all(chunk.closed for chunk in retained)
    assert all(chunk._pcm == bytearray(chunk.sample_count * 2) for chunk in retained)
    with pytest.raises(ValueError, match="voice_tts_stream_chunk_closed"):
        retained[0].view()
    engine.close()
    assert shim.destroyed is True


def test_streaming_tts_cancellation_stops_native_generation_on_next_chunk(tmp_path):
    engine, shim, proof, text = _engine(tmp_path)
    token = CancellationToken(task_id="tts-1", turn_epoch=1)
    seen = []

    def consume(chunk):
        seen.append(chunk.sequence)
        token.cancel()
        return True

    with pytest.raises(RuntimeError, match="voice_sherpa_stream_generation_cancelled"):
        engine.stream_synthesize(text=text, proof=proof, on_pcm_chunk=consume, cancellation=token)
    assert seen == [0]
    assert shim.callback_count == 2


def test_streaming_tts_consumer_stop_propagates_to_native_callback(tmp_path):
    engine, shim, proof, text = _engine(tmp_path)
    with pytest.raises(RuntimeError, match="voice_sherpa_stream_generation_cancelled"):
        engine.stream_synthesize(text=text, proof=proof, on_pcm_chunk=lambda chunk: False)
    assert shim.callback_count == 1


def test_streaming_tts_rejects_tampered_tokens_before_native_context(tmp_path):
    runtime, bundle, _, _, model, config, tokens, model_card, data_dir = _fixtures(tmp_path)
    tokens.write_bytes(b"tampered-tokens")
    shim = FakeStreamingShim()
    with pytest.raises(ValueError, match="voice_sherpa_stream_tokens_hash_mismatch"):
        SherpaOnnxStreamingVitsTtsEngine(
            runtime_seal=runtime,
            bundle_identity=bundle,
            language="tr",
            model_path=model,
            config_path=config,
            tokens_path=tokens,
            model_card_path=model_card,
            phonemizer_data_dir=data_dir,
            shim=shim,
        )
    assert shim.create_args is None


def test_native_shim_uses_current_generate_with_config_callback_api():
    source = Path("native/eay_sherpa_tts_shim.cpp").read_text(encoding="utf-8")
    assert "SherpaOnnxOfflineTtsGenerateWithConfig" in source
    assert "SherpaOnnxGeneratedAudioProgressCallbackWithArg" not in source  # callback type stays behind EAY ABI
    assert "SherpaOnnxOfflineTtsGenerateWithProgressCallback" not in source
    assert "SherpaOnnxOfflineTtsGenerateWithCallback" not in source
    assert "SherpaOnnxDestroyOfflineTtsGeneratedAudio" in source
