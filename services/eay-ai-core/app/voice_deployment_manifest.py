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
from .voice_tts_bundle import (
    VoiceTtsArtifactBundle,
    VoiceTtsBundlePromotionRegistry,
    seal_tts_bundle_execution_identity,
)


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
    tts_bundle_execution_identity_fingerprint: str
    tts_bundle_fingerprint: str
    tts_bundle_promotion_fingerprint: str
    tts_language_artifact_fingerprints: tuple[str, ...]
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
    tts_bundle: VoiceTtsArtifactBundle,
) -> tuple[VoiceRuntimeDeploymentManifest, VoiceModelExecutionIdentity]:
    """Build a startup manifest only from currently verified production registries.

    No caller-authored model/adapter/bundle fingerprints are trusted. The model must
    still be the exact production promotion head, every wake/VAD/STT/TTS adapter must
    match its immutable promotion, and the full five-language TTS artifact bundle must
    still match its separate human-gated bundle promotion.
    """
    profile.validate()
    tts_bundle.validate()
    caps = tuple(capabilities)
    production = ModelPromotionGate(db_path).require_current_production(model_record_id=model_record_id)
    artifact = ModelArtifactProvenanceRegistry(db_path).verify_artifact(
        artifact_sha256=production.artifact_sha256,
        training_job_fingerprint=production.training_job_fingerprint,
    )
    model_identity = seal_model_execution_identity(artifact)

    registry = VoiceAdapterPromotionRegistry(db_path)
    by_kind: dict[str, VoiceAdapterDeploymentIdentity] = {}
    adapters_by_kind = {}
    for adapter in profile.adapters:
        promotion = registry.verify(adapter=adapter, profile=profile, capabilities=caps)
        identity = _seal_adapter_identity(adapter=adapter, profile=profile, promotion=promotion)
        if identity.kind in by_kind:
            raise ValueError("voice_deployment_duplicate_adapter_kind")
        by_kind[identity.kind] = identity
        adapters_by_kind[identity.kind] = adapter
    required = {"wakeword", "vad", "stt", "tts"}
    if set(by_kind) != required:
        raise ValueError("voice_deployment_adapter_coverage_incomplete")

    tts_adapter = adapters_by_kind["tts"]
    bundle_promotion = VoiceTtsBundlePromotionRegistry(db_path).verify(
        bundle=tts_bundle,
        runtime_adapter=tts_adapter,
        profile=profile,
        capabilities=caps,
    )
    bundle_identity = seal_tts_bundle_execution_identity(bundle=tts_bundle, promotion=bundle_promotion)
    if bundle_identity.runtime_adapter_id != tts_adapter.adapter_id:
        raise ValueError("voice_deployment_tts_bundle_runtime_adapter_mismatch")
    if bundle_identity.runtime_adapter_promotion_fingerprint != by_kind["tts"].promotion_fingerprint:
        raise ValueError("voice_deployment_tts_bundle_runtime_promotion_mismatch")
    if bundle_identity.profile_fingerprint != profile.fingerprint:
        raise ValueError("voice_deployment_tts_bundle_profile_mismatch")

    ordered = tuple(by_kind[k].fingerprint for k in ("wakeword", "vad", "stt", "tts"))
    language_artifact_fps = tuple(
        bundle_identity.artifact_for(language).fingerprint for language in profile.languages
    )
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
        "tts_bundle_execution_identity_fingerprint": bundle_identity.fingerprint,
        "tts_bundle_fingerprint": bundle_identity.bundle_fingerprint,
        "tts_bundle_promotion_fingerprint": bundle_identity.bundle_promotion_fingerprint,
        "tts_language_artifact_fingerprints": language_artifact_fps,
    }
    return VoiceRuntimeDeploymentManifest(**payload, fingerprint=_sha256(payload)), model_identity
