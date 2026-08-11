import pytest

from app.voice_realtime_controller import (
    BoundedConversationMemory,
    SingleUseApprovalStore,
    VoiceRealtimeSessionController,
)


def test_bounded_memory_evicts_oldest_turns_by_count_and_tokens():
    memory = BoundedConversationMemory(max_turns=3, max_token_estimate=256)
    memory.append(role="user", text="one", token_estimate=100)
    memory.append(role="assistant", text="two", token_estimate=100)
    memory.append(role="user", text="three", token_estimate=100)
    snapshot = memory.snapshot()
    assert len(snapshot) == 2
    assert snapshot[0].role == "assistant"
    assert all(len(item.content_sha256) == 64 for item in snapshot)


def test_single_use_approval_token_is_bound_and_replay_safe():
    store = SingleUseApprovalStore()
    intent = "a" * 64
    token, record = store.issue(
        session_id="session-1",
        tool_call_id="tool-1",
        risk="write",
        intent_fingerprint=intent,
    )
    consumed = store.consume(
        token=token,
        session_id="session-1",
        tool_call_id="tool-1",
        risk="write",
        intent_fingerprint=intent,
    )
    assert consumed.token_id == record.token_id
    with pytest.raises(ValueError, match="voice_approval_token_replay"):
        store.consume(
            token=token,
            session_id="session-1",
            tool_call_id="tool-1",
            risk="write",
            intent_fingerprint=intent,
        )


def test_approval_token_cannot_cross_session_or_tool():
    store = SingleUseApprovalStore()
    intent = "b" * 64
    token, _ = store.issue(
        session_id="session-1",
        tool_call_id="tool-1",
        risk="critical",
        intent_fingerprint=intent,
    )
    with pytest.raises(ValueError, match="voice_approval_token_binding_mismatch"):
        store.consume(
            token=token,
            session_id="session-2",
            tool_call_id="tool-1",
            risk="critical",
            intent_fingerprint=intent,
        )


def test_barge_in_cancels_cancellable_model_tts_and_tool_tasks():
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    controller.streaming.wake()
    controller.streaming.stt_final("hello")
    controller.streaming.begin_response("response-1")
    controller.start_task(task_id="model-1", kind="model")
    controller.start_task(task_id="tts-1", kind="tts")
    controller.start_task(task_id="tool-1", kind="tool")
    controller.start_task(task_id="noncancel-1", kind="tool", cancellable=False)

    cancelled = controller.cancel_for_barge_in()
    assert {item.task_id for item in cancelled} == {"model-1", "tts-1", "tool-1"}
    assert {item.task_id for item in controller.active_tasks()} == {"noncancel-1"}
    snapshot = controller.streaming.snapshot()
    assert snapshot.cancelled_response_id == "response-1"
    assert snapshot.state.value == "listening"
