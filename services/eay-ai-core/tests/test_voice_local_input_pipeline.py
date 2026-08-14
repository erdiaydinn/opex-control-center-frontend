import hashlib

import pytest

from app.voice_input_lineage import VoiceInputLineageTracker
from app.voice_local_audio_adapter import PinnedLocalSttAdapter, PinnedLocalVadAdapter
from app.voice_local_input_pipeline import VoiceLocalInputPipeline
from app.voice_runtime_attestation import VoiceRuntimeArtifactSeal


def _hash(ch: str) -> str:
    return ch * 64


def _seal(*, kind: str, manifest: str) -> VoiceRuntimeArtifactSeal:
    return VoiceRuntimeArtifactSeal(
        candidate_id="silero-vad-onnx" if kind == "vad" else "whisper-cpp-openai-whisper",
        adapter_id=f"{kind}-prod-v1",
        kind=kind,
        implementation="silero-vad-onnx" if kind == "vad" else "whisper.cpp",
        runtime_license_id="mit",
        artifact_license_id="mit",
        runtime_artifact_sha256=_hash("1"),
        runtime_artifact_size_bytes=10,
        model_or_voice_artifact_sha256=_hash("2"),
        adapter_fingerprint=_hash("3"),
        promotion_fingerprint=_hash("4"),
        deployment_manifest_fingerprint=manifest,
        fingerprint=_hash("5" if kind == "vad" else "6"),
    )


def _pcm(duration_ms: int = 32, fill: int = 9) -> bytearray:
    return bytearray([fill] * (16000 * duration_ms // 1000 * 2))


class _VadEngine:
    def __init__(self, probability: float):
        self.probability = probability

    def score(self, *, frames):
        assert all(frame.pcm.readonly for frame in frames)
        return self.probability


class _SttEngine:
    def transcribe(self, *, frames, language):
        assert language == "tr"
        assert len(frames) == 2
        return "Depo performansı iyi"


def _pipeline(*, vad_probability: float = 0.9, manifest: str | None = None):
    manifest = manifest or _hash("0")
    lineage = VoiceInputLineageTracker(
        session_id="session-local-input",
        language="tr",
        deployment_manifest_fingerprint=manifest,
        wakeword_identity_fingerprint=_hash("a"),
        vad_identity_fingerprint=_hash("b"),
        stt_identity_fingerprint=_hash("c"),
    )
    vad = PinnedLocalVadAdapter(runtime_seal=_seal(kind="vad", manifest=manifest), engine=_VadEngine(vad_probability))
    stt = PinnedLocalSttAdapter(runtime_seal=_seal(kind="stt", manifest=manifest), engine=_SttEngine())
    return VoiceLocalInputPipeline(
        session_id="session-local-input",
        language="tr",
        deployment_manifest_fingerprint=manifest,
        input_lineage=lineage,
        vad=vad,
        stt=stt,
    )


def test_local_input_pipeline_binds_pcm_vad_stt_and_hash_only_lineage():
    pipeline = _pipeline()
    wake = pipeline.wake()
    first = _pcm(fill=3)
    second = _pcm(fill=4)
    first_hash = hashlib.sha256(first).hexdigest()
    pipeline.push_pcm(sequence=0, pcm=first, duration_ms=32)
    pipeline.push_pcm(sequence=1, pcm=second, duration_ms=32)

    vad = pipeline.detect_speech(threshold=0.5)
    assert vad.speech_detected is True
    assert pipeline.audio.snapshot().buffered_frame_count == 2
    assert hashlib.sha256(first).hexdigest() == first_hash

    utterance = pipeline.finalize_utterance()

    assert utterance.text == "Depo performansı iyi"
    assert utterance.text_sha256 == hashlib.sha256(utterance.text.encode("utf-8")).hexdigest()
    assert utterance.proof.wake_proof_fingerprint == wake.fingerprint
    assert utterance.proof.audio_frame_count == 2
    assert utterance.proof.audio_duration_ms == 64
    assert utterance.proof.text_sha256 == utterance.text_sha256
    assert len(utterance.proof.fingerprint) == 64
    assert pipeline.audio.snapshot().buffered_frame_count == 0
    assert first == bytearray(len(first))
    assert second == bytearray(len(second))


def test_local_input_pipeline_fails_closed_without_detected_speech_and_retains_audio_for_retry():
    pipeline = _pipeline(vad_probability=0.1)
    pipeline.wake()
    owned = _pcm()
    pipeline.push_pcm(sequence=0, pcm=owned, duration_ms=32)
    result = pipeline.detect_speech(threshold=0.5)
    assert result.speech_detected is False

    with pytest.raises(ValueError, match="voice_local_pipeline_speech_not_detected"):
        pipeline.finalize_utterance()
    assert pipeline.audio.snapshot().buffered_frame_count == 1
    assert any(owned)

    pipeline.discard_utterance()
    assert owned == bytearray(len(owned))


def test_local_input_pipeline_rejects_cross_manifest_adapter_before_audio_acceptance():
    manifest = _hash("7")
    lineage = VoiceInputLineageTracker(
        session_id="session-local-input",
        language="tr",
        deployment_manifest_fingerprint=manifest,
        wakeword_identity_fingerprint=_hash("a"),
        vad_identity_fingerprint=_hash("b"),
        stt_identity_fingerprint=_hash("c"),
    )
    vad = PinnedLocalVadAdapter(runtime_seal=_seal(kind="vad", manifest=_hash("8")), engine=_VadEngine(0.9))
    stt = PinnedLocalSttAdapter(runtime_seal=_seal(kind="stt", manifest=manifest), engine=_SttEngine())

    with pytest.raises(ValueError, match="voice_local_pipeline_vad_manifest_mismatch"):
        VoiceLocalInputPipeline(
            session_id="session-local-input",
            language="tr",
            deployment_manifest_fingerprint=manifest,
            input_lineage=lineage,
            vad=vad,
            stt=stt,
        )
