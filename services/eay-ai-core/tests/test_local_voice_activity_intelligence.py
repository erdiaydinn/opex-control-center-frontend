from datetime import datetime, timedelta, timezone

import pytest

from app.local_voice_activity import LocalVoiceActivityGate, VoiceActivityState
from app.local_voice_runtime import TransientAudioFrame

NOW = datetime(2026, 8, 18, 12, 50, tzinfo=timezone.utc)


def _frame(sequence, amplitude):
    sample = int(max(-32768, min(32767, amplitude)))
    return TransientAudioFrame(
        pcm16=sample.to_bytes(2, "little", signed=True) * 160,
        captured_at=NOW + timedelta(milliseconds=sequence * 10),
        sequence=sequence,
    )


def test_voice_activity_requires_sustained_speech_and_detects_endpoint():
    gate = LocalVoiceActivityGate(
        rms_threshold=0.02,
        minimum_speech_frames=2,
        end_silence_frames=3,
    )
    assert gate.consume(_frame(1, 0)).state is VoiceActivityState.SILENCE
    assert gate.consume(_frame(2, 3000)).state is VoiceActivityState.SILENCE
    assert gate.consume(_frame(3, 3000)).state is VoiceActivityState.SPEECH
    assert gate.consume(_frame(4, 0)).state is VoiceActivityState.SPEECH
    assert gate.consume(_frame(5, 0)).state is VoiceActivityState.SPEECH
    ended = gate.consume(_frame(6, 0))
    assert ended.state is VoiceActivityState.UTTERANCE_ENDED
    assert ended.raw_audio_retained is False
    assert ended.speaker_identity_inferred is False
    assert ended.command_authorized is False


def test_vad_is_not_identity_or_command_authority():
    gate = LocalVoiceActivityGate(rms_threshold=0.01, minimum_speech_frames=1)
    observation = gate.consume(_frame(1, 5000))
    assert observation.state is VoiceActivityState.SPEECH
    assert observation.speaker_identity_inferred is False
    assert observation.command_authorized is False
    serialized = observation.model_dump_json()
    assert "5000" not in serialized


def test_vad_sequence_must_be_monotonic():
    gate = LocalVoiceActivityGate()
    gate.consume(_frame(2, 0))
    with pytest.raises(ValueError, match="sequence_must_increase"):
        gate.consume(_frame(2, 0))
