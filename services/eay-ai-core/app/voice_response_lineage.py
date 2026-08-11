from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Protocol


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


class AcceptedResultLike(Protocol):
    task_id: str
    kind: str
    turn_epoch: int
    result_sha256: str
    governed_provenance_fingerprint: str | None
    fingerprint: str


@dataclass(frozen=True)
class VoiceResponseGenerationProof:
    session_id: str
    turn_epoch: int
    user_input_sha256: str
    accepted_tool_result_fingerprints: tuple[str, ...]
    governed_tool_provenance_fingerprints: tuple[str, ...]
    legal_context_fingerprint: str | None
    kpi_context_fingerprint: str | None
    fingerprint: str


@dataclass(frozen=True)
class VoiceTtsGenerationProof:
    session_id: str
    turn_epoch: int
    response_proof_fingerprint: str
    response_text_sha256: str
    voice_profile_fingerprint: str
    fingerprint: str


def seal_response_generation_proof(
    *,
    session_id: str,
    turn_epoch: int,
    user_input_sha256: str,
    accepted_tool_results: Iterable[AcceptedResultLike] = (),
    legal_context_fingerprint: str | None = None,
    kpi_context_fingerprint: str | None = None,
) -> VoiceResponseGenerationProof:
    """Seal the exact governed evidence allowed to feed one spoken response.

    A tool result may influence response generation only when it was accepted in the
    same turn and carries an immutable governed execution provenance fingerprint.
    Optional legal/KPI context fingerprints are likewise pinned into the proof, so a
    response cannot silently move to newer evidence after generation starts.
    """

    session_id = session_id.strip()
    if len(session_id) < 3:
        raise ValueError("voice_response_session_id_required")
    if turn_epoch < 1:
        raise ValueError("voice_response_turn_epoch_invalid")
    if not _valid_sha256(user_input_sha256):
        raise ValueError("voice_response_user_input_fingerprint_invalid")
    if legal_context_fingerprint is not None and not _valid_sha256(legal_context_fingerprint):
        raise ValueError("voice_response_legal_context_fingerprint_invalid")
    if kpi_context_fingerprint is not None and not _valid_sha256(kpi_context_fingerprint):
        raise ValueError("voice_response_kpi_context_fingerprint_invalid")

    accepted_fps: list[str] = []
    governed_fps: list[str] = []
    seen_tasks: set[str] = set()
    for result in accepted_tool_results:
        if result.kind != "tool":
            raise ValueError("voice_response_non_tool_result_forbidden")
        if result.turn_epoch != turn_epoch:
            raise ValueError("voice_response_stale_tool_result_forbidden")
        if result.task_id in seen_tasks:
            raise ValueError("voice_response_duplicate_tool_result_forbidden")
        if not _valid_sha256(result.fingerprint):
            raise ValueError("voice_response_tool_result_fingerprint_invalid")
        if not _valid_sha256(result.governed_provenance_fingerprint):
            raise ValueError("voice_response_tool_governed_provenance_required")
        seen_tasks.add(result.task_id)
        accepted_fps.append(result.fingerprint)
        governed_fps.append(str(result.governed_provenance_fingerprint))

    accepted_tuple = tuple(sorted(accepted_fps))
    governed_tuple = tuple(sorted(governed_fps))
    payload = {
        "session_id": session_id,
        "turn_epoch": turn_epoch,
        "user_input_sha256": user_input_sha256,
        "accepted_tool_result_fingerprints": accepted_tuple,
        "governed_tool_provenance_fingerprints": governed_tuple,
        "legal_context_fingerprint": legal_context_fingerprint,
        "kpi_context_fingerprint": kpi_context_fingerprint,
    }
    return VoiceResponseGenerationProof(
        **payload,
        fingerprint=_sha256(payload),
    )


def seal_tts_generation_proof(
    *,
    response_proof: VoiceResponseGenerationProof,
    current_turn_epoch: int,
    response_text_sha256: str,
    voice_profile_fingerprint: str,
) -> VoiceTtsGenerationProof:
    """Authorize TTS only from an exact, current-turn response-generation proof."""

    if response_proof.turn_epoch != current_turn_epoch:
        raise ValueError("voice_tts_stale_response_proof_forbidden")
    if not _valid_sha256(response_proof.fingerprint):
        raise ValueError("voice_tts_response_proof_fingerprint_invalid")
    if not _valid_sha256(response_text_sha256):
        raise ValueError("voice_tts_response_text_fingerprint_invalid")
    if not _valid_sha256(voice_profile_fingerprint):
        raise ValueError("voice_tts_voice_profile_fingerprint_invalid")

    payload = {
        "session_id": response_proof.session_id,
        "turn_epoch": response_proof.turn_epoch,
        "response_proof_fingerprint": response_proof.fingerprint,
        "response_text_sha256": response_text_sha256,
        "voice_profile_fingerprint": voice_profile_fingerprint,
    }
    return VoiceTtsGenerationProof(**payload, fingerprint=_sha256(payload))
