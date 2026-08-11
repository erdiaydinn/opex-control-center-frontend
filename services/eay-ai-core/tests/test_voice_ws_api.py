from fastapi.testclient import TestClient

from app.entrypoint import app


def _hash(ch: str = "a") -> str:
    return ch * 64


def test_voice_websocket_wake_and_hashed_audio_flow():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-1?language=tr") as ws:
        ready = ws.receive_json()
        assert ready["event"] == "ready"
        assert ready["protocol_version"] == "eay-voice-ws-v1"

        ws.send_json({"event": "wake", "sequence": 0, "message_id": "msg-0", "payload": {}})
        listening = ws.receive_json()
        assert listening["event"] == "listening"
        assert listening["state"] == "listening"
        assert len(listening["envelope_fingerprint"]) == 64

        ws.send_json(
            {
                "event": "audio_frame",
                "sequence": 1,
                "message_id": "msg-1",
                "payload": {
                    "frame_sequence": 0,
                    "pcm_sha256": _hash("b"),
                    "duration_ms": 20,
                    "sample_rate_hz": 16000,
                },
            }
        )
        frame = ws.receive_json()
        assert frame["event"] == "listening"
        assert frame["state"] == "listening"


def test_voice_websocket_rejects_raw_content_and_sequence_replay():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-2?language=en") as ws:
        ws.receive_json()
        ws.send_json(
            {
                "event": "wake",
                "sequence": 0,
                "message_id": "msg-0",
                "transcript": "must never enter the control plane",
                "payload": {},
            }
        )
        rejected = ws.receive_json()
        assert rejected == {"event": "error", "code": "voice_ws_raw_content_forbidden"}

        ws.send_json({"event": "wake", "sequence": 0, "message_id": "msg-1", "payload": {}})
        assert ws.receive_json()["event"] == "listening"
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "msg-2", "payload": {}})
        replay = ws.receive_json()
        assert replay["event"] == "error"
        assert replay["code"] == "voice_ws_sequence_gap_or_replay"


def test_voice_websocket_stt_final_keeps_only_hash_metadata():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-3?language=de") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "msg-0", "payload": {}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "stt_final",
                "sequence": 1,
                "message_id": "msg-1",
                "payload": {"text_sha256": _hash("c"), "token_estimate": 8},
            }
        )
        result = ws.receive_json()
        assert result["event"] == "thinking"
        assert result["memory_turn_count"] == 1
        assert result["stt_final_sha256"] == _hash("c")


def test_voice_websocket_invalid_language_fails_closed():
    client = TestClient(app)
    try:
        with client.websocket_connect("/v1/voice/ws/session-4?language=xx"):
            raise AssertionError("unsupported language websocket should close")
    except Exception:
        pass
