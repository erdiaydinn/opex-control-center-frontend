from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from .voice_deployment_manifest import VoiceAdapterDeploymentIdentity, VoiceRuntimeDeploymentManifest
from .voice_runtime_attestation import VoiceRuntimeArtifactSeal
from .voice_tts_bundle import VoiceTtsBundleExecutionIdentity


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


def _runtime_seal_payload(seal: VoiceRuntimeArtifactSeal) -> dict[str, object]:
    return {
        "candidate_id": seal.candidate_id,
        "adapter_id": seal.adapter_id,
        "kind": seal.kind,
        "implementation": seal.implementation,
        "runtime_license_id": seal.runtime_license_id,
        "artifact_license_id": seal.artifact_license_id,
        "runtime_artifact_sha256": seal.runtime_artifact_sha256,
        "runtime_artifact_size_bytes": seal.runtime_artifact_size_bytes,
        "model_or_voice_artifact_sha256": seal.model_or_voice_artifact_sha256,
        "adapter_fingerprint": seal.adapter_fingerprint,
        "promotion_fingerprint": seal.promotion_fingerprint,
        "deployment_manifest_fingerprint": seal.deployment_manifest_fingerprint,
    }


def _adapter_identity_payload(identity: VoiceAdapterDeploymentIdentity) -> dict[str, object]:
    return {
        "adapter_id": identity.adapter_id,
        "kind": identity.kind,
        "artifact_sha256": identity.artifact_sha256,
        "adapter_fingerprint": identity.adapter_fingerprint,
        "promotion_fingerprint": identity.promotion_fingerprint,
        "profile_fingerprint": identity.profile_fingerprint,
        "language_capability_fingerprints": tuple(sorted(identity.language_capability_fingerprints)),
    }


def _validate_runtime_seal(seal: VoiceRuntimeArtifactSeal) -> None:
    seal.validate()
    if _sha256(_runtime_seal_payload(seal)) != seal.fingerprint:
        raise ValueError("voice_runtime_attestation_seal_fingerprint_drift")


def _validate_adapter_identity(identity: VoiceAdapterDeploymentIdentity) -> None:
    if identity.kind not in {"wakeword", "vad", "stt", "tts"}:
        raise ValueError("voice_runtime_attestation_adapter_kind_invalid")
    for value, code in (
        (identity.artifact_sha256, "voice_runtime_attestation_adapter_artifact_invalid"),
        (identity.adapter_fingerprint, "voice_runtime_attestation_adapter_fingerprint_invalid"),
        (identity.promotion_fingerprint, "voice_runtime_attestation_adapter_promotion_invalid"),
        (identity.profile_fingerprint, "voice_runtime_attestation_profile_invalid"),
        (identity.fingerprint, "voice_runtime_attestation_adapter_identity_invalid"),
    ):
        if not _valid_sha256(value):
            raise ValueError(code)
    if not identity.language_capability_fingerprints or any(
        not _valid_sha256(value) for value in identity.language_capability_fingerprints
    ):
        raise ValueError("voice_runtime_attestation_language_capability_invalid")
    if _sha256(_adapter_identity_payload(identity)) != identity.fingerprint:
        raise ValueError("voice_runtime_attestation_adapter_identity_drift")


def _manifest_identity_map(manifest: VoiceRuntimeDeploymentManifest) -> dict[str, str]:
    return {
        "wakeword": manifest.wakeword_identity_fingerprint,
        "vad": manifest.vad_identity_fingerprint,
        "stt": manifest.stt_identity_fingerprint,
        "tts": manifest.tts_identity_fingerprint,
    }


