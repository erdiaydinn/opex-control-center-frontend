from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from .voice_async_runtime import VoiceAsyncExecutionCoordinator
from .voice_deployment_binding import require_voice_deployment_bindings
from .voice_input_lineage import VoiceInputLineageTracker
from .voice_realtime_controller import VoiceRealtimeSessionController
from .voice_response_lineage import VoiceResponseGenerationProof
from .voice_ws_protocol import VoiceWsSequenceGuard, seal_envelope

router = APIRouter(tags=["voice"])


_ALLOWED_RUNTIME_MODES = {"production", "evaluation", "development", "test"}


def _voice_runtime_mode() -> str:
    mode = os.getenv("EAY_VOICE_RUNTIME_MODE", "production").strip().lower()
    if mode not in _ALLOWED_RUNTIME_MODES:
        raise ValueError("voice_runtime_mode_invalid")
    return mode


def _production_release_required() -> bool:
    return _voice_runtime_mode() == "production"


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
    """Governed local-first voice control plane pinned to one verified deployment."""
    try:
        runtime_mode = _voice_runtime_mode()
        require_release = runtime_mode == "production"
        bindings = require_voice_deployment_bindings(
            revalidate=True,
            require_production_release=require_release,
        )
        session_manifest_fingerprint = bindings.deployment_manifest_fingerprint
        session_release_decision_fingerprint = bindings.governed_release_decision_fingerprint
        session_runtime_attestation_fingerprint = bindings.runtime_attestation_bundle_fingerprint

        def _fresh_manifest_fingerprint() -> str:
            current = require_voice_deployment_bindings(
                revalidate=True,
                require_production_release=require_release,
            )
            if current.deployment_manifest_fingerprint != session_manifest_fingerprint:
                raise ValueError("voice_session_deployment_manifest_drift")
            if current.governed_release_decision_fingerprint != session_release_decision_fingerprint:
                raise ValueError("voice_session_release_decision_drift")
            if current.runtime_attestation_bundle_fingerprint != session_runtime_attestation_fingerprint:
                raise ValueError("voice_session_runtime_attestation_drift")
            return current.deployment_manifest_fingerprint

        controller = VoiceRealtimeSessionController(session_id=session_id, language=language)
        coordinator = VoiceAsyncExecutionCoordinator(
            controller=controller,
            deployment_manifest_fingerprint=session_manifest_fingerprint,
            deployment_freshness_check=_fresh_manifest_fingerprint,
        )
        input_lineage = VoiceInputLineageTracker(
            session_id=session_id,
            language=language,
            deployment_manifest_fingerprint=session_manifest_fingerprint,
            wakeword_identity_fingerprint=bindings.wakeword_identity_fingerprint,
            vad_identity_fingerprint=bindings.vad_identity_fingerprint,
            stt_identity_fingerprint=bindings.stt_identity_fingerprint,
        )
    except ValueError as exc:
        await websocket.close(code=1008, reason=str(exc))
        return

    guard = VoiceWsSequenceGuard()
    latest_user_input_sha256: str | None = None
    latest_input_lineage_fingerprint: str | None = None
    response_proofs: dict[str, VoiceResponseGenerationProof] = {}
    await websocket.accept()
    await websocket.send_json(
        {
            "event": "ready",
            "session_id": session_id,
            "language": language,
            "protocol_version": "eay-voice-ws-v1",
            "runtime_mode": runtime_mode,
            "production_released": bindings.production_released,
            "governed_release_decision_fingerprint": session_release_decision_fingerprint,
            "runtime_attestation_bundle_fingerprint": session_runtime_attestation_fingerprint,
            "turn_epoch": coordinator.turn_epoch,
            "deployment_manifest_fingerprint": session_manifest_fingerprint,
        }
    )

    def _fresh_bindings():
        _fresh_manifest_fingerprint()
        return require_voice_deployment_bindings(
            revalidate=True,
            require_production_release=require_release,
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
                if str(key).lower() in {"raw_audio", "audio_bytes", "transcript", "prompt", "result_text", "tts_text"}
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
                    _fresh_bindings()
                    controller.streaming.wake()
                    wake_proof = input_lineage.seal_wake()
                    response = _response_payload(controller, coordinator, event="listening")
                    response["wake_input_proof_fingerprint"] = wake_proof.fingerprint
                elif event == "audio_frame":
                    from .voice_streaming import AudioFrame

                    frame = AudioFrame(
                        sequence=int(payload["frame_sequence"]),
                        pcm_sha256=_require_sha256(payload["pcm_sha256"], "voice_ws_pcm_hash_invalid"),
                        duration_ms=int(payload["duration_ms"]),
                        sample_rate_hz=int(payload["sample_rate_hz"]),
                    )
                    controller.streaming.push_audio(frame)
                    frame_proof = input_lineage.seal_audio_frame(frame)
                    response = _response_payload(controller, coordinator, event="listening")
                    response["audio_frame_proof_fingerprint"] = frame_proof.fingerprint
                elif event == "stt_partial":
                    digest = _require_sha256(payload.get("text_sha256"), "voice_ws_stt_hash_invalid")
                    response = _response_payload(controller, coordinator, event="listening")
                    response["stt_partial_sha256"] = digest
                elif event == "stt_final":
                    _fresh_bindings()
                    digest = _require_sha256(payload.get("text_sha256"), "voice_ws_stt_hash_invalid")
                    input_proof = input_lineage.seal_stt_final(text_sha256=digest)
                    controller.memory.append(
                        role="user",
                        text=digest,
                        token_estimate=max(1, int(payload.get("token_estimate", 1))),
                    )
                    controller.streaming.machine.end_utterance()
                    coordinator.start_turn()
                    latest_user_input_sha256 = digest
                    latest_input_lineage_fingerprint = input_proof.fingerprint
                    response_proofs.clear()
                    response = _response_payload(controller, coordinator, event="thinking")
                    response["stt_final_sha256"] = digest
                    response["input_lineage_fingerprint"] = input_proof.fingerprint
                    response["input_audio_chain_fingerprint"] = input_proof.audio_chain_fingerprint
                    response["input_audio_frame_count"] = input_proof.audio_frame_count
                elif event == "task_start":
                    task_id = str(payload.get("task_id", ""))
                    kind = str(payload.get("kind", ""))
                    if kind in {"model", "tts"}:
                        raise ValueError("voice_ws_proof_bound_start_required")
                    request_fingerprint = _require_sha256(
                        payload.get("request_fingerprint"),
                        "voice_ws_task_request_fingerprint_invalid",
                    )
                    lease, _ = coordinator.start_task(
                        task_id=task_id,
                        kind=kind,
                        request_fingerprint=request_fingerprint,
                        cancellable=bool(payload.get("cancellable", True)),
                    )
                    response = _response_payload(controller, coordinator, event="task_started")
                    response.update(
                        {
                            "task_id": lease.task_id,
                            "task_kind": lease.kind,
                            "task_turn_epoch": lease.turn_epoch,
                            "task_request_fingerprint": lease.request_fingerprint,
                        }
                    )
                elif event == "response_start":
                    bindings = _fresh_bindings()
                    if latest_user_input_sha256 is None or latest_input_lineage_fingerprint is None:
                        raise ValueError("voice_ws_response_user_input_missing")
                    supplied_user_input = _require_sha256(
                        payload.get("user_input_sha256"),
                        "voice_ws_response_user_input_invalid",
                    )
                    if supplied_user_input != latest_user_input_sha256:
                        raise ValueError("voice_ws_response_user_input_mismatch")
                    task_id = str(payload.get("task_id", ""))
                    raw_tool_ids = payload.get("tool_task_ids", [])
                    if not isinstance(raw_tool_ids, list) or any(not isinstance(item, str) for item in raw_tool_ids):
                        raise ValueError("voice_ws_response_tool_task_ids_invalid")
                    legal_fp = payload.get("legal_context_fingerprint")
                    kpi_fp = payload.get("kpi_context_fingerprint")
                    if legal_fp is not None:
                        legal_fp = _require_sha256(legal_fp, "voice_ws_response_legal_context_invalid")
                    if kpi_fp is not None:
                        kpi_fp = _require_sha256(kpi_fp, "voice_ws_response_kpi_context_invalid")
                    proof = coordinator.seal_response_generation(
                        user_input_sha256=supplied_user_input,
                        input_lineage_fingerprint=latest_input_lineage_fingerprint,
                        deployment_manifest_fingerprint=session_manifest_fingerprint,
                        model_execution_identity=bindings.model,
                        tool_task_ids=tuple(raw_tool_ids),
                        legal_context_fingerprint=legal_fp,
                        kpi_context_fingerprint=kpi_fp,
                    )
                    response_proofs[proof.fingerprint] = proof
                    lease, _ = coordinator.start_task(
                        task_id=task_id,
                        kind="model",
                        request_fingerprint=proof.fingerprint,
                        cancellable=True,
                    )
                    response = _response_payload(controller, coordinator, event="response_started")
                    response.update(
                        {
                            "task_id": lease.task_id,
                            "response_proof_fingerprint": proof.fingerprint,
                            "input_lineage_fingerprint": proof.input_lineage_fingerprint,
                            "deployment_manifest_fingerprint": proof.deployment_manifest_fingerprint,
                            "model_execution_identity_fingerprint": proof.model_execution_identity_fingerprint,
                            "model_artifact_sha256": proof.model_artifact_sha256,
                            "task_request_fingerprint": lease.request_fingerprint,
                        }
                    )
                elif event == "tts_start":
                    bindings = _fresh_bindings()
                    forbidden_tts_overrides = {
                        "language",
                        "tts_bundle_fingerprint",
                        "tts_bundle_promotion_fingerprint",
                        "tts_language_artifact_fingerprint",
                        "tts_voice_model_sha256",
                        "tts_voice_config_sha256",
                        "tts_voice_tokens_sha256",
                        "tts_voice_model_card_sha256",
                        "tts_phonemizer_data_manifest_fingerprint",
                        "tts_phonemizer_license_id_sha256",
                        "tts_phonemizer_source_sha256",
                    }.intersection(payload)
                    if forbidden_tts_overrides:
                        raise ValueError("voice_ws_tts_server_binding_override_forbidden")
                    language_identity = bindings.require_tts_language(language)
                    if bindings.tts_bundle is None:
                        raise ValueError("voice_deployment_tts_bundle_unconfigured")
                    task_id = str(payload.get("task_id", ""))
                    response_proof_fp = _require_sha256(
                        payload.get("response_proof_fingerprint"),
                        "voice_ws_tts_response_proof_invalid",
                    )
                    response_proof = response_proofs.get(response_proof_fp)
                    if response_proof is None:
                        raise ValueError("voice_ws_tts_response_proof_unknown")
                    response_text_sha256 = _require_sha256(
                        payload.get("response_text_sha256"),
                        "voice_ws_tts_response_text_invalid",
                    )
                    voice_profile_fingerprint = _require_sha256(
                        payload.get("voice_profile_fingerprint"),
                        "voice_ws_tts_voice_profile_invalid",
                    )
                    proof = coordinator.seal_tts_generation(
                        response_proof=response_proof,
                        deployment_manifest_fingerprint=session_manifest_fingerprint,
                        response_text_sha256=response_text_sha256,
                        voice_profile_fingerprint=voice_profile_fingerprint,
                        tts_execution_identity=bindings.tts,
                        tts_bundle_execution_identity=bindings.tts_bundle,
                    )
                    if proof.tts_language_artifact_fingerprint != language_identity.fingerprint:
                        raise ValueError("voice_ws_tts_language_artifact_binding_drift")
                    lease, _ = coordinator.start_task(
                        task_id=task_id,
                        kind="tts",
                        request_fingerprint=proof.fingerprint,
                        cancellable=True,
                    )
                    response = _response_payload(controller, coordinator, event="tts_started")
                    response.update(
                        {
                            "task_id": lease.task_id,
                            "language": proof.language,
                            "tts_proof_fingerprint": proof.fingerprint,
                            "response_proof_fingerprint": proof.response_proof_fingerprint,
                            "deployment_manifest_fingerprint": proof.deployment_manifest_fingerprint,
                            "tts_execution_identity_fingerprint": proof.tts_execution_identity_fingerprint,
                            "tts_adapter_artifact_sha256": proof.tts_adapter_artifact_sha256,
                            "tts_adapter_promotion_fingerprint": proof.tts_adapter_promotion_fingerprint,
                            "tts_bundle_execution_identity_fingerprint": proof.tts_bundle_execution_identity_fingerprint,
                            "tts_bundle_fingerprint": proof.tts_bundle_fingerprint,
                            "tts_bundle_promotion_fingerprint": proof.tts_bundle_promotion_fingerprint,
                            "tts_language_artifact_fingerprint": proof.tts_language_artifact_fingerprint,
                            "tts_voice_model_sha256": proof.tts_voice_model_sha256,
                            "tts_voice_config_sha256": proof.tts_voice_config_sha256,
                            "tts_voice_tokens_sha256": proof.tts_voice_tokens_sha256,
                            "tts_voice_model_card_sha256": proof.tts_voice_model_card_sha256,
                            "tts_phonemizer_data_manifest_fingerprint": proof.tts_phonemizer_data_manifest_fingerprint,
                            "tts_phonemizer_license_id_sha256": proof.tts_phonemizer_license_id_sha256,
                            "tts_phonemizer_source_sha256": proof.tts_phonemizer_source_sha256,
                            "task_request_fingerprint": lease.request_fingerprint,
                        }
                    )
                elif event == "task_result":
                    _fresh_bindings()
                    task_id = str(payload.get("task_id", ""))
                    result_sha256 = _require_sha256(
                        payload.get("result_sha256"),
                        "voice_ws_task_result_fingerprint_invalid",
                    )
                    lease = coordinator.lease_for(task_id)
                    governed_fp = payload.get("governed_provenance_fingerprint")
                    if lease.kind == "tool":
                        governed_fp = _require_sha256(
                            governed_fp,
                            "voice_ws_tool_governed_provenance_invalid",
                        )
                    elif governed_fp is not None:
                        raise ValueError("voice_ws_non_tool_provenance_forbidden")
                    accepted = coordinator.accept_result(
                        lease=lease,
                        result_sha256=result_sha256,
                        governed_provenance_fingerprint=governed_fp,
                    )
                    response = _response_payload(controller, coordinator, event="task_result_accepted")
                    response.update(
                        {
                            "task_id": accepted.task_id,
                            "task_kind": accepted.kind,
                            "result_sha256": accepted.result_sha256,
                            "accepted_result_fingerprint": accepted.fingerprint,
                        }
                    )
                    if accepted.governed_provenance_fingerprint is not None:
                        response["governed_provenance_fingerprint"] = accepted.governed_provenance_fingerprint
                elif event == "barge_in":
                    cancelled_ids = coordinator.cancel_for_barge_in()
                    response_proofs.clear()
                    latest_user_input_sha256 = None
                    latest_input_lineage_fingerprint = None
                    response = _response_payload(controller, coordinator, event="cancelled")
                    response["cancelled_task_ids_sha256"] = hashlib.sha256(
                        json.dumps(cancelled_ids, separators=(",", ":")).encode("utf-8")
                    ).hexdigest()
                elif event == "approval":
                    response = _safe_error("voice_ws_approval_requires_bound_tool_intent")
                else:
                    response = _safe_error("voice_ws_event_not_supported_here")

                response["deployment_manifest_fingerprint"] = session_manifest_fingerprint
                response["envelope_fingerprint"] = envelope.fingerprint
                await websocket.send_json(response)
            except (KeyError, TypeError, ValueError) as exc:
                await websocket.send_json(_safe_error(str(exc)))
    except WebSocketDisconnect:
        return
