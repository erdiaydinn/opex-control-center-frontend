import hashlib
import json
from dataclasses import replace

import pytest

from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_deployment_manifest import VoiceRuntimeDeploymentManifest, _seal_adapter_identity
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile
from app.voice_runtime_attestation import VoiceRuntimeArtifactSeal
from app.voice_runtime_attestation_bundle import seal_voice_runtime_attestation_bundle
from app.voice_tts_bundle import VoiceTtsBundleExecutionIdentity, VoiceTtsLanguageExecutionIdentity


def _hash(ch: str) -> str:
    return ch * 64


def _sha(payload):
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def _profile():
    adapters = (
        VoiceAdapterSpec("wake-v1", "wakeword", "custom-wake", True, True, "apache-2.0", CORE_LANGUAGES, _hash("1")),
        VoiceAdapterSpec("vad-v1", "vad", "silero-vad-onnx", True, True, "mit", CORE_LANGUAGES, _hash("2")),
        VoiceAdapterSpec("stt-v1", "stt", "whisper.cpp", True, True, "mit", CORE_LANGUAGES, _hash("3")),
        VoiceAdapterSpec("tts-v1", "tts", "sherpa-onnx-vits", True, True, "apache-2.0", CORE_LANGUAGES, _hash("4")),
    )
    return VoiceProfile("jarvis-prod-v1", ("EAY",), CORE_LANGUAGES, 16000, True, True, True, "eay-natural-v1", False, adapters)


def _promotion(profile, adapter, ch):
    return VoiceAdapterPromotion(
        adapter_id=adapter.adapter_id,
        kind=adapter.kind,
        adapter_artifact_sha256=adapter.artifact_sha256,
        adapter_fingerprint=adapter_fingerprint(adapter),
        profile_fingerprint=profile.fingerprint,
        language_capability_fingerprints=tuple(_hash(x) for x in "56789"),
        reviewer="reviewer",
        approval_reference=f"VOICE-{adapter.kind}",
        promoted_at="2026-08-12T10:00:00+00:00",
        fingerprint=_hash(ch),
    )


def _tts_bundle(profile_fp):
    artifacts = tuple(
        VoiceTtsLanguageExecutionIdentity(
            language=language,
            voice_id_sha256=_hash("5"),
            model_sha256=_hash(ch),
            config_sha256=_hash("6"),
            tokens_sha256=_hash("7"),
            model_card_sha256=_hash("8"),
            artifact_license_id_sha256=_hash("9"),
            artifact_fingerprint=_hash("a"),
            fingerprint=_hash(ch),
        )
        for language, ch in zip(CORE_LANGUAGES, ("b", "c", "d", "e", "f"))
    )
    identity = VoiceTtsBundleExecutionIdentity(
        bundle_fingerprint=_hash("a"),
        bundle_promotion_fingerprint=_hash("b"),
        runtime_adapter_id="tts-v1",
        runtime_adapter_promotion_fingerprint=_hash("d"),
        profile_fingerprint=profile_fp,
        phonemizer_data_manifest_fingerprint=_hash("c"),
        phonemizer_license_id_sha256=_hash("d"),
        phonemizer_source_sha256=_hash("e"),
        language_artifacts=artifacts,
        fingerprint=_hash("f"),
    )
    identity.validate()
    return identity


