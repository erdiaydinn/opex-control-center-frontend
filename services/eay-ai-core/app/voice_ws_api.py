from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .voice_async_runtime import VoiceAsyncExecutionCoordinator
from .voice_realtime_controller import VoiceRealtimeSessionController
from .voice_ws_protocol import VoiceWsSequenceGuard, seal_envelope

router = APIRouter(tags=["voice"])


def _safe_error(code: str) -> dict[str, str]:
    return {"event": "error", "code": code}


def _response_payload(
    controller: VoiceRealtimeSessionController,
    coordinator: VoiceAsyncExecutionCoordinator,
    *,
    event: str,
) -> dict[str, Any]:
    snapshot = controller.streaming.snapshot()
    return {
        "event": event,
        "state": snapshot.state.value,
        "stream_fingerprint": snapshot.fingerprint,
        "response_id": snapshot.response_id,
        "cancelled_response_id": snapshot.cancelled_response_id,
        "active_task_count": len(controller.active_tasks()),
        "memory_turn_count": len(controller.memory.snapshot()),
        "turn_epoch": coordinator.turn_epoch,
    }


def _require_sha256(value: object, code: str) -> str:
    digest = str(value or "")
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(code)
    return digest


@router.websocket("/v1/voice/ws/{session_id}")
async def voice_websocket(websocket: WebSocket, session_id: str, language: str = "tr") -> None:
    """Governed control-plane WebSocket for the local-first voice runtime.

    Raw microphone bytes, transcript/prompt text and generated text are deliberately
    excluded. The endpoint coordinates immutable hashes, turn epochs and cancellation
    leases so late adapter results cannot cross a barge-in or a newer user turn.
    Tool results additionally require an exact governed execution provenance fingerprint.
    """

    try:
        controller = VoiceRealtimeSessionController(session_id=session_id, language=language)
        coordinator = VoiceAsyncExecutionCoordinator(controller=controller)
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
            "turn_epoch": coordinator.turn_epoch,
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
                if str(key).lower()
                in {"raw_audio", "audio_bytes", "transcript", "prompt", "result_text", "tts_text"}
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
                    response = _response_payload(controller, coordinator, event="listening")
                elif event == "audio_frame":
                    from .voice_streaming import AudioFrame

                    controller.streaming.push_audio(
                        AudioFrame(
                            sequence=int(payload["frame_sequence"]),
                            pcm_sha256=_require_sha256(payload["pcm_sha256"], "voice_ws_pcm_hash_invalid"),
                            duration_ms=int(payload["duration_ms"]),
                            sample_rate_hz=int(payload["sample_rate_hz"]),
                        )
                    )
                    response = _response_payload(controller, coordinator, event="listening")
                elif event == "stt_partial":
                    digest = _require_sha256(payload.get("text_sha256"), "voice_ws_stt_hash_invalid")
                    response = _response_payload(controller, coordinator, event="listening")
                    response["stt_partial_sha256"] = digest
                elif event == "stt_final":
                    digest = _require_sha256(payload.get("text_sha256"), "voice_ws_stt_hash_invalid")
                    controller.memory.append(
                        role="user",
                        text=digest,
                        token_estimate=max(1, int(payload.get("token_estimate", 1))),
                    )
                    controller.streaming.machine.end_utterance()
                    coordinator.start_turn()
                    response = _response_payload(controller, coordinator, event="thinking")
                    response["stt_final_sha256"] = digest
                elif event == "task_start":
                    task_id = str(payload.get("task_id", ""))
                    kind = str(payload.get("kind", ""))
                    request_fingerprint = _require_sha256(
                        payload.get("request_fingerprint"), "voice_ws_task_request_fingerprint_invalid"
                    )
                    lease, _ = coordinator.start_task(
                        task_id=task_id,
                        kind=kind,
                        request_fingerprint=request_fingerprint,
                        cancellable=bool(payload.get("cancellable", True)),
                    )
                    response = _response_payload(controller, coordinator, event="task_started")
                    response["task_id"] = lease.task_id
                    response["task_kind"] = lease.kind
                    response["task_turn_epoch"] = lease.turn_epoch
                    response["task_request_fingerprint"] = lease.request_fingerprint
                elif event == "task_result":
                    task_id = str(payload.get("task_id", ""))
                    result_sha256 = _require_sha256(
                        payload.get("result_sha256"), "voice_ws_task_result_fingerprint_invalid"
                    )
                    lease = coordinator.lease_for(task_id)
                    governed_fp = payload.get("governed_provenance_fingerprint")
                    if lease.kind == "tool":
                        governed_fp = _require_sha256(
                            governed_fp, "voice_ws_tool_governed_provenance_invalid"
                        )
                    elif governed_fp is not None:
                        raise ValueError("voice_ws_non_tool_provenance_forbidden")
                    accepted = coordinator.accept_result(
                        lease=lease,
                        result_sha256=result_sha256,
                        governed_provenance_fingerprint=governed_fp,
                    )
                    response = _response_payload(controller, coordinator, event="task_result_accepted")
                    response["task_id"] = accepted.task_id
                    response["task_kind"] = accepted.kind
                    response["result_sha256"] = accepted.result_sha256
                    response["accepted_result_fingerprint"] = accepted.fingerprint
                    if accepted.governed_provenance_fingerprint is not None:
                        response["governed_provenance_fingerprint"] = accepted.governed_provenance_fingerprint
                elif event == "barge_in":
                    cancelled_ids = coordinator.cancel_for_barge_in()
                    response = _response_payload(controller, coordinator, event="cancelled")
                    response["cancelled_task_ids_sha256"] = hashlib.sha256(
                        json.dumps(cancelled_ids, separators=(",", ":")).encode("utf-8")
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
