from fastapi.testclient import TestClient

from app.entrypoint import app
from app.voice_deployment_binding import (
    VoiceDeploymentExecutionBindings,
    clear_voice_deployment_bindings,
    configure_voice_deployment_bindings,
)
from app.voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity


def _hash(ch: str) -> str:
    return ch * 64


def _bindings(manifest: str) -> VoiceDeploymentExecutionBindings:
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
        profile_fingerprint=_hash("c"),
        language_capability_fingerprints=(_hash("3"),),
        fingerprint=_hash("4"),
    )
    return VoiceDeploymentExecutionBindings(
        model=model,
        tts=tts,
        deployment_manifest_fingerprint=manifest,
        wakeword_identity_fingerprint=_hash("5"),
        vad_identity_fingerprint=_hash("6"),
        stt_identity_fingerprint=_hash("7"),
    )


def test_websocket_rejects_task_result_if_deployment_changes_mid_task():
    clear_voice_deployment_bindings()
    configure_voice_deployment_bindings(_bindings(_hash("0")))
    client = TestClient(app)
    try:
        with client.websocket_connect("/v1/voice/ws/session-drift?language=tr") as ws:
            ws.receive_json()
            ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
            ws.receive_json()
            ws.send_json({"event": "stt_final", "sequence": 1, "message_id": "m-1", "payload": {"text_sha256": _hash("a")}})
            ws.receive_json()
            ws.send_json({"event": "task_start", "sequence": 2, "message_id": "m-2", "payload": {"task_id": "tool-1", "kind": "tool", "request_fingerprint": _hash("b")}})
            assert ws.receive_json()["event"] == "task_started"

            configure_voice_deployment_bindings(_bindings(_hash("9")))
            ws.send_json({"event": "task_result", "sequence": 3, "message_id": "m-3", "payload": {"task_id": "tool-1", "result_sha256": _hash("c"), "governed_provenance_fingerprint": _hash("d")}})
            error = ws.receive_json()
            assert error["event"] == "error"
            assert error["code"] == "voice_session_deployment_manifest_drift"
    finally:
        clear_voice_deployment_bindings()


def test_websocket_response_proof_carries_exact_microphone_to_stt_lineage():
    clear_voice_deployment_bindings()
    configure_voice_deployment_bindings(_bindings(_hash("0")))
    client = TestClient(app)
    try:
        with client.websocket_connect("/v1/voice/ws/session-input-lineage?language=tr") as ws:
            ready = ws.receive_json()
            assert ready["deployment_manifest_fingerprint"] == _hash("0")
            ws.send_json({"event": "wake", "sequence": 0, "message_id": "m-0", "payload": {}})
            wake = ws.receive_json()
            assert len(wake["wake_input_proof_fingerprint"]) == 64
            ws.send_json({"event": "audio_frame", "sequence": 1, "message_id": "m-1", "payload": {"frame_sequence": 0, "pcm_sha256": _hash("e"), "duration_ms": 20, "sample_rate_hz": 16000}})
            frame = ws.receive_json()
            assert len(frame["audio_frame_proof_fingerprint"]) == 64
            ws.send_json({"event": "stt_final", "sequence": 2, "message_id": "m-2", "payload": {"text_sha256": _hash("a")}})
            stt = ws.receive_json()
            input_lineage = stt["input_lineage_fingerprint"]
            assert stt["input_audio_frame_count"] == 1
            assert len(stt["input_audio_chain_fingerprint"]) == 64
            ws.send_json({"event": "response_start", "sequence": 3, "message_id": "m-3", "payload": {"task_id": "model-1", "user_input_sha256": _hash("a")}})
            response = ws.receive_json()
            assert response["event"] == "response_started"
            assert response["input_lineage_fingerprint"] == input_lineage
            assert response["deployment_manifest_fingerprint"] == _hash("0")
    finally:
        clear_voice_deployment_bindings()
