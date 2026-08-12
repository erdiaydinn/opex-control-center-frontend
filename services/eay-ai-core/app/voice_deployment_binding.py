from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .language_capability import LanguageCapability
from .voice_adapter_promotion import VoiceAdapterPromotionRegistry
from .voice_deployment_manifest import VoiceRuntimeDeploymentManifest, build_verified_voice_deployment_manifest
from .voice_execution_identity import (
    VoiceModelExecutionIdentity,
    VoiceTtsExecutionIdentity,
    seal_tts_execution_identity,
)
from .voice_runtime import VoiceProfile
from .voice_tts_bundle import (
    VoiceTtsArtifactBundle,
    VoiceTtsBundleExecutionIdentity,
    VoiceTtsBundlePromotionRegistry,
    VoiceTtsLanguageExecutionIdentity,
    seal_tts_bundle_execution_identity,
)


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceDeploymentExecutionBindings:
    """Server-owned exact execution identities for one deployed voice runtime."""

    model: VoiceModelExecutionIdentity
    tts: VoiceTtsExecutionIdentity
    deployment_manifest_fingerprint: str
    wakeword_identity_fingerprint: str = "0" * 64
    vad_identity_fingerprint: str = "0" * 64
    stt_identity_fingerprint: str = "0" * 64
    model_record_id: str = "synthetic-test-binding"
    tts_bundle: VoiceTtsBundleExecutionIdentity | None = None

    def validate(self) -> None:
        if not _valid_sha256(self.model.fingerprint) or not _valid_sha256(self.model.artifact_sha256):
            raise ValueError("voice_deployment_model_identity_invalid")
        if not _valid_sha256(self.tts.fingerprint) or not _valid_sha256(self.tts.artifact_sha256):
            raise ValueError("voice_deployment_tts_identity_invalid")
        if not _valid_sha256(self.tts.promotion_fingerprint):
            raise ValueError("voice_deployment_tts_promotion_invalid")
        if not _valid_sha256(self.deployment_manifest_fingerprint):
            raise ValueError("voice_deployment_manifest_fingerprint_invalid")
        for value, code in (
            (self.wakeword_identity_fingerprint, "voice_deployment_wakeword_identity_invalid"),
            (self.vad_identity_fingerprint, "voice_deployment_vad_identity_invalid"),
            (self.stt_identity_fingerprint, "voice_deployment_stt_identity_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)
        if len(self.model_record_id.strip()) < 3:
            raise ValueError("voice_deployment_model_record_id_required")
        if self.tts_bundle is not None:
            self.tts_bundle.validate()
            if self.tts_bundle.runtime_adapter_id != self.tts.adapter_id:
                raise ValueError("voice_deployment_tts_bundle_adapter_mismatch")
            if self.tts_bundle.runtime_adapter_promotion_fingerprint != self.tts.promotion_fingerprint:
                raise ValueError("voice_deployment_tts_bundle_promotion_mismatch")
            if self.tts_bundle.profile_fingerprint != self.tts.profile_fingerprint:
                raise ValueError("voice_deployment_tts_bundle_profile_mismatch")

    def require_tts_language(self, language: str) -> VoiceTtsLanguageExecutionIdentity:
        if self.tts_bundle is None:
            raise ValueError("voice_deployment_tts_bundle_unconfigured")
        self.tts_bundle.validate()
        return self.tts_bundle.artifact_for(language)


@dataclass(frozen=True)
class _VerifiedDeploymentSource:
    db_path: Path
    model_record_id: str
    profile: VoiceProfile
    capabilities: tuple[LanguageCapability, ...]
    tts_bundle: VoiceTtsArtifactBundle


_BINDINGS: VoiceDeploymentExecutionBindings | None = None
_VERIFIED_SOURCE: _VerifiedDeploymentSource | None = None


def configure_voice_deployment_bindings(bindings: VoiceDeploymentExecutionBindings) -> None:
    """Install an already-verified binding.

    This low-level function is retained for isolated tests and embedding. Production
    deployments should call ``configure_verified_voice_deployment`` so every new turn
    can revalidate the registries behind the pinned deployment manifest. If no TTS
    bundle identity is supplied here, TTS start remains fail-closed.
    """

    global _BINDINGS, _VERIFIED_SOURCE
    bindings.validate()
    _BINDINGS = bindings
    _VERIFIED_SOURCE = None


def configure_verified_voice_deployment(
    *,
    db_path: Path,
    model_record_id: str,
    profile: VoiceProfile,
    capabilities: Iterable[LanguageCapability],
    tts_bundle: VoiceTtsArtifactBundle,
) -> VoiceRuntimeDeploymentManifest:
    """Build and install bindings only from current production registries."""

    global _BINDINGS, _VERIFIED_SOURCE
    caps = tuple(capabilities)
    manifest, model_identity = build_verified_voice_deployment_manifest(
        db_path=db_path,
        model_record_id=model_record_id,
        profile=profile,
        capabilities=caps,
        tts_bundle=tts_bundle,
    )
    tts_adapter = next((adapter for adapter in profile.adapters if adapter.kind == "tts"), None)
    if tts_adapter is None:
        raise ValueError("voice_deployment_tts_adapter_missing")
    tts_promotion = VoiceAdapterPromotionRegistry(db_path).verify(
        adapter=tts_adapter,
        profile=profile,
        capabilities=caps,
    )
    tts_identity = seal_tts_execution_identity(
        adapter=tts_adapter,
        profile=profile,
        promotion=tts_promotion,
    )
    bundle_promotion = VoiceTtsBundlePromotionRegistry(db_path).verify(
        bundle=tts_bundle,
        runtime_adapter=tts_adapter,
        profile=profile,
        capabilities=caps,
    )
    bundle_identity = seal_tts_bundle_execution_identity(bundle=tts_bundle, promotion=bundle_promotion)
    if bundle_identity.fingerprint != manifest.tts_bundle_execution_identity_fingerprint:
        raise ValueError("voice_deployment_tts_bundle_manifest_mismatch")

    bindings = VoiceDeploymentExecutionBindings(
        model=model_identity,
        tts=tts_identity,
        deployment_manifest_fingerprint=manifest.fingerprint,
        wakeword_identity_fingerprint=manifest.wakeword_identity_fingerprint,
        vad_identity_fingerprint=manifest.vad_identity_fingerprint,
        stt_identity_fingerprint=manifest.stt_identity_fingerprint,
        model_record_id=model_record_id,
        tts_bundle=bundle_identity,
    )
    bindings.validate()
    _BINDINGS = bindings
    _VERIFIED_SOURCE = _VerifiedDeploymentSource(
        db_path=Path(db_path),
        model_record_id=model_record_id,
        profile=profile,
        capabilities=caps,
        tts_bundle=tts_bundle,
    )
    return manifest


def clear_voice_deployment_bindings() -> None:
    global _BINDINGS, _VERIFIED_SOURCE
    _BINDINGS = None
    _VERIFIED_SOURCE = None


def _revalidate_verified_source(bindings: VoiceDeploymentExecutionBindings) -> None:
    source = _VERIFIED_SOURCE
    if source is None:
        return
    manifest, model_identity = build_verified_voice_deployment_manifest(
        db_path=source.db_path,
        model_record_id=source.model_record_id,
        profile=source.profile,
        capabilities=source.capabilities,
        tts_bundle=source.tts_bundle,
    )
    if manifest.fingerprint != bindings.deployment_manifest_fingerprint:
        raise ValueError("voice_deployment_manifest_drift")
    if model_identity.fingerprint != bindings.model.fingerprint:
        raise ValueError("voice_deployment_model_identity_drift")
    if manifest.wakeword_identity_fingerprint != bindings.wakeword_identity_fingerprint:
        raise ValueError("voice_deployment_wakeword_identity_drift")
    if manifest.vad_identity_fingerprint != bindings.vad_identity_fingerprint:
        raise ValueError("voice_deployment_vad_identity_drift")
    if manifest.stt_identity_fingerprint != bindings.stt_identity_fingerprint:
        raise ValueError("voice_deployment_stt_identity_drift")
    tts_adapter = next((adapter for adapter in source.profile.adapters if adapter.kind == "tts"), None)
    if tts_adapter is None:
        raise ValueError("voice_deployment_tts_adapter_missing")
    promotion = VoiceAdapterPromotionRegistry(source.db_path).verify(
        adapter=tts_adapter,
        profile=source.profile,
        capabilities=source.capabilities,
    )
    tts_identity = seal_tts_execution_identity(
        adapter=tts_adapter,
        profile=source.profile,
        promotion=promotion,
    )
    if tts_identity.fingerprint != bindings.tts.fingerprint:
        raise ValueError("voice_deployment_tts_identity_drift")
    bundle_promotion = VoiceTtsBundlePromotionRegistry(source.db_path).verify(
        bundle=source.tts_bundle,
        runtime_adapter=tts_adapter,
        profile=source.profile,
        capabilities=source.capabilities,
    )
    bundle_identity = seal_tts_bundle_execution_identity(bundle=source.tts_bundle, promotion=bundle_promotion)
    if bindings.tts_bundle is None:
        raise ValueError("voice_deployment_tts_bundle_unconfigured")
    if bundle_identity.fingerprint != bindings.tts_bundle.fingerprint:
        raise ValueError("voice_deployment_tts_bundle_identity_drift")
    if manifest.tts_bundle_execution_identity_fingerprint != bindings.tts_bundle.fingerprint:
        raise ValueError("voice_deployment_tts_bundle_manifest_drift")


def require_voice_deployment_bindings(*, revalidate: bool = False) -> VoiceDeploymentExecutionBindings:
    if _BINDINGS is None:
        raise ValueError("voice_execution_identity_unconfigured")
    _BINDINGS.validate()
    if revalidate:
        _revalidate_verified_source(_BINDINGS)
    return _BINDINGS
