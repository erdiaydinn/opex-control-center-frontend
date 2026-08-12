import hashlib

import pytest

from app.voice_adapter_candidates import candidate_by_id
from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_audio_dataplane import VoiceAudioDataPlane
from app.voice_local_audio_adapter import PinnedLocalSttAdapter, PinnedLocalVadAdapter
from app.voice_runtime_attestation import seal_local_voice_runtime


def _hash(ch: str) -> str:
    return ch * 64


def _pcm(fill: int = 5) -> bytearray:
    return bytearray([fill] * (16000 * 20 // 1000 * 2))


def _promotion(adapter, ch: str) -> VoiceAdapterPromotion:
    return VoiceAdapterPromotion(
        adapter_id=adapter.adapter_id,
        kind=adapter.kind,
        adapter_artifact_sha256=adapter.artifact_sha256,
        adapter_fingerprint=adapter_fingerprint(adapter),
        profile_fingerprint=_hash("b"),
        language_capability_fingerprints=(_hash("c"),),
        reviewer="voice-reviewer",
        approval_reference="VOICE-LOCAL-001",
        promoted_at="2026-08-12T09:00:00+00:00",
        fingerprint=_hash(ch),
    )


def _runtime_seal(tmp_path, *, candidate_id: str, adapter_id: str, artifact_hash: str, promotion_ch: str, manifest: str):
    candidate = candidate_by_id(candidate_id)
    adapter = candidate.build_spec(adapter_id=adapter_id, artifact_sha256=artifact_hash)
    runtime = tmp_path / f"{adapter_id}.runtime"
    runtime.write_bytes((candidate_id + "-runtime").encode("utf-8"))
    runtime_sha = hashlib.sha256(runtime.read_bytes()).hexdigest()
    return seal_local_voice_runtime(
        candidate_id=candidate_id,
        adapter=adapter,
        promotion=_promotion(adapter, promotion_ch),
        deployment_manifest_fingerprint=manifest,
        runtime_artifact_path=runtime,
        expected_runtime_artifact_sha256=runtime_sha,
    )


def test_pinned_vad_inspects_ram_without_destroying_audio_needed_by_stt(tmp_path):
    manifest = _hash("0")
    seal = _runtime_seal(
        tmp_path,
        candidate_id="silero-vad-onnx",
        adapter_id="vad-prod-v1",
        artifact_hash=_hash("1"),
        promotion_ch="2",
        manifest=manifest,
    )

    class VadEngine:
        def score(self, *, frames):
            assert frames[0].pcm.readonly is True
            assert any(frames[0].pcm)
            return 0.91

    owned = _pcm()
    plane = VoiceAudioDataPlane(session_id="session-vad", deployment_manifest_fingerprint=manifest)
    plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)
    result = PinnedLocalVadAdapter(runtime_seal=seal, engine=VadEngine()).detect(
        audio=plane,
        max_frames=1,
        threshold=0.6,
    )

    assert result.speech_detected is True
    assert result.speech_probability == 0.91
    assert result.runtime_seal_fingerprint == seal.fingerprint
    assert len(result.input_audio_fingerprint) == 64
    assert plane.snapshot().buffered_frame_count == 1
    assert any(owned)
    plane.discard_all()
    assert owned == bytearray(len(owned))


def test_pinned_stt_returns_transient_text_but_provenance_is_hash_only(tmp_path):
    manifest = _hash("3")
    seal = _runtime_seal(
        tmp_path,
        candidate_id="whisper-cpp-openai-whisper",
        adapter_id="stt-prod-v1",
        artifact_hash=_hash("4"),
        promotion_ch="5",
        manifest=manifest,
    )

    class SttEngine:
        def transcribe(self, *, frames, language):
            assert language == "tr"
            assert len(frames) == 1
            return "  Depo performansı iyi.  "

    owned = _pcm(fill=8)
    plane = VoiceAudioDataPlane(session_id="session-stt", deployment_manifest_fingerprint=manifest)
    plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)
    result = PinnedLocalSttAdapter(runtime_seal=seal, engine=SttEngine()).transcribe(
        audio=plane,
        max_frames=1,
        language="tr",
    )

    assert result.text == "Depo performansı iyi."
    assert result.text_sha256 == hashlib.sha256(result.text.encode("utf-8")).hexdigest()
    assert result.runtime_seal_fingerprint == seal.fingerprint
    assert len(result.fingerprint) == 64
    assert owned == bytearray(len(owned))


def test_local_adapter_rejects_cross_deployment_audio(tmp_path):
    seal = _runtime_seal(
        tmp_path,
        candidate_id="silero-vad-onnx",
        adapter_id="vad-prod-v2",
        artifact_hash=_hash("6"),
        promotion_ch="7",
        manifest=_hash("8"),
    )

    class VadEngine:
        def score(self, *, frames):
            return 0.5

    plane = VoiceAudioDataPlane(session_id="session-cross", deployment_manifest_fingerprint=_hash("9"))
    plane.push_owned_pcm(sequence=0, pcm=_pcm(), duration_ms=20, sample_rate_hz=16000)
    with pytest.raises(ValueError, match="voice_local_vad_deployment_manifest_mismatch"):
        PinnedLocalVadAdapter(runtime_seal=seal, engine=VadEngine()).detect(audio=plane, max_frames=1)


def test_local_stt_rejects_unsupported_language_before_audio_consumption(tmp_path):
    manifest = _hash("a")
    seal = _runtime_seal(
        tmp_path,
        candidate_id="whisper-cpp-openai-whisper",
        adapter_id="stt-prod-v2",
        artifact_hash=_hash("b"),
        promotion_ch="c",
        manifest=manifest,
    )

    class SttEngine:
        def transcribe(self, *, frames, language):
            return "should not run"

    owned = _pcm()
    plane = VoiceAudioDataPlane(session_id="session-lang", deployment_manifest_fingerprint=manifest)
    plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)
    with pytest.raises(ValueError, match="voice_local_stt_language_not_enabled"):
        PinnedLocalSttAdapter(runtime_seal=seal, engine=SttEngine()).transcribe(
            audio=plane,
            max_frames=1,
            language="xx",
        )
    assert plane.snapshot().buffered_frame_count == 1
    assert any(owned)