@dataclass(frozen=True)
class VoiceRuntimeAttestationBundle:
    deployment_manifest_fingerprint: str
    profile_fingerprint: str
    tts_bundle_execution_identity_fingerprint: str
    wakeword_runtime_seal_fingerprint: str
    vad_runtime_seal_fingerprint: str
    stt_runtime_seal_fingerprint: str
    tts_runtime_seal_fingerprint: str
    wakeword_deployment_identity_fingerprint: str
    vad_deployment_identity_fingerprint: str
    stt_deployment_identity_fingerprint: str
    tts_deployment_identity_fingerprint: str
    runtime_seals: tuple[VoiceRuntimeArtifactSeal, ...]
    adapter_identities: tuple[VoiceAdapterDeploymentIdentity, ...]
    fingerprint: str

    def _payload(self) -> dict[str, object]:
        return {
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "profile_fingerprint": self.profile_fingerprint,
            "tts_bundle_execution_identity_fingerprint": self.tts_bundle_execution_identity_fingerprint,
            "runtime_seal_fingerprints": (
                self.wakeword_runtime_seal_fingerprint,
                self.vad_runtime_seal_fingerprint,
                self.stt_runtime_seal_fingerprint,
                self.tts_runtime_seal_fingerprint,
            ),
            "adapter_identity_fingerprints": (
                self.wakeword_deployment_identity_fingerprint,
                self.vad_deployment_identity_fingerprint,
                self.stt_deployment_identity_fingerprint,
                self.tts_deployment_identity_fingerprint,
            ),
        }

    def validate(self) -> None:
        for value, code in (
            (self.deployment_manifest_fingerprint, "voice_runtime_attestation_manifest_invalid"),
            (self.profile_fingerprint, "voice_runtime_attestation_profile_invalid"),
            (self.tts_bundle_execution_identity_fingerprint, "voice_runtime_attestation_tts_bundle_invalid"),
            (self.wakeword_runtime_seal_fingerprint, "voice_runtime_attestation_wake_seal_invalid"),
            (self.vad_runtime_seal_fingerprint, "voice_runtime_attestation_vad_seal_invalid"),
            (self.stt_runtime_seal_fingerprint, "voice_runtime_attestation_stt_seal_invalid"),
            (self.tts_runtime_seal_fingerprint, "voice_runtime_attestation_tts_seal_invalid"),
            (self.wakeword_deployment_identity_fingerprint, "voice_runtime_attestation_wake_identity_invalid"),
            (self.vad_deployment_identity_fingerprint, "voice_runtime_attestation_vad_identity_invalid"),
            (self.stt_deployment_identity_fingerprint, "voice_runtime_attestation_stt_identity_invalid"),
            (self.tts_deployment_identity_fingerprint, "voice_runtime_attestation_tts_identity_invalid"),
            (self.fingerprint, "voice_runtime_attestation_bundle_fingerprint_invalid"),
        ):
            if not _valid_sha256(value):
                raise ValueError(code)

        seals_by_kind: dict[str, VoiceRuntimeArtifactSeal] = {}
        for seal in self.runtime_seals:
            _validate_runtime_seal(seal)
            if seal.kind in seals_by_kind:
                raise ValueError("voice_runtime_attestation_duplicate_runtime_kind")
            seals_by_kind[seal.kind] = seal
        identities_by_kind: dict[str, VoiceAdapterDeploymentIdentity] = {}
        for identity in self.adapter_identities:
            _validate_adapter_identity(identity)
            if identity.kind in identities_by_kind:
                raise ValueError("voice_runtime_attestation_duplicate_adapter_kind")
            identities_by_kind[identity.kind] = identity
        required = {"wakeword", "vad", "stt", "tts"}
        if set(seals_by_kind) != required or set(identities_by_kind) != required:
            raise ValueError("voice_runtime_attestation_exact_adapter_coverage_required")

        expected_seal_fps = {
            "wakeword": self.wakeword_runtime_seal_fingerprint,
            "vad": self.vad_runtime_seal_fingerprint,
            "stt": self.stt_runtime_seal_fingerprint,
            "tts": self.tts_runtime_seal_fingerprint,
        }
        expected_identity_fps = {
            "wakeword": self.wakeword_deployment_identity_fingerprint,
            "vad": self.vad_deployment_identity_fingerprint,
            "stt": self.stt_deployment_identity_fingerprint,
            "tts": self.tts_deployment_identity_fingerprint,
        }
        for kind in ("wakeword", "vad", "stt", "tts"):
            seal = seals_by_kind[kind]
            identity = identities_by_kind[kind]
            if seal.fingerprint != expected_seal_fps[kind] or identity.fingerprint != expected_identity_fps[kind]:
                raise ValueError("voice_runtime_attestation_nested_fingerprint_mismatch")
            if seal.deployment_manifest_fingerprint != self.deployment_manifest_fingerprint:
                raise ValueError("voice_runtime_attestation_runtime_manifest_mismatch")
            if identity.profile_fingerprint != self.profile_fingerprint:
                raise ValueError("voice_runtime_attestation_profile_drift")
            if seal.adapter_id != identity.adapter_id:
                raise ValueError("voice_runtime_attestation_adapter_id_mismatch")
            if seal.adapter_fingerprint != identity.adapter_fingerprint:
                raise ValueError("voice_runtime_attestation_adapter_contract_mismatch")
            if seal.promotion_fingerprint != identity.promotion_fingerprint:
                raise ValueError("voice_runtime_attestation_adapter_promotion_mismatch")
            if seal.model_or_voice_artifact_sha256 != identity.artifact_sha256:
                raise ValueError("voice_runtime_attestation_model_artifact_mismatch")
        if _sha256(self._payload()) != self.fingerprint:
            raise ValueError("voice_runtime_attestation_bundle_fingerprint_drift")

    def assert_matches_deployment(
        self,
        *,
        manifest: VoiceRuntimeDeploymentManifest,
        tts_bundle_identity: VoiceTtsBundleExecutionIdentity,
    ) -> None:
        self.validate()
        tts_bundle_identity.validate()
        if self.deployment_manifest_fingerprint != manifest.fingerprint:
            raise ValueError("voice_runtime_attestation_deployment_manifest_drift")
        if self.profile_fingerprint != manifest.profile_fingerprint:
            raise ValueError("voice_runtime_attestation_deployment_profile_drift")
        if self.tts_bundle_execution_identity_fingerprint != manifest.tts_bundle_execution_identity_fingerprint:
            raise ValueError("voice_runtime_attestation_deployment_tts_bundle_drift")
        if self.tts_bundle_execution_identity_fingerprint != tts_bundle_identity.fingerprint:
            raise ValueError("voice_runtime_attestation_tts_bundle_identity_drift")
        actual = {
            "wakeword": self.wakeword_deployment_identity_fingerprint,
            "vad": self.vad_deployment_identity_fingerprint,
            "stt": self.stt_deployment_identity_fingerprint,
            "tts": self.tts_deployment_identity_fingerprint,
        }
        if actual != _manifest_identity_map(manifest):
            raise ValueError("voice_runtime_attestation_deployment_adapter_identity_drift")


