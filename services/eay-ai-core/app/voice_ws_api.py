from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .voice_realtime_controller import VoiceRealtimeSessionController
from .voice_ws_protocol import VoiceWsSequenceGuard, seal_envelope

router = APIRouter(tags=["voice"])


def _safe_error(code: str) -> dict[str, str]:
    return {"event": "error", "code": code}


def _response_payload(controller: VoiceRealtimeSessionController, *, event: str) -> dict[str, Any]:
    snapshot = controller.streaming.snapshot()
    return {
        "event": event,
        "state": snapshot.state.value,
        "stream_fingerprint": snapshot.fingerprint,
        "response_id": snapshot.response_id,
        "cancelled_response_id": snapshot.cancelled_response_id,
        "active_task_count": len(controller.active_tasks()),
        "memory_turn_count": len(controller.memory.snapshot()),
    }


@router.websocket("/v1/voice/ws/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str, language: str = "tr") -> None:
    """Governed control-plane WebSocket for the local-first voice runtime.

    This endpoint intentionally accepts only control metadata and content hashes. Raw
    microphone bytes, transcript text and prompts are not accepted in JSON messages;
    live audio transport/adapters remain a separate transient-data layer.
    """

    try:
        controller = VoiceRealtimeSessionController(session_id=session_id, language=language)
    except ValueError:
        await websocket.close(code=1008, reason="voice_session_invalid")
        return

    guard = VoiceWsSequenceGuard()
    await websocket.accept()
    await websocket.send_json(
        {
            "event": "ready",
            "session_id": session_id,
            "language": language,
            "protocol_version": "eay-voice-ws-v1",
        }
    )

    try:
        while True:
            message = await websocket.receive_json()
            if not isinstance(message, dict):
                await websocket.send_json(_safe_error("voice_ws_message_object_required"))
                continue

            forbidden = {
                key
                for key in message
                if str(key).lower() in {"raw_audio", "audio_bytes", "transcript", "prompt"}
            }
            if forbidden:
                await websocket.send_json(_safe_error("voice_ws_raw_content_forbidden"))
                continue

            try:
                event = str(message.get("event", ""))
                sequence = int(message.get("sequence", -1))
                message_id = str(message.get("message_id", ""))
                payload = message.get("payload") or {}
                if not isinstance(payload, dict):
                    raise ValueError("voice_ws_payload_object_required")

                envelope = seal_envelope(
                    session_id=session_id,
                    message_id=message_id,
                    event=event,
                    sequence=sequence,
                    payload=payload,
                )
                guard.accept(envelope)

                if event == "wake":
                    controller.streaming.wake()
                    response = _response_payload(controller, event="listening")
                elif event == "audio_frame":
                    # Raw PCM does not enter this control-plane endpoint. The adapter
                    # transport supplies an immutable frame hash and bounded metadata.
                    from .voice_streaming import AudioFrame

                    controller.streaming.push_audio(
                        AudioFrame(
                            sequence=int(payload["frame_sequence"]),
                            pcm_sha256=str(payload["pcm_sha256"]),
                            duration_ms=int(payload["duration_ms"]),
                            sample_rate_hz=int(payload["sample_rate_hz"]),
                        )
                    )
                    response = _response_payload(controller, event="listening")
                elif event == "stt_partial":
                    digest = str(payload.get("text_sha256", ""))
                    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                        raise ValueError("voice_ws_stt_hash_invalid")
                    # The live adapter owns text; the control plane records only the hash.
                    response = _response_payload(controller, event="listening")
                    response["stt_partial_sha256"] = digest
                elif event == "stt_final":
                    digest = str(payload.get("text_sha256", ""))
                    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
                        raise ValueError("voice_ws_stt_hash_invalid")
                    controller.memory.append(
                        role="user",
                        text=digest,
                        token_estimate=max(1, int(payload.get("token_estimate", 1))),
                    )
                    controller.streaming.machine.end_utterance()
                    response = _response_payload(controller, event="thinking")
                    response["stt_final_sha256"] = digest
                elif event == "barge_in":
                    cancelled = controller.cancel_for_barge_in()
                    response = _response_payload(controller, event="cancelled")
                    response["cancelled_task_ids_sha256"] = hashlib.sha256(
                        json.dumps(sorted(task.task_id for task in cancelled), separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                elif event == "approval":
                    response = _safe_error("voice_ws_approval_requires_bound_tool_intent")
                else:
                    response = _safe_error("voice_ws_event_not_supported_here")

                response["envelope_fingerprint"] = envelope.fingerprint
                await websocket.send_json(response)
            except (KeyError, TypeError, ValueError) as exc:
                await websocket.send_json(_safe_error(str(exc)))
    except WebSocketDisconnect:
        return
