from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal, Mapping

ClientEvent = Literal[
    "wake",
    "audio_frame",
    "stt_partial",
    "stt_final",
    "task_start",
    "task_result",
    "response_start",
    "tts_start",
    "barge_in",
    "approval",
]
ServerEvent = Literal[
    "listening",
    "thinking",
    "task_started",
    "task_result_accepted",
    "response_started",
    "tts_started",
    "approval_required",
    "tts_chunk",
    "cancelled",
    "done",
    "error",
]

_ALLOWED_EVENTS = {
    "wake",
    "audio_frame",
    "stt_partial",
    "stt_final",
    "task_start",
    "task_result",
    "response_start",
    "tts_start",
    "barge_in",
    "approval",
    "listening",
    "thinking",
    "task_started",
    "task_result_accepted",
    "response_started",
    "tts_started",
    "approval_required",
    "tts_chunk",
    "cancelled",
    "done",
    "error",
}


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceWsEnvelope:
    session_id: str
    message_id: str
    event: str
    sequence: int
    payload_sha256: str
    protocol_version: str
    fingerprint: str


def seal_envelope(
    *,
    session_id: str,
    message_id: str,
    event: str,
    sequence: int,
    payload: Mapping[str, object],
    protocol_version: str = "eay-voice-ws-v1",
) -> VoiceWsEnvelope:
    session_id = session_id.strip()
    message_id = message_id.strip()
    protocol_version = protocol_version.strip()
    if len(session_id) < 3:
        raise ValueError("voice_ws_session_id_required")
    if len(message_id) < 3:
        raise ValueError("voice_ws_message_id_required")
    if sequence < 0:
        raise ValueError("voice_ws_sequence_invalid")
    if event not in _ALLOWED_EVENTS:
        raise ValueError("voice_ws_event_invalid")
    forbidden = {
        key
        for key in payload
        if key.lower() in {"raw_audio", "audio_bytes", "transcript", "prompt", "result_text", "tts_text"}
    }
    if forbidden:
        raise ValueError("voice_ws_raw_content_forbidden")
    payload_sha = _sha256(dict(payload))
    data = {
        "session_id": session_id,
        "message_id": message_id,
        "event": event,
        "sequence": sequence,
        "payload_sha256": payload_sha,
        "protocol_version": protocol_version,
    }
    return VoiceWsEnvelope(
        session_id=session_id,
        message_id=message_id,
        event=event,
        sequence=sequence,
        payload_sha256=payload_sha,
        protocol_version=protocol_version,
        fingerprint=_sha256(data),
    )


class VoiceWsSequenceGuard:
    def __init__(self) -> None:
        self._last_by_session: dict[str, int] = {}

    def accept(self, envelope: VoiceWsEnvelope) -> None:
        previous = self._last_by_session.get(envelope.session_id, -1)
        if envelope.sequence != previous + 1:
            raise ValueError("voice_ws_sequence_gap_or_replay")
        self._last_by_session[envelope.session_id] = envelope.sequence