def seal_voice_runtime_attestation_bundle(
    *,
    manifest: VoiceRuntimeDeploymentManifest,
    runtime_seals: Iterable[VoiceRuntimeArtifactSeal],
    adapter_identities: Iterable[VoiceAdapterDeploymentIdentity],
    tts_bundle_identity: VoiceTtsBundleExecutionIdentity,
) -> VoiceRuntimeAttestationBundle:
    runtime_seals = tuple(runtime_seals)
    adapter_identities = tuple(adapter_identities)
    tts_bundle_identity.validate()
    seals_by_kind = {item.kind: item for item in runtime_seals}
    identities_by_kind = {item.kind: item for item in adapter_identities}
    if len(seals_by_kind) != len(runtime_seals):
        raise ValueError("voice_runtime_attestation_duplicate_runtime_kind")
    if len(identities_by_kind) != len(adapter_identities):
        raise ValueError("voice_runtime_attestation_duplicate_adapter_kind")
    required = {"wakeword", "vad", "stt", "tts"}
    if set(seals_by_kind) != required or set(identities_by_kind) != required:
        raise ValueError("voice_runtime_attestation_exact_adapter_coverage_required")
    expected_manifest_identities = _manifest_identity_map(manifest)
    if {kind: identities_by_kind[kind].fingerprint for kind in required} != expected_manifest_identities:
        raise ValueError("voice_runtime_attestation_deployment_adapter_identity_drift")
    if tts_bundle_identity.fingerprint != manifest.tts_bundle_execution_identity_fingerprint:
        raise ValueError("voice_runtime_attestation_deployment_tts_bundle_drift")

    payload = {
        "deployment_manifest_fingerprint": manifest.fingerprint,
        "profile_fingerprint": manifest.profile_fingerprint,
        "tts_bundle_execution_identity_fingerprint": tts_bundle_identity.fingerprint,
        "runtime_seal_fingerprints": tuple(seals_by_kind[kind].fingerprint for kind in ("wakeword", "vad", "stt", "tts")),
        "adapter_identity_fingerprints": tuple(identities_by_kind[kind].fingerprint for kind in ("wakeword", "vad", "stt", "tts")),
    }
    bundle = VoiceRuntimeAttestationBundle(
        deployment_manifest_fingerprint=manifest.fingerprint,
        profile_fingerprint=manifest.profile_fingerprint,
        tts_bundle_execution_identity_fingerprint=tts_bundle_identity.fingerprint,
        wakeword_runtime_seal_fingerprint=seals_by_kind["wakeword"].fingerprint,
        vad_runtime_seal_fingerprint=seals_by_kind["vad"].fingerprint,
        stt_runtime_seal_fingerprint=seals_by_kind["stt"].fingerprint,
        tts_runtime_seal_fingerprint=seals_by_kind["tts"].fingerprint,
        wakeword_deployment_identity_fingerprint=identities_by_kind["wakeword"].fingerprint,
        vad_deployment_identity_fingerprint=identities_by_kind["vad"].fingerprint,
        stt_deployment_identity_fingerprint=identities_by_kind["stt"].fingerprint,
        tts_deployment_identity_fingerprint=identities_by_kind["tts"].fingerprint,
        runtime_seals=runtime_seals,
        adapter_identities=adapter_identities,
        fingerprint=_sha256(payload),
    )
    bundle.validate()
    bundle.assert_matches_deployment(manifest=manifest, tts_bundle_identity=tts_bundle_identity)
    return bundle
