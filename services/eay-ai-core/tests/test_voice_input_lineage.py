import pytest

from app.voice_input_lineage import VoiceInputLineageTracker
from app.voice_streaming import AudioFrame


def _hash(ch: str) -> str:
    return ch * 64


def _tracker(*, manifest: str = _hash("0")) -> VoiceInputLineageTracker:
    return VoiceInputLineageTracker(
        session_id="session-1",
        language="tr",
        deployment_manifest_fingerprint=manifest,
        wakeword_identity_fingerprint=_hash("1"),
        vad_identity_fingerprint=_hash("2"),
        stt_identity_fingerprint=_hash("3"),
    )


def test_voice_input_lineage_binds_wake_vad_audio_chain_and_stt():
    tracker = _tracker()
    wake = tracker.seal_wake()
    first = tracker.seal_audio_frame(
        AudioFrame(sequence=0, pcm_sha256=_hash("a"), duration_ms=20, sample_rate_hz=16000)
    )
    second = tracker.seal_audio_frame(
        AudioFrame(sequence=1, pcm_sha256=_hash("b"), duration_ms=20, sample_rate_hz=16000)
    )
    stt = tracker.seal_stt_final(text_sha256=_hash("c"))

    assert wake.deployment_manifest_fingerprint == _hash("0")
    assert first.vad_identity_fingerprint == _hash("2")
    assert second.previous_audio_chain_fingerprint == first.fingerprint
    assert stt.wake_proof_fingerprint == wake.fingerprint
    assert stt.vad_identity_fingerprint == _hash("2")
    assert stt.stt_identity_fingerprint == _hash("3")
    assert stt.audio_chain_fingerprint == second.fingerprint
    assert stt.audio_frame_count == 2
    assert stt.audio_duration_ms == 40
    assert stt.text_sha256 == _hash("c")
    assert len(stt.fingerprint) == 64


def test_voice_input_lineage_rejects_audio_before_wake():
    tracker = _tracker()
    with pytest.raises(ValueError, match="voice_input_wake_proof_required"):
        tracker.seal_audio_frame(
            AudioFrame(sequence=0, pcm_sha256=_hash("a"), duration_ms=20, sample_rate_hz=16000)
        )


def test_voice_input_lineage_changes_when_deployment_manifest_changes():
    left = _tracker(manifest=_hash("0"))
    right = _tracker(manifest=_hash("9"))
    left.seal_wake()
    right.seal_wake()
    left_proof = left.seal_stt_final(text_sha256=_hash("c"))
    right_proof = right.seal_stt_final(text_sha256=_hash("c"))
    assert left_proof.fingerprint != right_proof.fingerprint
    assert left_proof.audio_chain_fingerprint != right_proof.audio_chain_fingerprint


def test_voice_input_lineage_can_seal_no_frame_utterance_without_inventing_audio():
    tracker = _tracker()
    tracker.seal_wake()
    proof = tracker.seal_stt_final(text_sha256=_hash("c"))
    assert proof.audio_frame_count == 0
    assert proof.audio_duration_ms == 0
    assert len(proof.audio_chain_fingerprint) == 64
