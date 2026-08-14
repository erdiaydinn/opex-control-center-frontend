from __future__ import annotations

from dataclasses import dataclass, replace
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
from .voice_release_evidence import GovernedVoiceReleaseDecision, VoiceReleaseEvidenceRegistry
from .voice_runtime import VoiceProfile
from .voice_runtime_attestation_bundle import VoiceRuntimeAttestationBundle
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
    governed_release_decision_fingerprint: str | None = None
    runtime_attestation_bundle_fingerprint: str | None = None

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
        release_fields = (
            self.governed_release_decision_fingerprint,
            self.runtime_attestation_bundle_fingerprint,
        )
        if any(value is not None for value in release_fields):
            if self.tts_bundle is None:
                raise ValueError("voice_deployment_released_tts_bundle_required")
            if not all(_valid_sha256(value) for value in release_fields):
                raise ValueError("voice_deployment_release_lineage_incomplete")

    @property
    def production_released(self) -> bool:
        return (
            _valid_sha256(self.governed_release_decision_fingerprint)
            and _valid_sha256(self.runtime_attestation_bundle_fingerprint)
        )

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
    governed_release_decision_fingerprint: str | None = None
    runtime_attestation_bundle: VoiceRuntimeAttestationBundle | None = None


@dataclass(frozen=True)
class _VerifiedDeploymentBuild:
    manifest: VoiceRuntimeDeploymentManifest
    bindings: VoiceDeploymentExecutionBindings
    source: _VerifiedDeploymentSource


_BINDINGS: VoiceDeploymentExecutionBindings | None = None
_VERIFIED_SOURCE: _VerifiedDeploymentSource | None = None


def configure_voice_deployment_bindings(bindings: VoiceDeploymentExecutionBindings) -> None:
    """Install an already-verified binding for tests/embedding only.

    This low-level function deliberately does not manufacture release evidence. A
    binding installed here is not marked ``production_released``. Production startup
    should use ``configure_released_voice_deployment``.
    """
    global _BINDINGS, _VERIFIED_SOURCE
    bindings.validate()
    _BINDINGS = bindings
    _VERIFIED_SOURCE = None


def _build_verified_deployment(
    *,
    db_path: Path,
    model_record_id: str,
    profile: VoiceProfile,
    capabilities: Iterable[LanguageCapability],
    tts_bundle: VoiceTtsArtifactBundle,
) -> _VerifiedDeploymentBuild:
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
    source = _VerifiedDeploymentSource(
        db_path=Path(db_path),
        model_record_id=model_record_id,
        profile=profile,
        capabilities=caps,
        tts_bundle=tts_bundle,
    )
    return _VerifiedDeploymentBuild(manifest=manifest, bindings=bindings, source=source)


def _install_verified_build(build: _VerifiedDeploymentBuild) -> None:
    global _BINDINGS, _VERIFIED_SOURCE
    build.bindings.validate()
    _BINDINGS = build.bindings
    _VERIFIED_SOURCE = build.source


def configure_verified_voice_deployment(
    *,
    db_path: Path,
    model_record_id: str,
    profile: VoiceProfile,
    capabilities: Iterable[LanguageCapability],
    tts_bundle: VoiceTtsArtifactBundle,
) -> VoiceRuntimeDeploymentManifest:
    """Install a registry-verified staging/evaluation deployment.

    This verifies production model/adapter/TTS promotions, but intentionally does not
    mark the runtime as voice-release approved. Production session bootstrap must use
    ``configure_released_voice_deployment`` after immutable multilingual measurements.
    """
    build = _build_verified_deployment(
        db_path=db_path,
        model_record_id=model_record_id,
        profile=profile,
        capabilities=capabilities,
        tts_bundle=tts_bundle,
    )
    _install_verified_build(build)
    return build.manifest


def configure_released_voice_deployment(
    *,
    db_path: Path,
    model_record_id: str,
    profile: VoiceProfile,
    capabilities: Iterable[LanguageCapability],
    tts_bundle: VoiceTtsArtifactBundle,
    runtime_attestation_bundle: VoiceRuntimeAttestationBundle,
    governed_release_decision_fingerprint: str,
) -> tuple[VoiceRuntimeDeploymentManifest, GovernedVoiceReleaseDecision]:
    """Install production bindings only after exact approved voice release evidence.

    No global binding is changed until current registry state, runtime attestation and
    the immutable five-language release decision all match the same deployment.
    """
    build = _build_verified_deployment(
        db_path=db_path,
        model_record_id=model_record_id,
        profile=profile,
        capabilities=capabilities,
        tts_bundle=tts_bundle,
    )
    if build.bindings.tts_bundle is None:
        raise ValueError("voice_deployment_tts_bundle_unconfigured")
    runtime_attestation_bundle.assert_matches_deployment(
        manifest=build.manifest,
        tts_bundle_identity=build.bindings.tts_bundle,
    )
    decision = VoiceReleaseEvidenceRegistry(db_path).require_release(
        governed_release_decision_fingerprint,
        deployment_manifest_fingerprint=build.manifest.fingerprint,
        model_execution_identity_fingerprint=build.bindings.model.fingerprint,
        tts_bundle_execution_identity_fingerprint=build.bindings.tts_bundle.fingerprint,
        runtime_attestation_bundle_fingerprint=runtime_attestation_bundle.fingerprint,
    )
    released_bindings = replace(
        build.bindings,
        governed_release_decision_fingerprint=decision.fingerprint,
        runtime_attestation_bundle_fingerprint=runtime_attestation_bundle.fingerprint,
    )
    released_source = replace(
        build.source,
        governed_release_decision_fingerprint=decision.fingerprint,
        runtime_attestation_bundle=runtime_attestation_bundle,
    )
    released = _VerifiedDeploymentBuild(
        manifest=build.manifest,
        bindings=released_bindings,
        source=released_source,
    )
    _install_verified_build(released)
    return build.manifest, decision


