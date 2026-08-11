from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .language_capability import LanguageCapability
from .model_artifact_provenance import ModelArtifactProvenanceRegistry
from .model_promotion_gate import ModelPromotionGate
from .voice_adapter_promotion import VoiceAdapterPromotionRegistry, adapter_fingerprint
from .voice_execution_identity import VoiceModelExecutionIdentity, seal_model_execution_identity
from .voice_runtime import VoiceProfile


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceAdapterDeploymentIdentity:
    adapter_id: str
    kind: str
    artifact_sha256: str
    adapter_fingerprint: str
    promotion_fingerprint: str
    profile_fingerprint: str
    language_capability_fingerprints: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class VoiceRuntimeDeploymentManifest:
    model_record_id: str
    model_production_promotion_fingerprint: str
    model_release_proof_fingerprint: str
    model_execution_identity_fingerprint: str
    model_artifact_sha256: str
    profile_fingerprint: str
    adapter_identity_fingerprints: tuple[str, ...]
    wakeword_identity_fingerprint: str
    vad_identity_fingerprint: str
    stt_identity_fingerprint: str
    tts_identity_fingerprint: str
    fingerprint: str


def _seal_adapter_identity(*, adapter, profile, promotion) -> VoiceAdapterDeploymentIdentity:
    current_fp = adapter_fingerprint(adapter)
    if current_fp != promotion.adapter_fingerprint:
        raise ValueError("voice_deployment_adapter_fingerprint_drift")
    if adapter.artifact_sha256 != promotion.adapter_artifact_sha256:
        raise ValueError("voice_deployment_adapter_artifact_drift")
    if profile.fingerprint != promotion.profile_fingerprint:
        raise ValueError("voice_deployment_profile_drift")
    payload = {
        "adapter_id": adapter.adapter_id,
        "kind": adapter.kind,
        "artifact_sha256": adapter.artifact_sha256,
        "adapter_fingerprint": current_fp,
        "promotion_fingerprint": promotion.fingerprint,
        "profile_fingerprint": profile.fingerprint,
        "language_capability_fingerprints": tuple(sorted(promotion.language_capability_fingerprints)),
    }
    return VoiceAdapterDeploymentIdentity(**payload, fingerprint=_sha256(payload))


def build_verified_voice_deployment_manifest(
    *,
    db_path: Path,
    model_record_id: str,
    profile: VoiceProfile,
    capabilities: Iterable[LanguageCapability],
) -> tuple[VoiceRuntimeDeploymentManifest, VoiceModelExecutionIdentity]:
    """Build a startup manifest only from currently verified production registries.

    No caller-authored model/adapter fingerprints are trusted. The model must still be
    the exact production promotion head and every wake/VAD/STT/TTS adapter must still
    match its immutable human-gated promotion, artifact, profile and language evals.
    """
    profile.validate()
    caps = tuple(capabilities)
    production = ModelPromotionGate(db_path).require_current_production(model_record_id=model_record_id)
    artifact = ModelArtifactProvenanceRegistry(db_path).verify_artifact(
        artifact_sha256=production.artifact_sha256,
        training_job_fingerprint=production.training_job_fingerprint,
    )
    model_identity = seal_model_execution_identity(artifact)

    registry = VoiceAdapterPromotionRegistry(db_path)
    by_kind: dict[str, VoiceAdapterDeploymentIdentity] = {}
    for adapter in profile.adapters:
        promotion = registry.verify(adapter=adapter, profile=profile, capabilities=caps)
        identity = _seal_adapter_identity(adapter=adapter, profile=profile, promotion=promotion)
        if identity.kind in by_kind:
            raise ValueError("voice_deployment_duplicate_adapter_kind")
        by_kind[identity.kind] = identity
    required = {"wakeword", "vad", "stt", "tts"}
    if set(by_kind) != required:
        raise ValueError("voice_deployment_adapter_coverage_incomplete")

    ordered = tuple(by_kind[k].fingerprint for k in ("wakeword", "vad", "stt", "tts"))
    payload = {
        "model_record_id": model_record_id,
        "model_production_promotion_fingerprint": production.fingerprint,
        "model_release_proof_fingerprint": production.release_proof_fingerprint,
        "model_execution_identity_fingerprint": model_identity.fingerprint,
        "model_artifact_sha256": model_identity.artifact_sha256,
        "profile_fingerprint": profile.fingerprint,
        "adapter_identity_fingerprints": ordered,
        "wakeword_identity_fingerprint": by_kind["wakeword"].fingerprint,
        "vad_identity_fingerprint": by_kind["vad"].fingerprint,
        "stt_identity_fingerprint": by_kind["stt"].fingerprint,
        "tts_identity_fingerprint": by_kind["tts"].fingerprint,
    }
    return VoiceRuntimeDeploymentManifest(**payload, fingerprint=_sha256(payload)), model_identity
