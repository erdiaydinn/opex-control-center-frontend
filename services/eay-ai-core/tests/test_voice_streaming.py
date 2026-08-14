import pytest

from app.voice_runtime import VoiceState
from app.voice_streaming import AudioFrame, VoiceStreamingOrchestrator


def _frame(sequence: int, duration_ms: int = 100):
    return AudioFrame(
        sequence=sequence,
        pcm_sha256=(f"{sequence + 1:064x}")[-64:],
        duration_ms=duration_ms,
        sample_rate_hz=16000,
    )


def test_streaming_turn_flows_from_wake_to_stt_to_response():
    voice = VoiceStreamingOrchestrator(session_id="session-1", language="tr")
    assert voice.wake().state == VoiceState.LISTENING
    assert voice.push_audio(_frame(0)).buffered_ms == 100
    partial = voice.stt_partial("dünkü nsfr")
    assert len(partial.stt_partial_sha256 or "") == 64
    final = voice.stt_final("dünkü nsfr en kötü üç depo")
    assert final.state == VoiceState.THINKING
    assert len(final.stt_final_sha256 or "") == 64
    speaking = voice.begin_response("response-1")
    assert speaking.state == VoiceState.SPEAKING
    assert speaking.response_id == "response-1"


def test_rejects_frame_gap_and_replay():
    voice = VoiceStreamingOrchestrator(session_id="session-2", language="en")
    voice.wake()
    voice.push_audio(_frame(0))
    with pytest.raises(ValueError, match="sequence_gap_or_replay"):
        voice.push_audio(_frame(0))
    with pytest.raises(ValueError, match="sequence_gap_or_replay"):
        voice.push_audio(_frame(2))


def test_backpressure_is_bounded_and_consumption_releases_capacity():
    voice = VoiceStreamingOrchestrator(session_id="session-3", language="de", max_buffer_ms=200)
    voice.wake()
    voice.push_audio(_frame(0, 100))
    voice.push_audio(_frame(1, 100))
    with pytest.raises(ValueError, match="backpressure_limit"):
        voice.push_audio(_frame(2, 100))
    voice.consume_audio(100)
    assert voice.push_audio(_frame(2, 100)).buffered_ms == 200


def test_barge_in_cancels_active_response_and_returns_to_listening():
    voice = VoiceStreamingOrchestrator(session_id="session-4", language="ar")
    voice.wake()
    voice.stt_final("أخبرني عن الأداء")
    voice.begin_response("response-42")
    turn = voice.barge_in()
    assert turn.state == VoiceState.LISTENING
    assert turn.response_id is None
    assert turn.cancelled_response_id == "response-42"


def test_non_core_language_is_fail_closed_for_voice_runtime():
    with pytest.raises(ValueError, match="language_not_enabled"):
        VoiceStreamingOrchestrator(session_id="session-5", language="fr")
