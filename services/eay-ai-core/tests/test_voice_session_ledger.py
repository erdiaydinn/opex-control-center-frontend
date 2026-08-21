import sqlite3

import pytest

from app.voice_session_ledger import VoiceSessionLedger


def test_voice_session_ledger_hashes_transcript_and_chains_events(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    first = ledger.append(
        session_id="session-1",
        event_type="utterance_final",
        language="tr",
        transcript="Bugünkü NSFR durumunu göster",
        metadata={"sample_rate_hz": 16000},
    )
    second = ledger.append(
        session_id="session-1",
        event_type="response_started",
        language="tr",
    )

    assert len(first.transcript_sha256 or "") == 64
    assert second.previous_event_sha256 == first.event_sha256
    verified = ledger.verify_session("session-1")
    assert [item.event_id for item in verified] == [first.event_id, second.event_id]

    with sqlite3.connect(tmp_path / "voice.db") as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(voice_session_events)")}
    assert "transcript" not in columns
    assert "audio" not in columns


def test_raw_audio_or_transcript_metadata_is_forbidden(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    with pytest.raises(ValueError, match="voice_session_raw_content_metadata_forbidden"):
        ledger.append(
            session_id="session-2",
            event_type="wake",
            language="en",
            metadata={"raw_audio": "not-allowed"},
        )


def test_write_or_critical_approval_must_have_explicit_reference(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    with pytest.raises(ValueError, match="voice_session_approval_reference_required"):
        ledger.append(
            session_id="session-3",
            event_type="approval_granted",
            language="de",
            action_risk="critical",
        )

    event = ledger.append(
        session_id="session-3",
        event_type="approval_granted",
        language="de",
        action_risk="write",
        approval_reference="VOICE-APPROVAL-42",
    )
    assert event.approval_reference == "VOICE-APPROVAL-42"


def test_tool_request_requires_tool_call_id(tmp_path):
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    with pytest.raises(ValueError, match="voice_session_tool_call_id_required"):
        ledger.append(
            session_id="session-4",
            event_type="tool_request",
            language="fa",
            action_risk="read",
        )


def test_session_chain_tampering_is_detected(tmp_path):
    db = tmp_path / "voice.db"
    ledger = VoiceSessionLedger(db)
    ledger.append(session_id="session-5", event_type="wake", language="ar")
    ledger.append(session_id="session-5", event_type="response_started", language="ar")

    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE voice_session_events SET previous_event_sha256=? WHERE event_id=2",
            ("f" * 64,),
        )

    with pytest.raises(ValueError, match="voice_session_chain_drift"):
        ledger.verify_session("session-5")
