from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Mapping


VoiceEventType = Literal[
    "wake",
    "utterance_final",
    "tool_request",
    "tool_result",
    "approval_required",
    "approval_granted",
    "response_proof",
    "tts_proof",
    "response_started",
    "interrupted",
    "response_finished",
    "error",
]
ActionRisk = Literal["read", "write", "critical"]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def hash_transcript(text: str) -> str:
    normalized = " ".join(str(text or "").strip().split())
    if not normalized:
        raise ValueError("voice_transcript_required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceSessionEvent:
    event_id: int
    session_id: str
    event_type: str
    language: str
    action_risk: str | None
    transcript_sha256: str | None
    tool_call_id: str | None
    approval_reference: str | None
    metadata_sha256: str
    previous_event_sha256: str | None
    occurred_at: str
    event_sha256: str


class VoiceSessionLedger:
    """Append-only audit lineage for conversational voice sessions.

    Raw microphone bytes and transcript text are intentionally not persisted here.
    The ledger stores only transcript hashes plus bounded non-content metadata so a
    conversation can be audited without creating a second raw-audio data lake.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS voice_session_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                language TEXT NOT NULL,
                action_risk TEXT,
                transcript_sha256 TEXT,
                tool_call_id TEXT,
                approval_reference TEXT,
                metadata_sha256 TEXT NOT NULL,
                previous_event_sha256 TEXT,
                occurred_at TEXT NOT NULL,
                event_sha256 TEXT NOT NULL UNIQUE
                )"""
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_voice_session_events_session ON voice_session_events(session_id,event_id)"
            )

    def append(
        self,
        *,
        session_id: str,
        event_type: VoiceEventType,
        language: str,
        transcript: str | None = None,
        action_risk: ActionRisk | None = None,
        tool_call_id: str | None = None,
        approval_reference: str | None = None,
        metadata: Mapping[str, str | int | float | bool | None] | None = None,
        occurred_at: datetime | None = None,
    ) -> VoiceSessionEvent:
        session_id = session_id.strip()
        language = language.strip().lower()
        if len(session_id) < 3:
            raise ValueError("voice_session_id_required")
        if not language:
            raise ValueError("voice_session_language_required")
        if action_risk not in {None, "read", "write", "critical"}:
            raise ValueError("voice_session_action_risk_invalid")
        if event_type == "approval_granted" and action_risk not in {"write", "critical"}:
            raise ValueError("voice_session_approval_risk_required")
        if event_type == "approval_granted" and len((approval_reference or "").strip()) < 3:
            raise ValueError("voice_session_approval_reference_required")
        if event_type in {"tool_request", "tool_result"} and not (tool_call_id or "").strip():
            raise ValueError("voice_session_tool_call_id_required")

        transcript_sha256 = hash_transcript(transcript) if transcript is not None else None
        safe_metadata = dict(metadata or {})
        forbidden = {key for key in safe_metadata if key.lower() in {"transcript", "audio", "audio_bytes", "raw_audio", "prompt"}}
        if forbidden:
            raise ValueError("voice_session_raw_content_metadata_forbidden")
        metadata_sha256 = _sha256(safe_metadata)
        when = occurred_at or datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            previous = conn.execute(
                "SELECT event_sha256 FROM voice_session_events WHERE session_id=? ORDER BY event_id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
            previous_sha = previous["event_sha256"] if previous else None
            payload = {
                "session_id": session_id,
                "event_type": event_type,
                "language": language,
                "action_risk": action_risk,
                "transcript_sha256": transcript_sha256,
                "tool_call_id": (tool_call_id or "").strip() or None,
                "approval_reference": (approval_reference or "").strip() or None,
                "metadata_sha256": metadata_sha256,
                "previous_event_sha256": previous_sha,
                "occurred_at": when.isoformat(),
            }
            event_sha = _sha256(payload)
            cursor = conn.execute(
                """INSERT INTO voice_session_events(
                session_id,event_type,language,action_risk,transcript_sha256,
                tool_call_id,approval_reference,metadata_sha256,previous_event_sha256,
                occurred_at,event_sha256
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    session_id,
                    event_type,
                    language,
                    action_risk,
                    transcript_sha256,
                    payload["tool_call_id"],
                    payload["approval_reference"],
                    metadata_sha256,
                    previous_sha,
                    when.isoformat(),
                    event_sha,
                ),
            )
            event_id = int(cursor.lastrowid)
        return self.get(event_id)

    def get(self, event_id: int) -> VoiceSessionEvent:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM voice_session_events WHERE event_id=?", (event_id,)).fetchone()
        if row is None:
            raise KeyError("voice_session_event_not_found")
        self._verify_row(row)
        return VoiceSessionEvent(**dict(row))

    def verify_session(self, session_id: str) -> tuple[VoiceSessionEvent, ...]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM voice_session_events WHERE session_id=? ORDER BY event_id",
                (session_id,),
            ).fetchall()
        previous_sha: str | None = None
        events: list[VoiceSessionEvent] = []
        for row in rows:
            if row["previous_event_sha256"] != previous_sha:
                raise ValueError("voice_session_chain_drift")
            self._verify_row(row)
            previous_sha = row["event_sha256"]
            events.append(VoiceSessionEvent(**dict(row)))
        return tuple(events)

    @staticmethod
    def _verify_row(row: sqlite3.Row) -> None:
        payload = {
            "session_id": row["session_id"],
            "event_type": row["event_type"],
            "language": row["language"],
            "action_risk": row["action_risk"],
            "transcript_sha256": row["transcript_sha256"],
            "tool_call_id": row["tool_call_id"],
            "approval_reference": row["approval_reference"],
            "metadata_sha256": row["metadata_sha256"],
            "previous_event_sha256": row["previous_event_sha256"],
            "occurred_at": row["occurred_at"],
        }
        if _sha256(payload) != row["event_sha256"]:
            raise ValueError("voice_session_event_fingerprint_mismatch")
