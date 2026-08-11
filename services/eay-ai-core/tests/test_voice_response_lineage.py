import pytest

from app.voice_async_runtime import VoiceAsyncExecutionCoordinator
from app.voice_realtime_controller import VoiceRealtimeSessionController
from app.voice_session_ledger import VoiceSessionLedger


def _hash(ch: str) -> str:
    return ch * 64


def _coordinator(tmp_path=None):
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    ledger = VoiceSessionLedger(tmp_path / "voice.db") if tmp_path is not None else None
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller, ledger=ledger)
    coordinator.start_turn()
    return controller, coordinator, ledger


def test_response_proof_binds_current_governed_tool_result(tmp_path):
    _, coordinator, ledger = _coordinator(tmp_path)
    lease, _ = coordinator.start_task(
        task_id="tool-1",
        kind="tool",
        request_fingerprint=_hash("a"),
    )
    accepted = coordinator.accept_result(
        lease=lease,
        result_sha256=_hash("b"),
        governed_provenance_fingerprint=_hash("c"),
    )

    response = coordinator.seal_response_generation(
        user_input_sha256=_hash("d"),
        tool_task_ids=(accepted.task_id,),
        kpi_context_fingerprint=_hash("e"),
    )

    assert response.turn_epoch == 1
    assert response.accepted_tool_result_fingerprints == (accepted.fingerprint,)
    assert response.governed_tool_provenance_fingerprints == (_hash("c"),)
    assert len(response.fingerprint) == 64
    assert [event.event_type for event in ledger.verify_session("session-1")] == ["response_proof"]


def test_stale_tool_result_cannot_feed_new_turn_response():
    _, coordinator, _ = _coordinator()
    lease, _ = coordinator.start_task(
        task_id="tool-1",
        kind="tool",
        request_fingerprint=_hash("a"),
    )
    coordinator.accept_result(
        lease=lease,
        result_sha256=_hash("b"),
        governed_provenance_fingerprint=_hash("c"),
    )
    coordinator.start_turn()

    with pytest.raises(ValueError, match="voice_response_stale_tool_result_forbidden"):
        coordinator.seal_response_generation(
            user_input_sha256=_hash("d"),
            tool_task_ids=("tool-1",),
        )


def test_tts_requires_current_response_proof_and_exact_voice_profile(tmp_path):
    _, coordinator, ledger = _coordinator(tmp_path)
    response = coordinator.seal_response_generation(user_input_sha256=_hash("d"))
    tts = coordinator.seal_tts_generation(
        response_proof=response,
        response_text_sha256=_hash("e"),
        voice_profile_fingerprint=_hash("f"),
    )

    assert tts.response_proof_fingerprint == response.fingerprint
    assert len(tts.fingerprint) == 64
    assert [event.event_type for event in ledger.verify_session("session-1")] == [
        "response_proof",
        "tts_proof",
    ]


def test_barge_in_invalidates_response_proof_for_tts():
    controller, coordinator, _ = _coordinator()
    response = coordinator.seal_response_generation(user_input_sha256=_hash("d"))
    controller.streaming.wake()
    coordinator.cancel_for_barge_in()

    with pytest.raises(ValueError, match="voice_tts_stale_response_proof_forbidden"):
        coordinator.seal_tts_generation(
            response_proof=response,
            response_text_sha256=_hash("e"),
            voice_profile_fingerprint=_hash("f"),
        )


def test_response_rejects_non_tool_accepted_result():
    _, coordinator, _ = _coordinator()
    lease, _ = coordinator.start_task(
        task_id="model-1",
        kind="model",
        request_fingerprint=_hash("a"),
    )
    coordinator.accept_result(lease=lease, result_sha256=_hash("b"))

    with pytest.raises(ValueError, match="voice_response_non_tool_result_forbidden"):
        coordinator.seal_response_generation(
            user_input_sha256=_hash("d"),
            tool_task_ids=("model-1",),
        )