def _fixture():
    profile = _profile()
    promotion_chars = {"wakeword": "a", "vad": "b", "stt": "c", "tts": "d"}
    identities = []
    seals = []
    manifest_fp = _hash("0")
    for adapter in profile.adapters:
        promotion = _promotion(profile, adapter, promotion_chars[adapter.kind])
        identity = _seal_adapter_identity(adapter=adapter, profile=profile, promotion=promotion)
        identities.append(identity)
        payload = {
            "candidate_id": f"candidate-{adapter.kind}",
            "adapter_id": adapter.adapter_id,
            "kind": adapter.kind,
            "implementation": adapter.implementation,
            "runtime_license_id": adapter.resolved_runtime_license_id,
            "artifact_license_id": adapter.resolved_artifact_license_id,
            "runtime_artifact_sha256": _hash("e"),
            "runtime_artifact_size_bytes": 100,
            "model_or_voice_artifact_sha256": adapter.artifact_sha256,
            "adapter_fingerprint": identity.adapter_fingerprint,
            "promotion_fingerprint": identity.promotion_fingerprint,
            "deployment_manifest_fingerprint": manifest_fp,
        }
        seals.append(VoiceRuntimeArtifactSeal(**payload, fingerprint=_sha(payload)))

    by_kind = {item.kind: item for item in identities}
    tts_bundle = _tts_bundle(profile.fingerprint)
    manifest = VoiceRuntimeDeploymentManifest(
        model_record_id="model-prod",
        model_production_promotion_fingerprint=_hash("1"),
        model_release_proof_fingerprint=_hash("2"),
        model_execution_identity_fingerprint=_hash("3"),
        model_artifact_sha256=_hash("4"),
        profile_fingerprint=profile.fingerprint,
        adapter_identity_fingerprints=tuple(by_kind[k].fingerprint for k in ("wakeword", "vad", "stt", "tts")),
        wakeword_identity_fingerprint=by_kind["wakeword"].fingerprint,
        vad_identity_fingerprint=by_kind["vad"].fingerprint,
        stt_identity_fingerprint=by_kind["stt"].fingerprint,
        tts_identity_fingerprint=by_kind["tts"].fingerprint,
        tts_bundle_execution_identity_fingerprint=tts_bundle.fingerprint,
        tts_bundle_fingerprint=tts_bundle.bundle_fingerprint,
        tts_bundle_promotion_fingerprint=tts_bundle.bundle_promotion_fingerprint,
        tts_language_artifact_fingerprints=tuple(item.fingerprint for item in tts_bundle.language_artifacts),
        fingerprint=manifest_fp,
    )
    return manifest, tuple(seals), tuple(identities), tts_bundle


def test_runtime_attestation_bundle_binds_exact_four_runtime_seals_to_deployment():
    manifest, seals, identities, tts_bundle = _fixture()
    bundle = seal_voice_runtime_attestation_bundle(
        manifest=manifest,
        runtime_seals=seals,
        adapter_identities=identities,
        tts_bundle_identity=tts_bundle,
    )
    assert bundle.deployment_manifest_fingerprint == manifest.fingerprint
    assert bundle.tts_bundle_execution_identity_fingerprint == tts_bundle.fingerprint
    assert len(bundle.fingerprint) == 64
    bundle.assert_matches_deployment(manifest=manifest, tts_bundle_identity=tts_bundle)


def test_runtime_attestation_bundle_rejects_runtime_seal_fingerprint_tamper():
    manifest, seals, identities, tts_bundle = _fixture()
    tampered = (replace(seals[0], runtime_artifact_size_bytes=101),) + seals[1:]
    with pytest.raises(ValueError, match="voice_runtime_attestation_seal_fingerprint_drift"):
        seal_voice_runtime_attestation_bundle(
            manifest=manifest,
            runtime_seals=tampered,
            adapter_identities=identities,
            tts_bundle_identity=tts_bundle,
        )


def test_runtime_attestation_bundle_rejects_adapter_identity_not_in_manifest():
    manifest, seals, identities, tts_bundle = _fixture()
    changed = replace(identities[1], fingerprint=_hash("9"))
    with pytest.raises(ValueError, match="voice_runtime_attestation_deployment_adapter_identity_drift"):
        seal_voice_runtime_attestation_bundle(
            manifest=manifest,
            runtime_seals=seals,
            adapter_identities=(identities[0], changed) + identities[2:],
            tts_bundle_identity=tts_bundle,
        )


def test_runtime_attestation_bundle_rejects_missing_runtime_kind():
    manifest, seals, identities, tts_bundle = _fixture()
    with pytest.raises(ValueError, match="voice_runtime_attestation_exact_adapter_coverage_required"):
        seal_voice_runtime_attestation_bundle(
            manifest=manifest,
            runtime_seals=seals[:-1],
            adapter_identities=identities,
            tts_bundle_identity=tts_bundle,
        )


def test_runtime_attestation_bundle_rejects_tts_bundle_drift():
    manifest, seals, identities, tts_bundle = _fixture()
    changed = replace(tts_bundle, fingerprint=_hash("1"))
    with pytest.raises(ValueError, match="voice_runtime_attestation_deployment_tts_bundle_drift"):
        seal_voice_runtime_attestation_bundle(
            manifest=manifest,
            runtime_seals=seals,
            adapter_identities=identities,
            tts_bundle_identity=changed,
        )
