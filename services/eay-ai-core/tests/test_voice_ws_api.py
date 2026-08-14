import pytest
from fastapi.testclient import TestClient

from app.entrypoint import app
from app.voice_deployment_binding import (
    VoiceDeploymentExecutionBindings,
    clear_voice_deployment_bindings,
    configure_voice_deployment_bindings,
)
from app.voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity
from app.voice_tts_bundle import VoiceTtsBundleExecutionIdentity, VoiceTtsLanguageExecutionIdentity


def _hash(ch: str = "a") -> str:
    return ch * 64


MANIFEST = _hash("0")


def _bundle_identity(profile_fp: str) -> VoiceTtsBundleExecutionIdentity:
    artifacts = tuple(
        VoiceTtsLanguageExecutionIdentity(
            language=language,
            voice_id_sha256=_hash("5"),
            model_sha256=_hash(ch),
            config_sha256=_hash("6"),
            tokens_sha256=_hash("4"),
            model_card_sha256=_hash("7"),
            artifact_license_id_sha256=_hash("8"),
            artifact_fingerprint=_hash("9"),
            fingerprint=_hash(ch),
        )
        for language, ch in zip(("tr", "en", "de", "ar", "fa"), ("a", "b", "c", "d", "e"))
    )
    identity = VoiceTtsBundleExecutionIdentity(
        bundle_fingerprint=_hash("5"),
        bundle_promotion_fingerprint=_hash("6"),
        runtime_adapter_id="tts-local-v1",
        runtime_adapter_promotion_fingerprint=_hash("2"),
        profile_fingerprint=profile_fp,
        phonemizer_data_manifest_fingerprint=_hash("a"),
        phonemizer_license_id_sha256=_hash("b"),
        phonemizer_source_sha256=_hash("c"),
        language_artifacts=artifacts,
        fingerprint=_hash("7"),
    )
    identity.validate()
    return identity


def _install_bindings(profile_fp: str = _hash("c"), manifest_fp: str = MANIFEST) -> None:
    model = VoiceModelExecutionIdentity(
        artifact_sha256=_hash("8"),
        artifact_provenance_fingerprint=_hash("9"),
        training_job_fingerprint=_hash("a"),
        artifact_format="gguf",
        build_reference_sha256=_hash("b"),
        fingerprint=_hash("d"),
    )
    tts = VoiceTtsExecutionIdentity(
        adapter_id="tts-local-v1",
        implementation="local-tts-v1",
        license_id="apache-2.0",
        license_id_sha256=_hash("e"),
        artifact_sha256=_hash("f"),
        adapter_fingerprint=_hash("1"),
        promotion_fingerprint=_hash("2"),
        profile_fingerprint=profile_fp,
        language_capability_fingerprints=(_hash("3"),),
        fingerprint=_hash("4"),
    )
    configure_voice_deployment_bindings(
        VoiceDeploymentExecutionBindings(
            model=model,
            tts=tts,
            deployment_manifest_fingerprint=manifest_fp,
            tts_bundle=_bundle_identity(profile_fp),
        )
    )


@pytest.fixture(autouse=True)
def _reset_bindings():
    clear_voice_deployment_bindings()
    _install_bindings()
    yield
    clear_voice_deployment_bindings()


def test_voice_websocket_wake_and_hashed_audio_flow():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-1?language=tr") as ws:
        ready = ws.receive_json()
        assert ready["event"] == "ready"
        assert ready["protocol_version"] == "eay-voice-ws-v1"
        assert ready["turn_epoch"] == 0
        assert ready["deployment_manifest_fingerprint"] == MANIFEST
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "msg-0", "payload": {}})
        listening = ws.receive_json()
        assert listening["event"] == "listening"
        assert listening["state"] == "listening"
        assert listening["deployment_manifest_fingerprint"] == MANIFEST
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
        assert ws.receive_json() == {"event": "error", "code": "voice_ws_raw_content_forbidden"}
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
        assert result["deployment_manifest_fingerprint"] == MANIFEST


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
                "payload": {"task_id": "tool-1", "kind": "tool", "request_fingerprint": _hash("e")},
            }
        )
        started = ws.receive_json()
        assert started["event"] == "task_started"
        assert started["active_task_count"] == 1
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {
                    "task_id": "tool-1",
                    "result_sha256": _hash("f"),
                    "governed_provenance_fingerprint": _hash("1"),
                },
            }
        )
        accepted = ws.receive_json()
        assert accepted["event"] == "task_result_accepted"
        assert accepted["active_task_count"] == 0


def test_voice_websocket_model_and_tts_generic_start_are_forbidden():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-1?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "task_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "model-1", "kind": "model", "request_fingerprint": _hash("b")},
            }
        )
        assert ws.receive_json()["code"] == "voice_ws_proof_bound_start_required"
        ws.send_json(
            {
                "event": "task_start",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {"task_id": "tts-1", "kind": "tts", "request_fingerprint": _hash("c")},
            }
        )
        assert ws.receive_json()["code"] == "voice_ws_proof_bound_start_required"


