import pytest

from app.voice_ws_protocol import VoiceWsSequenceGuard, seal_envelope


def test_voice_ws_envelope_is_deterministically_sealed():
    item = seal_envelope(
        session_id="session-1",
        message_id="msg-1",
        event="audio_frame",
        sequence=0,
        payload={"pcm_sha256": "a" * 64, "duration_ms": 20},
    )
    assert len(item.payload_sha256) == 64
    assert len(item.fingerprint) == 64
    assert item.protocol_version == "eay-voice-ws-v1"


def test_voice_ws_rejects_raw_audio_or_transcript_content():
    with pytest.raises(ValueError, match="voice_ws_raw_content_forbidden"):
        seal_envelope(
            session_id="session-1",
            message_id="msg-2",
            event="audio_frame",
            sequence=0,
            payload={"raw_audio": "bytes"},
        )
    with pytest.raises(ValueError, match="voice_ws_raw_content_forbidden"):
        seal_envelope(
            session_id="session-1",
            message_id="msg-3",
            event="stt_final",
            sequence=0,
            payload={"transcript": "secret"},
        )


def test_voice_ws_sequence_guard_rejects_replay_and_gap():
    guard = VoiceWsSequenceGuard()
    first = seal_envelope(
        session_id="session-2", message_id="msg-1", event="wake", sequence=0, payload={}
    )
    guard.accept(first)
    replay = seal_envelope(
        session_id="session-2", message_id="msg-2", event="wake", sequence=0, payload={}
    )
    with pytest.raises(ValueError, match="voice_ws_sequence_gap_or_replay"):
        guard.accept(replay)
    gap = seal_envelope(
        session_id="session-2", message_id="msg-3", event="wake", sequence=2, payload={}
    )
    with pytest.raises(ValueError, match="voice_ws_sequence_gap_or_replay"):
        guard.accept(gap)
