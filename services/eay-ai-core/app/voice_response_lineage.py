from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable, Protocol

from .voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity
from .voice_tts_bundle import VoiceTtsBundleExecutionIdentity


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
    input_lineage_fingerprint: str
    accepted_tool_result_fingerprints: tuple[str, ...]
    governed_tool_provenance_fingerprints: tuple[str, ...]
    legal_context_fingerprint: str | None
    kpi_context_fingerprint: str | None
    deployment_manifest_fingerprint: str
    model_execution_identity_fingerprint: str
    model_artifact_sha256: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceTtsGenerationProof:
    session_id: str
    turn_epoch: int
    language: str
    response_proof_fingerprint: str
    response_text_sha256: str
    voice_profile_fingerprint: str
    deployment_manifest_fingerprint: str
    tts_execution_identity_fingerprint: str
    tts_adapter_artifact_sha256: str
    tts_adapter_promotion_fingerprint: str
    tts_bundle_execution_identity_fingerprint: str
    tts_bundle_fingerprint: str
    tts_bundle_promotion_fingerprint: str
    tts_language_artifact_fingerprint: str
    tts_voice_model_sha256: str
    tts_voice_config_sha256: str
    tts_voice_tokens_sha256: str
    tts_voice_model_card_sha256: str
    tts_voice_license_id_sha256: str
    tts_phonemizer_data_manifest_fingerprint: str
    tts_phonemizer_license_id_sha256: str
    tts_phonemizer_source_sha256: str
    fingerprint: str

    def _payload(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "turn_epoch": self.turn_epoch,
            "language": self.language,
            "response_proof_fingerprint": self.response_proof_fingerprint,
            "response_text_sha256": self.response_text_sha256,
            "voice_profile_fingerprint": self.voice_profile_fingerprint,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "tts_execution_identity_fingerprint": self.tts_execution_identity_fingerprint,
            "tts_adapter_artifact_sha256": self.tts_adapter_artifact_sha256,
            "tts_adapter_promotion_fingerprint": self.tts_adapter_promotion_fingerprint,
            "tts_bundle_execution_identity_fingerprint": self.tts_bundle_execution_identity_fingerprint,
            "tts_bundle_fingerprint": self.tts_bundle_fingerprint,
            "tts_bundle_promotion_fingerprint": self.tts_bundle_promotion_fingerprint,
            "tts_language_artifact_fingerprint": self.tts_language_artifact_fingerprint,
            "tts_voice_model_sha256": self.tts_voice_model_sha256,
            "tts_voice_config_sha256": self.tts_voice_config_sha256,
            "tts_voice_tokens_sha256": self.tts_voice_tokens_sha256,
            "tts_voice_model_card_sha256": self.tts_voice_model_card_sha256,
            "tts_voice_license_id_sha256": self.tts_voice_license_id_sha256,
            "tts_phonemizer_data_manifest_fingerprint": self.tts_phonemizer_data_manifest_fingerprint,
            "tts_phonemizer_license_id_sha256": self.tts_phonemizer_license_id_sha256,
            "tts_phonemizer_source_sha256": self.tts_phonemizer_source_sha256,
        }

    def validate(self) -> None:
        if len(self.session_id.strip()) < 3:
            raise ValueError("voice_tts_proof_session_id_required")
        if self.turn_epoch < 1:
            raise ValueError("voice_tts_proof_turn_epoch_invalid")
        if not self.language.strip():
            raise ValueError("voice_tts_proof_language_required")
        for value, code in (
            (self.response_proof_fingerprint, "voice_tts_proof_response_fingerprint_invalid"),
            (self.response_text_sha256, "voice_tts_proof_response_text_hash_invalid"),
            (self.voice_profile_fingerprint, "voice_tts_proof_profile_fingerprint_invalid"),
            (self.deployment_manifest_fingerprint, "voice_tts_proof_deployment_manifest_invalid"),
            (self.tts_execution_identity_fingerprint, "voice_tts_proof_execution_identity_invalid"),
            (self.tts_adapter_artifact_sha256, "voice_tts_proof_adapter_artifact_hash_invalid"),
            (self.tts_adapter_promotion_fingerprint, "voice_tts_proof_adapter_promotion_invalid"),
            (self.tts_bundle_execution_identity_fingerprint, "voice_tts_proof_bundle_identity_invalid"),
            (self.tts_bundle_fingerprint, "voice_tts_proof_bundle_fingerprint_invalid"),
            (self.tts_bundle_promotion_fingerprint, "voice_tts_proof_bundle_promotion_invalid"),
            (self.tts_language_artifact_fingerprint, "voice_tts_proof_language_artifact_invalid"),
            (self.tts_voice_model_sha256, "voice_tts_proof_voice_model_hash_invalid"),
            (self.tts_voice_config_sha256, "voice_tts_proof_voice_config_hash_invalid"),
            (self.tts_voice_tokens_sha256, "voice_tts_proof_voice_tokens_hash_invalid"),
            (self.tts_voice_model_card_sha256, "voice_tts_proof_model_card_hash_invalid"),
            (self.tts_voice_license_id_sha256, "voice_tts_proof_voice_license_hash_invalid"),
            (self.tts_phonemizer_data_manifest_fingerprint, "voice_tts_proof_phonemizer_manifest_invalid"),
            (self.tts_phonemizer_license_id_sha256, "voice_tts_proof_phonemizer_license_invalid"),
            (self.tts_phonemizer_source_sha256, "voice_tts_proof_phonemizer_source_invalid"),
            (self.fingerprint, "voice_tts_proof_fingerprint_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)
        if _sha256(self._payload()) != self.fingerprint:
            raise ValueError("voice_tts_proof_fingerprint_drift")


def seal_response_generation_proof(
    *,
    session_id: str,
    turn_epoch: int,
    user_input_sha256: str,
    input_lineage_fingerprint: str,
    deployment_manifest_fingerprint: str,
    model_execution_identity: VoiceModelExecutionIdentity,
    accepted_tool_results: Iterable[AcceptedResultLike] = (),
    legal_context_fingerprint: str | None = None,
    kpi_context_fingerprint: str | None = None,
) -> VoiceResponseGenerationProof:
    session_id = session_id.strip()
    if len(session_id) < 3:
        raise ValueError("voice_response_session_id_required")
    if turn_epoch < 1:
        raise ValueError("voice_response_turn_epoch_invalid")
    if not _valid_sha256(user_input_sha256):
        raise ValueError("voice_response_user_input_fingerprint_invalid")
    if not _valid_sha256(input_lineage_fingerprint):
        raise ValueError("voice_response_input_lineage_required")
    if not _valid_sha256(deployment_manifest_fingerprint):
        raise ValueError("voice_response_deployment_manifest_required")
    if not _valid_sha256(model_execution_identity.fingerprint):
        raise ValueError("voice_response_model_execution_identity_required")
    if not _valid_sha256(model_execution_identity.artifact_sha256):
        raise ValueError("voice_response_model_artifact_required")
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

    payload = {
        "session_id": session_id,
        "turn_epoch": turn_epoch,
        "user_input_sha256": user_input_sha256,
        "input_lineage_fingerprint": input_lineage_fingerprint,
        "accepted_tool_result_fingerprints": tuple(sorted(accepted_fps)),
        "governed_tool_provenance_fingerprints": tuple(sorted(governed_fps)),
        "legal_context_fingerprint": legal_context_fingerprint,
        "kpi_context_fingerprint": kpi_context_fingerprint,
        "deployment_manifest_fingerprint": deployment_manifest_fingerprint,
        "model_execution_identity_fingerprint": model_execution_identity.fingerprint,
        "model_artifact_sha256": model_execution_identity.artifact_sha256,
    }
    return VoiceResponseGenerationProof(**payload, fingerprint=_sha256(payload))


def seal_tts_generation_proof(
    *,
    response_proof: VoiceResponseGenerationProof,
    current_turn_epoch: int,
    language: str,
    deployment_manifest_fingerprint: str,
    response_text_sha256: str,
    voice_profile_fingerprint: str,
    tts_execution_identity: VoiceTtsExecutionIdentity,
    tts_bundle_execution_identity: VoiceTtsBundleExecutionIdentity,
) -> VoiceTtsGenerationProof:
    if response_proof.turn_epoch != current_turn_epoch:
        raise ValueError("voice_tts_stale_response_proof_forbidden")
    if not _valid_sha256(response_proof.fingerprint):
        raise ValueError("voice_tts_response_proof_fingerprint_invalid")
    if not _valid_sha256(deployment_manifest_fingerprint):
        raise ValueError("voice_tts_deployment_manifest_required")
    if response_proof.deployment_manifest_fingerprint != deployment_manifest_fingerprint:
        raise ValueError("voice_tts_deployment_manifest_mismatch")
    if not _valid_sha256(response_text_sha256):
        raise ValueError("voice_tts_response_text_fingerprint_invalid")
    if not _valid_sha256(voice_profile_fingerprint):
        raise ValueError("voice_tts_voice_profile_fingerprint_invalid")
    if not _valid_sha256(tts_execution_identity.fingerprint):
        raise ValueError("voice_tts_execution_identity_required")
    if tts_execution_identity.profile_fingerprint != voice_profile_fingerprint:
        raise ValueError("voice_tts_execution_profile_mismatch")

    tts_bundle_execution_identity.validate()
    if tts_bundle_execution_identity.profile_fingerprint != voice_profile_fingerprint:
        raise ValueError("voice_tts_bundle_profile_mismatch")
    if tts_bundle_execution_identity.runtime_adapter_id != tts_execution_identity.adapter_id:
        raise ValueError("voice_tts_bundle_adapter_mismatch")
    if tts_bundle_execution_identity.runtime_adapter_promotion_fingerprint != tts_execution_identity.promotion_fingerprint:
        raise ValueError("voice_tts_bundle_runtime_promotion_mismatch")
    language_artifact = tts_bundle_execution_identity.artifact_for(language)

    payload = {
        "session_id": response_proof.session_id,
        "turn_epoch": response_proof.turn_epoch,
        "language": language_artifact.language,
        "response_proof_fingerprint": response_proof.fingerprint,
        "response_text_sha256": response_text_sha256,
        "voice_profile_fingerprint": voice_profile_fingerprint,
        "deployment_manifest_fingerprint": deployment_manifest_fingerprint,
        "tts_execution_identity_fingerprint": tts_execution_identity.fingerprint,
        "tts_adapter_artifact_sha256": tts_execution_identity.artifact_sha256,
        "tts_adapter_promotion_fingerprint": tts_execution_identity.promotion_fingerprint,
        "tts_bundle_execution_identity_fingerprint": tts_bundle_execution_identity.fingerprint,
        "tts_bundle_fingerprint": tts_bundle_execution_identity.bundle_fingerprint,
        "tts_bundle_promotion_fingerprint": tts_bundle_execution_identity.bundle_promotion_fingerprint,
        "tts_language_artifact_fingerprint": language_artifact.fingerprint,
        "tts_voice_model_sha256": language_artifact.model_sha256,
        "tts_voice_config_sha256": language_artifact.config_sha256,
        "tts_voice_tokens_sha256": language_artifact.tokens_sha256,
        "tts_voice_model_card_sha256": language_artifact.model_card_sha256,
        "tts_voice_license_id_sha256": language_artifact.artifact_license_id_sha256,
        "tts_phonemizer_data_manifest_fingerprint": tts_bundle_execution_identity.phonemizer_data_manifest_fingerprint,
        "tts_phonemizer_license_id_sha256": tts_bundle_execution_identity.phonemizer_license_id_sha256,
        "tts_phonemizer_source_sha256": tts_bundle_execution_identity.phonemizer_source_sha256,
    }
    proof = VoiceTtsGenerationProof(**payload, fingerprint=_sha256(payload))
    proof.validate()
    return proof
