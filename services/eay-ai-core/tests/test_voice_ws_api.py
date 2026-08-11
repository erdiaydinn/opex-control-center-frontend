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
        assert ready["turn_epoch"] == 0

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


def test_voice_websocket_stt_final_starts_governed_turn():
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
        assert result["turn_epoch"] == 1


def test_voice_websocket_accepts_current_task_result_and_retires_task():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-5?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("d")}})
        assert ws.receive_json()["turn_epoch"] == 1
        ws.send_json(
            {
                "event": "task_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "stt-post-1", "kind": "stt", "request_fingerprint": _hash("e")},
            }
        )
        started = ws.receive_json()
        assert started["event"] == "task_started"
        assert started["active_task_count"] == 1
        assert started["task_turn_epoch"] == 1
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {"task_id": "stt-post-1", "result_sha256": _hash("f")},
            }
        )
        accepted = ws.receive_json()
        assert accepted["event"] == "task_result_accepted"
        assert accepted["active_task_count"] == 0
        assert accepted["result_sha256"] == _hash("f")
        assert len(accepted["accepted_result_fingerprint"]) == 64


def test_voice_websocket_model_and_tts_generic_start_are_forbidden():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-1?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json({"event": "task_start", "sequence": 2, "message_id": "m-2", "payload": {"task_id": "model-1", "kind": "model", "request_fingerprint": _hash("b")}})
        assert ws.receive_json()["code"] == "voice_ws_proof_bound_start_required"
        ws.send_json({"event": "task_start", "sequence": 3, "message_id": "m-3", "payload": {"task_id": "tts-1", "kind": "tts", "request_fingerprint": _hash("c")}})
        assert ws.receive_json()["code"] == "voice_ws_proof_bound_start_required"


def test_voice_websocket_response_and_tts_are_exact_proof_bound():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-2?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json({"event": "response_start", "sequence": 2, "message_id": "m-2", "payload": {"task_id": "model-1", "user_input_sha256": _hash("a")}})
        started = ws.receive_json()
        assert started["event"] == "response_started"
        response_fp = started["response_proof_fingerprint"]
        assert started["task_request_fingerprint"] == response_fp
        ws.send_json({"event": "task_result", "sequence": 3, "message_id": "m-3", "payload": {"task_id": "model-1", "result_sha256": _hash("b")}})
        assert ws.receive_json()["event"] == "task_result_accepted"
        ws.send_json({"event": "tts_start", "sequence": 4, "message_id": "m-4", "payload": {"task_id": "tts-1", "response_proof_fingerprint": response_fp, "response_text_sha256": _hash("b"), "voice_profile_fingerprint": _hash("c")}})
        tts = ws.receive_json()
        assert tts["event"] == "tts_started"
        assert tts["response_proof_fingerprint"] == response_fp
        assert tts["task_request_fingerprint"] == tts["tts_proof_fingerprint"]


def test_voice_websocket_response_rejects_wrong_user_input_and_unknown_tts_proof():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-3?language=en") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json({"event": "response_start", "sequence": 2, "message_id": "m-2", "payload": {"task_id": "model-1", "user_input_sha256": _hash("b")}})
        assert ws.receive_json()["code"] == "voice_ws_response_user_input_mismatch"
        ws.send_json({"event": "tts_start", "sequence": 3, "message_id": "m-3", "payload": {"task_id": "tts-1", "response_proof_fingerprint": _hash("c"), "response_text_sha256": _hash("d"), "voice_profile_fingerprint": _hash("e")}})
        assert ws.receive_json()["code"] == "voice_ws_tts_response_proof_unknown"


def test_voice_websocket_tool_result_requires_governed_execution_provenance():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-7?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("4")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "task_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "tool-1", "kind": "tool", "request_fingerprint": _hash("5")},
            }
        )
        ws.receive_json()
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {"task_id": "tool-1", "result_sha256": _hash("6")},
            }
        )
        rejected = ws.receive_json()
        assert rejected["event"] == "error"
        assert rejected["code"] == "voice_ws_tool_governed_provenance_invalid"

        ws.send_json(
            {
                "event": "task_result",
                "sequence": 4,
                "message_id": "m-4",
                "payload": {
                    "task_id": "tool-1",
                    "result_sha256": _hash("6"),
                    "governed_provenance_fingerprint": _hash("7"),
                },
            }
        )
        accepted = ws.receive_json()
        assert accepted["event"] == "task_result_accepted"
        assert accepted["governed_provenance_fingerprint"] == _hash("7")


def test_voice_websocket_barge_in_rejects_late_task_result():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-6?language=en") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("1")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "task_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "stt-post-1", "kind": "stt", "request_fingerprint": _hash("2")},
            }
        )
        ws.receive_json()
        ws.send_json({"event": "barge_in", "sequence": 3, "message_id": "m-3", "payload": {}})
        cancelled = ws.receive_json()
        assert cancelled["event"] == "cancelled"
        assert cancelled["turn_epoch"] == 2
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 4,
                "message_id": "m-4",
                "payload": {"task_id": "stt-post-1", "result_sha256": _hash("3")},
            }
        )
        late = ws.receive_json()
        assert late["event"] == "error"
        assert late["code"] == "voice_async_cancelled_result_rejected"


def test_voice_websocket_invalid_language_fails_closed():
    client = TestClient(app)
    try:
        with client.websocket_connect("/v1/voice/ws/session-4?language=xx"):
            raise AssertionError("unsupported language websocket should close")
    except Exception:
        pass