def clear_voice_deployment_bindings() -> None:
    global _BINDINGS, _VERIFIED_SOURCE
    _BINDINGS = None
    _VERIFIED_SOURCE = None


def _assert_build_matches_pinned(current: _VerifiedDeploymentBuild, bindings: VoiceDeploymentExecutionBindings) -> None:
    manifest = current.manifest
    if manifest.fingerprint != bindings.deployment_manifest_fingerprint:
        raise ValueError("voice_deployment_manifest_drift")
    if current.bindings.model.fingerprint != bindings.model.fingerprint:
        raise ValueError("voice_deployment_model_identity_drift")
    if manifest.wakeword_identity_fingerprint != bindings.wakeword_identity_fingerprint:
        raise ValueError("voice_deployment_wakeword_identity_drift")
    if manifest.vad_identity_fingerprint != bindings.vad_identity_fingerprint:
        raise ValueError("voice_deployment_vad_identity_drift")
    if manifest.stt_identity_fingerprint != bindings.stt_identity_fingerprint:
        raise ValueError("voice_deployment_stt_identity_drift")
    if current.bindings.tts.fingerprint != bindings.tts.fingerprint:
        raise ValueError("voice_deployment_tts_identity_drift")
    if bindings.tts_bundle is None or current.bindings.tts_bundle is None:
        raise ValueError("voice_deployment_tts_bundle_unconfigured")
    if current.bindings.tts_bundle.fingerprint != bindings.tts_bundle.fingerprint:
        raise ValueError("voice_deployment_tts_bundle_identity_drift")
    if manifest.tts_bundle_execution_identity_fingerprint != bindings.tts_bundle.fingerprint:
        raise ValueError("voice_deployment_tts_bundle_manifest_drift")


def _revalidate_verified_source(bindings: VoiceDeploymentExecutionBindings) -> None:
    source = _VERIFIED_SOURCE
    if source is None:
        return
    current = _build_verified_deployment(
        db_path=source.db_path,
        model_record_id=source.model_record_id,
        profile=source.profile,
        capabilities=source.capabilities,
        tts_bundle=source.tts_bundle,
    )
    _assert_build_matches_pinned(current, bindings)

    release_fp = source.governed_release_decision_fingerprint
    runtime_bundle = source.runtime_attestation_bundle
    if release_fp is None and runtime_bundle is None:
        if bindings.production_released:
            raise ValueError("voice_deployment_release_source_missing")
        return
    if release_fp is None or runtime_bundle is None:
        raise ValueError("voice_deployment_release_source_incomplete")
    if current.bindings.tts_bundle is None:
        raise ValueError("voice_deployment_tts_bundle_unconfigured")
    runtime_bundle.assert_matches_deployment(
        manifest=current.manifest,
        tts_bundle_identity=current.bindings.tts_bundle,
    )
    decision = VoiceReleaseEvidenceRegistry(source.db_path).require_release(
        release_fp,
        deployment_manifest_fingerprint=current.manifest.fingerprint,
        model_execution_identity_fingerprint=current.bindings.model.fingerprint,
        tts_bundle_execution_identity_fingerprint=current.bindings.tts_bundle.fingerprint,
        runtime_attestation_bundle_fingerprint=runtime_bundle.fingerprint,
    )
    if bindings.governed_release_decision_fingerprint != decision.fingerprint:
        raise ValueError("voice_deployment_release_decision_drift")
    if bindings.runtime_attestation_bundle_fingerprint != runtime_bundle.fingerprint:
        raise ValueError("voice_deployment_runtime_attestation_drift")


def require_voice_deployment_bindings(
    *,
    revalidate: bool = False,
    require_production_release: bool = False,
) -> VoiceDeploymentExecutionBindings:
    if _BINDINGS is None:
        raise ValueError("voice_execution_identity_unconfigured")
    _BINDINGS.validate()
    if require_production_release and not _BINDINGS.production_released:
        raise ValueError("voice_deployment_production_release_required")
    if revalidate:
        _revalidate_verified_source(_BINDINGS)
    return _BINDINGS
