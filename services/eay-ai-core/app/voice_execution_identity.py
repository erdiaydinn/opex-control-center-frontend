from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .model_artifact_provenance import ArtifactRecord
from .voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from .voice_runtime import VoiceAdapterSpec, VoiceProfile


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceModelExecutionIdentity:
    artifact_sha256: str
    artifact_provenance_fingerprint: str
    training_job_fingerprint: str
    artifact_format: str
    build_reference_sha256: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceTtsExecutionIdentity:
    adapter_id: str
    implementation: str
    license_id: str
    license_id_sha256: str
    artifact_sha256: str
    adapter_fingerprint: str
    promotion_fingerprint: str
    profile_fingerprint: str
    language_capability_fingerprints: tuple[str, ...]
    fingerprint: str


def seal_model_execution_identity(record: ArtifactRecord) -> VoiceModelExecutionIdentity:
    """Bind one voice response to an exact registered local model artifact.

    The identity carries artifact bytes, registered artifact provenance and the exact
    training-job lineage. Build references are hashed so audit lineage does not need to
    expose deployment-internal paths or CI references.
    """

    if not _valid_sha256(record.artifact_sha256):
        raise ValueError("voice_model_artifact_sha256_invalid")
    if not _valid_sha256(record.fingerprint):
        raise ValueError("voice_model_artifact_provenance_invalid")
    if not _valid_sha256(record.training_job_fingerprint):
        raise ValueError("voice_model_training_lineage_invalid")
    if len(record.format.strip()) < 2:
        raise ValueError("voice_model_artifact_format_required")
    if len(record.build_reference.strip()) < 2:
        raise ValueError("voice_model_build_reference_required")

    payload = {
        "artifact_sha256": record.artifact_sha256,
        "artifact_provenance_fingerprint": record.fingerprint,
        "training_job_fingerprint": record.training_job_fingerprint,
        "artifact_format": record.format.strip().lower(),
        "build_reference_sha256": hashlib.sha256(record.build_reference.strip().encode("utf-8")).hexdigest(),
    }
    return VoiceModelExecutionIdentity(**payload, fingerprint=_sha256(payload))


def seal_tts_execution_identity(
    *,
    adapter: VoiceAdapterSpec,
    profile: VoiceProfile,
    promotion: VoiceAdapterPromotion,
) -> VoiceTtsExecutionIdentity:
    """Bind TTS execution to the exact promoted adapter bytes/license/profile.

    A stale promotion cannot authorize changed model bytes, implementation, license or
    voice profile. This function intentionally accepts a verified promotion record, not
    a caller-authored promotion fingerprint.
    """

    profile.validate()
    adapter.validate()
    if adapter.kind != "tts":
        raise ValueError("voice_tts_execution_requires_tts_adapter")
    if adapter.adapter_id != promotion.adapter_id or promotion.kind != "tts":
        raise ValueError("voice_tts_execution_promotion_identity_mismatch")
    if adapter.artifact_sha256 != promotion.adapter_artifact_sha256:
        raise ValueError("voice_tts_execution_artifact_drift")
    current_adapter_fp = adapter_fingerprint(adapter)
    if current_adapter_fp != promotion.adapter_fingerprint:
        raise ValueError("voice_tts_execution_adapter_drift")
    if profile.fingerprint != promotion.profile_fingerprint:
        raise ValueError("voice_tts_execution_profile_drift")
    if not _valid_sha256(promotion.fingerprint):
        raise ValueError("voice_tts_execution_promotion_fingerprint_invalid")
    if not promotion.language_capability_fingerprints or any(
        not _valid_sha256(item) for item in promotion.language_capability_fingerprints
    ):
        raise ValueError("voice_tts_execution_language_capability_lineage_invalid")

    license_id = adapter.license_id.strip().lower()
    payload = {
        "adapter_id": adapter.adapter_id,
        "implementation": adapter.implementation.strip(),
        "license_id": license_id,
        "license_id_sha256": hashlib.sha256(license_id.encode("utf-8")).hexdigest(),
        "artifact_sha256": str(adapter.artifact_sha256),
        "adapter_fingerprint": current_adapter_fp,
        "promotion_fingerprint": promotion.fingerprint,
        "profile_fingerprint": profile.fingerprint,
        "language_capability_fingerprints": tuple(sorted(promotion.language_capability_fingerprints)),
    }
    return VoiceTtsExecutionIdentity(**payload, fingerprint=_sha256(payload))
