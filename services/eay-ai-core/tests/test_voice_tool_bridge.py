import pytest

from app.voice_session_ledger import VoiceSessionLedger
from app.voice_tool_bridge import VoiceToolBridge


def test_read_only_voice_tool_intent_seals_without_approval(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "eay.db")
    bridge = VoiceToolBridge(ledger)
    intent = bridge.seal_intent(
        session_id="session-1",
        language="tr",
        tool_name="ops_kpi_query",
        tool_call_id="tool-1",
        risk="read",
        arguments={"metric": "nsfr"},
        reason="read yesterday nsfr",
    )
    assert intent.approval_reference is None
    assert len(intent.fingerprint) == 64
    events = ledger.verify_session("session-1")
    assert [item.event_type for item in events] == ["tool_request"]


def test_write_voice_tool_requires_explicit_approval(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "eay.db")
    bridge = VoiceToolBridge(ledger)
    with pytest.raises(ValueError, match="voice_tool_explicit_approval_required"):
        bridge.seal_intent(
            session_id="session-2",
            language="en",
            tool_name="send_report",
            tool_call_id="tool-2",
            risk="write",
            arguments={"recipient": "ops"},
            reason="send reviewed report",
        )
    events = ledger.verify_session("session-2")
    assert [item.event_type for item in events] == ["approval_required"]


def test_write_voice_tool_records_request_and_approval(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "eay.db")
    bridge = VoiceToolBridge(ledger)
    intent = bridge.seal_intent(
        session_id="session-3",
        language="de",
        tool_name="send_report",
        tool_call_id="tool-3",
        risk="write",
        arguments={"recipient": "ops"},
        reason="send reviewed report",
        approval_reference="voice-approve-001",
    )
    assert intent.approval_reference == "voice-approve-001"
    events = ledger.verify_session("session-3")
    assert [item.event_type for item in events] == ["tool_request", "approval_granted"]
    assert events[-1].approval_reference == "voice-approve-001"


def test_critical_voice_tool_also_requires_approval(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "eay.db")
    bridge = VoiceToolBridge(ledger)
    with pytest.raises(ValueError, match="voice_tool_explicit_approval_required"):
        bridge.seal_intent(
            session_id="session-4",
            language="fa",
            tool_name="model_promote",
            tool_call_id="tool-4",
            risk="critical",
            arguments={"model": "candidate"},
            reason="promote model candidate",
        )