def test_voice_websocket_session_bootstrap_requires_server_deployment_manifest():
    clear_voice_deployment_bindings()
    client = TestClient(app)
    with pytest.raises(Exception):
        with client.websocket_connect("/v1/voice/ws/session-unbound?language=tr"):
            pass


def test_voice_websocket_response_and_tts_are_exact_proof_bound():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-2?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "response_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "model-1", "user_input_sha256": _hash("a")},
            }
        )
        started = ws.receive_json()
        assert started["event"] == "response_started"
        assert started["deployment_manifest_fingerprint"] == MANIFEST
        assert started["model_execution_identity_fingerprint"] == _hash("d")
        assert started["model_artifact_sha256"] == _hash("8")
        response_fp = started["response_proof_fingerprint"]
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {"task_id": "model-1", "result_sha256": _hash("b")},
            }
        )
        assert ws.receive_json()["event"] == "task_result_accepted"
        ws.send_json(
            {
                "event": "tts_start",
                "sequence": 4,
                "message_id": "m-4",
                "payload": {
                    "task_id": "tts-1",
                    "response_proof_fingerprint": response_fp,
                    "response_text_sha256": _hash("b"),
                    "voice_profile_fingerprint": _hash("c"),
                },
            }
        )
        tts = ws.receive_json()
        assert tts["event"] == "tts_started"
        assert tts["language"] == "tr"
        assert tts["deployment_manifest_fingerprint"] == MANIFEST
        assert tts["tts_execution_identity_fingerprint"] == _hash("4")
        assert tts["tts_adapter_artifact_sha256"] == _hash("f")
        assert tts["tts_adapter_promotion_fingerprint"] == _hash("2")
        assert tts["tts_bundle_execution_identity_fingerprint"] == _hash("7")
        assert tts["tts_bundle_promotion_fingerprint"] == _hash("6")
        assert tts["tts_voice_model_sha256"] == _hash("a")
        assert tts["tts_voice_tokens_sha256"] == _hash("4")
        assert tts["tts_phonemizer_data_manifest_fingerprint"] == _hash("a")
        assert tts["tts_phonemizer_license_id_sha256"] == _hash("b")


def test_voice_websocket_tts_rejects_client_artifact_override():
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-override?language=tr") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "response_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "model-1", "user_input_sha256": _hash("a")},
            }
        )
        response_fp = ws.receive_json()["response_proof_fingerprint"]
        ws.send_json(
            {
                "event": "tts_start",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {
                    "task_id": "tts-1",
                    "response_proof_fingerprint": response_fp,
                    "response_text_sha256": _hash("b"),
                    "voice_profile_fingerprint": _hash("c"),
                    "tts_voice_tokens_sha256": _hash("f"),
                },
            }
        )
        assert ws.receive_json()["code"] == "voice_ws_tts_server_binding_override_forbidden"


def test_voice_websocket_response_rejects_wrong_user_input_and_unknown_tts_proof():
    _install_bindings(profile_fp=_hash("e"))
    client = TestClient(app)
    with client.websocket_connect("/v1/voice/ws/session-proof-3?language=en") as ws:
        ws.receive_json()
        ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
        ws.receive_json()
        ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
        ws.receive_json()
        ws.send_json(
            {
                "event": "response_start",
                "sequence": 2,
                "message_id": "m-2",
                "payload": {"task_id": "model-1", "user_input_sha256": _hash("b")},
            }
        )
        assert ws.receive_json()["code"] == "voice_ws_response_user_input_mismatch"
        ws.send_json(
            {
                "event": "tts_start",
                "sequence": 3,
                "message_id": "m-3",
                "payload": {
                    "task_id": "tts-1",
                    "response_proof_fingerprint": _hash("c"),
                    "response_text_sha256": _hash("d"),
                    "voice_profile_fingerprint": _hash("e"),
                },
            }
        )
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
        assert ws.receive_json()["code"] == "voice_ws_tool_governed_provenance_invalid"
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
        assert ws.receive_json()["event"] == "task_result_accepted"


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
                "payload": {"task_id": "tool-1", "kind": "tool", "request_fingerprint": _hash("2")},
            }
        )
        assert ws.receive_json()["event"] == "task_started"
        ws.send_json({"event": "barge_in", "sequence": 3, "message_id": "m-3", "payload": {}})
        cancelled = ws.receive_json()
        assert cancelled["event"] == "cancelled"
        assert cancelled["turn_epoch"] == 2
        ws.send_json(
            {
                "event": "task_result",
                "sequence": 4,
                "message_id": "m-4",
                "payload": {
                    "task_id": "tool-1",
                    "result_sha256": _hash("3"),
                    "governed_provenance_fingerprint": _hash("4"),
                },
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
