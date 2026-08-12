import pytest

from app.voice_async_runtime import VoiceAsyncExecutionCoordinator
from app.voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity
from app.voice_realtime_controller import VoiceRealtimeSessionController
from app.voice_session_ledger import VoiceSessionLedger


def _hash(ch: str) -> str:
    return ch * 64


MANIFEST = _hash("0")


def _model_identity() -> VoiceModelExecutionIdentity:
    return VoiceModelExecutionIdentity(
        artifact_sha256=_hash("1"), artifact_provenance_fingerprint=_hash("2"),
        training_job_fingerprint=_hash("3"), artifact_format="gguf",
        build_reference_sha256=_hash("4"), fingerprint=_hash("5"),
    )


def _tts_identity(profile_fp: str = _hash("f")) -> VoiceTtsExecutionIdentity:
    return VoiceTtsExecutionIdentity(
        adapter_id="tts-local-v1", implementation="local-tts-v1", license_id="apache-2.0",
        license_id_sha256=_hash("6"), artifact_sha256=_hash("7"), adapter_fingerprint=_hash("8"),
        promotion_fingerprint=_hash("9"), profile_fingerprint=profile_fp,
        language_capability_fingerprints=(_hash("a"),), fingerprint=_hash("b"),
    )


def _coordinator(tmp_path=None):
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    ledger = VoiceSessionLedger(tmp_path / "voice.db") if tmp_path is not None else None
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller, ledger=ledger)
    coordinator.start_turn()
    return controller, coordinator, ledger


def _response(coordinator, **kwargs):
    return coordinator.seal_response_generation(
        user_input_sha256=_hash("d"),
        deployment_manifest_fingerprint=MANIFEST,
        model_execution_identity=_model_identity(),
        **kwargs,
    )


def test_response_proof_binds_current_governed_tool_result(tmp_path):
    _, coordinator, ledger = _coordinator(tmp_path)
    lease, _ = coordinator.start_task(task_id="tool-1", kind="tool", request_fingerprint=_hash("a"))
    accepted = coordinator.accept_result(lease=lease, result_sha256=_hash("b"), governed_provenance_fingerprint=_hash("c"))
    response = _response(coordinator, tool_task_ids=(accepted.task_id,), kpi_context_fingerprint=_hash("e"))
    assert response.turn_epoch == 1
    assert response.deployment_manifest_fingerprint == MANIFEST
    assert response.accepted_tool_result_fingerprints == (accepted.fingerprint,)
    assert response.governed_tool_provenance_fingerprints == (_hash("c"),)
    assert response.model_artifact_sha256 == _hash("1")
    assert response.model_execution_identity_fingerprint == _hash("5")
    assert len(response.fingerprint) == 64
    assert [event.event_type for event in ledger.verify_session("session-1")] == ["response_proof"]


def test_stale_tool_result_cannot_feed_new_turn_response():
    _, coordinator, _ = _coordinator()
    lease, _ = coordinator.start_task(task_id="tool-1", kind="tool", request_fingerprint=_hash("a"))
    coordinator.accept_result(lease=lease, result_sha256=_hash("b"), governed_provenance_fingerprint=_hash("c"))
    coordinator.start_turn()
    with pytest.raises(ValueError, match="voice_response_stale_tool_result_forbidden"):
        _response(coordinator, tool_task_ids=("tool-1",))


def test_tts_requires_current_response_proof_and_exact_voice_profile(tmp_path):
    _, coordinator, ledger = _coordinator(tmp_path)
    response = _response(coordinator)
    tts = coordinator.seal_tts_generation(
        response_proof=response, deployment_manifest_fingerprint=MANIFEST,
        response_text_sha256=_hash("e"), voice_profile_fingerprint=_hash("f"),
        tts_execution_identity=_tts_identity(),
    )
    assert tts.response_proof_fingerprint == response.fingerprint
    assert tts.deployment_manifest_fingerprint == MANIFEST
    assert tts.tts_adapter_artifact_sha256 == _hash("7")
    assert tts.tts_adapter_promotion_fingerprint == _hash("9")
    assert len(tts.fingerprint) == 64
    assert [event.event_type for event in ledger.verify_session("session-1")] == ["response_proof", "tts_proof"]


def test_tts_rejects_deployment_manifest_mismatch():
    _, coordinator, _ = _coordinator()
    response = _response(coordinator)
    with pytest.raises(ValueError, match="voice_tts_deployment_manifest_mismatch"):
        coordinator.seal_tts_generation(
            response_proof=response, deployment_manifest_fingerprint=_hash("1"),
            response_text_sha256=_hash("e"), voice_profile_fingerprint=_hash("f"),
            tts_execution_identity=_tts_identity(),
        )


def test_tts_rejects_profile_drift():
    _, coordinator, _ = _coordinator()
    response = _response(coordinator)
    with pytest.raises(ValueError, match="voice_tts_execution_profile_mismatch"):
        coordinator.seal_tts_generation(
            response_proof=response, deployment_manifest_fingerprint=MANIFEST,
            response_text_sha256=_hash("e"), voice_profile_fingerprint=_hash("f"),
            tts_execution_identity=_tts_identity(_hash("e")),
        )


def test_barge_in_invalidates_response_proof_for_tts():
    controller, coordinator, _ = _coordinator()
    response = _response(coordinator)
    controller.streaming.wake()
    coordinator.cancel_for_barge_in()
    with pytest.raises(ValueError, match="voice_tts_stale_response_proof_forbidden"):
        coordinator.seal_tts_generation(
            response_proof=response, deployment_manifest_fingerprint=MANIFEST,
            response_text_sha256=_hash("e"), voice_profile_fingerprint=_hash("f"),
            tts_execution_identity=_tts_identity(),
        )


def test_response_rejects_non_tool_accepted_result():
    _, coordinator, _ = _coordinator()
    lease, _ = coordinator.start_task(task_id="model-1", kind="model", request_fingerprint=_hash("a"))
    coordinator.accept_result(lease=lease, result_sha256=_hash("b"))
    with pytest.raises(ValueError, match="voice_response_non_tool_result_forbidden"):
        _response(coordinator, tool_task_ids=("model-1",))
