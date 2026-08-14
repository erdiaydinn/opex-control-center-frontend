import asyncio
import hashlib

import pytest

from app.voice_async_runtime import VoiceAsyncExecutionCoordinator
from app.voice_realtime_controller import VoiceRealtimeSessionController
from app.voice_session_ledger import VoiceSessionLedger
from app.voice_tool_bridge import VoiceToolIntent
from app.voice_tool_execution_provenance import (
    GovernedToolExecutionProof,
    GovernedVoiceToolResult,
)


def _intent(*, risk: str = "read", fingerprint: str = "a" * 64) -> VoiceToolIntent:
    return VoiceToolIntent(
        session_id="session-1",
        language="tr",
        tool_name="ops_kpi_query",
        tool_call_id="tool-1",
        risk=risk,
        arguments_sha256="b" * 64,
        reason_sha256="c" * 64,
        approval_reference="approval-1" if risk != "read" else None,
        fingerprint=fingerprint,
    )


def _proof() -> GovernedToolExecutionProof:
    return GovernedToolExecutionProof(
        tool="ops_kpi_query",
        query_id="ops-kpi-v1",
        execution_id="exec-1",
        status="executed",
        sql_sha256="5" * 64,
        activation_provenance_fingerprint="6" * 64,
        result_contract_fingerprint="7" * 64,
        legal_grounding_fingerprint=None,
        fingerprint="8" * 64,
    )


def test_barge_in_rejects_late_result_from_previous_turn():
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller)
    coordinator.start_turn()
    controller.streaming.wake()
    controller.streaming.stt_final("hello")
    controller.streaming.begin_response("response-1")
    lease, token = coordinator.start_task(
        task_id="model-1",
        kind="model",
        request_fingerprint="d" * 64,
    )

    assert coordinator.cancel_for_barge_in() == ("model-1",)
    assert token.cancelled is True
    with pytest.raises(ValueError, match="voice_async_cancelled_result_rejected"):
        coordinator.accept_result(lease=lease, result_sha256="e" * 64)


def test_write_tool_approval_token_is_exact_and_single_use():
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller)
    intent = _intent(risk="write", fingerprint="f" * 64)
    token, _ = controller.approvals.issue(
        session_id=intent.session_id,
        tool_call_id=intent.tool_call_id,
        risk="write",
        intent_fingerprint=intent.fingerprint,
    )

    coordinator.authorize_tool_execution(intent=intent, approval_token=token)
    with pytest.raises(ValueError, match="voice_approval_token_replay"):
        coordinator.authorize_tool_execution(intent=intent, approval_token=token)


def test_approval_token_cannot_authorize_changed_intent():
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller)
    original = _intent(risk="critical", fingerprint="1" * 64)
    token, _ = controller.approvals.issue(
        session_id=original.session_id,
        tool_call_id=original.tool_call_id,
        risk="critical",
        intent_fingerprint=original.fingerprint,
    )
    changed = _intent(risk="critical", fingerprint="2" * 64)

    with pytest.raises(ValueError, match="voice_approval_token_binding_mismatch"):
        coordinator.authorize_tool_execution(intent=changed, approval_token=token)


def test_accepted_tool_result_is_hash_only_audited_with_governed_provenance(tmp_path):
    class Adapter:
        async def execute(self, *, intent, cancellation):
            cancellation.checkpoint()
            return GovernedVoiceToolResult(
                content="sensitive-result-not-persisted",
                execution_proof=_proof(),
            )

    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller, ledger=ledger)
    coordinator.start_turn()
    lease, cancellation = coordinator.start_task(
        task_id="tool-1",
        kind="tool",
        request_fingerprint="3" * 64,
    )
    intent = _intent(risk="read", fingerprint="4" * 64)

    accepted = asyncio.run(
        coordinator.execute_tool(
            intent=intent,
            approval_token=None,
            adapter=Adapter(),
            lease=lease,
            cancellation=cancellation,
        )
    )

    assert accepted.result_sha256 == hashlib.sha256(b"sensitive-result-not-persisted").hexdigest()
    assert accepted.governed_provenance_fingerprint == "8" * 64
    events = ledger.verify_session("session-1")
    assert [event.event_type for event in events] == ["tool_result"]
    assert events[0].tool_call_id == "tool-1"
    assert len(events[0].metadata_sha256) == 64


def test_raw_tool_adapter_result_is_rejected_even_when_hashable():
    class UnsafeAdapter:
        async def execute(self, *, intent, cancellation):
            return "unguarded tool result"

    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(controller=controller)
    coordinator.start_turn()
    lease, cancellation = coordinator.start_task(
        task_id="tool-1",
        kind="tool",
        request_fingerprint="9" * 64,
    )

    with pytest.raises(ValueError, match="voice_async_tool_governed_result_required"):
        asyncio.run(
            coordinator.execute_tool(
                intent=_intent(),
                approval_token=None,
                adapter=UnsafeAdapter(),
                lease=lease,
                cancellation=cancellation,
            )
        )


def test_task_result_is_rejected_if_deployment_drifted_after_task_start():
    state = {"manifest": "0" * 64}
    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(
        controller=controller,
        deployment_manifest_fingerprint="0" * 64,
        deployment_freshness_check=lambda: state["manifest"],
    )
    coordinator.start_turn()
    lease, _ = coordinator.start_task(
        task_id="model-1",
        kind="model",
        request_fingerprint="d" * 64,
    )
    state["manifest"] = "1" * 64

    with pytest.raises(ValueError, match="voice_async_deployment_manifest_drift"):
        coordinator.accept_result(lease=lease, result_sha256="e" * 64)


def test_tool_adapter_completion_revalidates_deployment_before_result_acceptance():
    state = {"manifest": "0" * 64}

    class DriftAdapter:
        async def execute(self, *, intent, cancellation):
            state["manifest"] = "1" * 64
            return GovernedVoiceToolResult(content="result", execution_proof=_proof())

    controller = VoiceRealtimeSessionController(session_id="session-1", language="tr")
    coordinator = VoiceAsyncExecutionCoordinator(
        controller=controller,
        deployment_manifest_fingerprint="0" * 64,
        deployment_freshness_check=lambda: state["manifest"],
    )
    coordinator.start_turn()
    lease, cancellation = coordinator.start_task(
        task_id="tool-1",
        kind="tool",
        request_fingerprint="3" * 64,
    )

    with pytest.raises(ValueError, match="voice_async_deployment_manifest_drift"):
        asyncio.run(
            coordinator.execute_tool(
                intent=_intent(),
                approval_token=None,
                adapter=DriftAdapter(),
                lease=lease,
                cancellation=cancellation,
            )
        )
