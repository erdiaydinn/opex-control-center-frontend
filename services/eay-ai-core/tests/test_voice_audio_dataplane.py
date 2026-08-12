import hashlib

import pytest

from app.voice_audio_dataplane import VoiceAudioDataPlane


def _hash(ch: str = "0") -> str:
    return ch * 64


def _pcm(duration_ms: int = 20, sample_rate_hz: int = 16000, fill: int = 7) -> bytearray:
    size = sample_rate_hz * duration_ms // 1000 * 2
    return bytearray([fill] * size)


def test_audio_dataplane_owns_hashes_processes_in_memory_and_wipes_consumed_buffer():
    plane = VoiceAudioDataPlane(
        session_id="session-1",
        deployment_manifest_fingerprint=_hash(),
    )
    owned = _pcm(fill=9)
    expected_hash = hashlib.sha256(owned).hexdigest()
    receipt = plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)

    assert receipt.frame.pcm_sha256 == expected_hash
    assert receipt.buffered_frame_count == 1
    assert plane.snapshot().buffered_bytes == len(owned)

    def processor(frames):
        assert len(frames) == 1
        assert frames[0].pcm.readonly is True
        assert hashlib.sha256(frames[0].pcm).hexdigest() == expected_hash
        return frames[0].pcm_sha256

    assert plane.process_next(max_frames=1, processor=processor) == expected_hash
    assert plane.snapshot().buffered_bytes == 0
    assert plane.snapshot().buffered_frame_count == 0
    assert owned == bytearray(len(owned))


def test_audio_dataplane_wipes_even_when_processor_raises():
    plane = VoiceAudioDataPlane(session_id="session-2", deployment_manifest_fingerprint=_hash("1"))
    owned = _pcm(fill=3)
    plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)

    def processor(_frames):
        raise RuntimeError("engine failed")

    with pytest.raises(RuntimeError, match="engine failed"):
        plane.process_next(max_frames=1, processor=processor)
    assert owned == bytearray(len(owned))
    assert plane.snapshot().buffered_frame_count == 0


def test_audio_dataplane_rejects_immutable_input_and_sequence_replay():
    plane = VoiceAudioDataPlane(session_id="session-3", deployment_manifest_fingerprint=_hash("2"))
    with pytest.raises(TypeError, match="mutable_owned_buffer_required"):
        plane.push_owned_pcm(sequence=0, pcm=bytes(_pcm()), duration_ms=20, sample_rate_hz=16000)  # type: ignore[arg-type]

    plane.push_owned_pcm(sequence=0, pcm=_pcm(), duration_ms=20, sample_rate_hz=16000)
    with pytest.raises(ValueError, match="sequence_gap_or_replay"):
        plane.push_owned_pcm(sequence=0, pcm=_pcm(), duration_ms=20, sample_rate_hz=16000)


def test_audio_dataplane_enforces_pcm_shape_and_backpressure():
    plane = VoiceAudioDataPlane(
        session_id="session-4",
        deployment_manifest_fingerprint=_hash("3"),
        max_buffer_bytes=64 * 1024,
        max_frames=1,
    )
    with pytest.raises(ValueError, match="pcm_length_mismatch"):
        plane.push_owned_pcm(sequence=0, pcm=bytearray(10), duration_ms=20, sample_rate_hz=16000)

    owned = _pcm()
    plane.push_owned_pcm(sequence=0, pcm=owned, duration_ms=20, sample_rate_hz=16000)
    with pytest.raises(ValueError, match="frame_backpressure"):
        plane.push_owned_pcm(sequence=1, pcm=_pcm(), duration_ms=20, sample_rate_hz=16000)


def test_audio_dataplane_close_wipes_all_owned_pcm_and_blocks_reuse():
    first = _pcm(fill=1)
    second = _pcm(fill=2)
    plane = VoiceAudioDataPlane(session_id="session-5", deployment_manifest_fingerprint=_hash("4"))
    plane.push_owned_pcm(sequence=0, pcm=first, duration_ms=20, sample_rate_hz=16000)
    plane.push_owned_pcm(sequence=1, pcm=second, duration_ms=20, sample_rate_hz=16000)
    plane.close()

    assert first == bytearray(len(first))
    assert second == bytearray(len(second))
    assert plane.snapshot().closed is True
    with pytest.raises(ValueError, match="voice_audio_dataplane_closed"):
        plane.push_owned_pcm(sequence=2, pcm=_pcm(), duration_ms=20, sample_rate_hz=16000)
