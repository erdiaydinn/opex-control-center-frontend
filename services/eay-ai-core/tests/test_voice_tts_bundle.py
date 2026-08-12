from dataclasses import replace

import pytest

from app.language_capability import evaluate_language_capability
from app.voice_adapter_promotion import VoiceAdapterPromotionRegistry
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile
from app.voice_tts_bundle import VoiceTtsArtifactBundle, VoiceTtsBundlePromotionRegistry, VoiceTtsLanguageArtifact


def _hash(ch: str) -> str:
    return ch * 64


def _caps():
    return [
        evaluate_language_capability(
            language=language,
            eval_pack_version="voice-tts-v1",
            eval_score=0.96,
            safety_score=0.996,
            domain_score=0.93,
            human_approved=True,
        )
        for language in CORE_LANGUAGES
    ]


def _tts_adapter():
    return VoiceAdapterSpec(
        adapter_id="tts-sherpa-prod-v1",
        kind="tts",
        implementation="sherpa-onnx-vits",
        local=True,
        streaming=True,
        license_id="apache-2.0",
        languages=CORE_LANGUAGES,
        artifact_sha256=_hash("1"),
        runtime_license_id="apache-2.0",
        artifact_license_id="apache-2.0",
    )


def _profile(tts):
    peers = (
        VoiceAdapterSpec("wake-prod", "wakeword", "custom-wake", True, True, "apache-2.0", CORE_LANGUAGES, _hash("2")),
        VoiceAdapterSpec("vad-prod", "vad", "silero-vad-onnx", True, True, "mit", CORE_LANGUAGES, _hash("3")),
        VoiceAdapterSpec("stt-prod", "stt", "whisper.cpp", True, True, "mit", CORE_LANGUAGES, _hash("4")),
        tts,
    )
    return VoiceProfile(
        profile_id="eay-jarvis-tts-v1",
        wake_phrases=("EAY",),
        languages=CORE_LANGUAGES,
        sample_rate_hz=16000,
        full_duplex=True,
        barge_in=True,
        local_first=True,
        voice_identity_id="eay-natural-neutral-v1",
        clone_reference_voice=False,
        adapters=peers,
    )


def _bundle(*, license_id="mit", phonemizer_license_id="mit", phonemizer_manifest=None):
    locales = {"tr": "tr_TR", "en": "en_US", "de": "de_DE", "ar": "ar_JO", "fa": "fa_IR"}
    artifacts = []
    for index, language in enumerate(CORE_LANGUAGES, start=5):
        ch = format(index, "x")[-1]
        artifacts.append(
            VoiceTtsLanguageArtifact(
                language=locales[language],
                voice_id=f"eay-{language}-neutral-v1",
                model_sha256=_hash(ch),
                config_sha256=_hash(format(index + 5, "x")[-1]),
                tokens_sha256=_hash(format(index + 1, "x")[-1]),
                model_card_sha256=_hash(format(index + 10, "x")[-1]),
                artifact_license_id=license_id,
                model_card_source=f"https://models.example.invalid/{language}/MODEL_CARD",
            )
        )
    return VoiceTtsArtifactBundle(
        bundle_id="eay-natural-neutral-core5",
        bundle_version="1",
        runtime_adapter_id="tts-sherpa-prod-v1",
        voice_identity_id="eay-natural-neutral-v1",
        phonemizer_data_manifest_fingerprint=phonemizer_manifest or _hash("e"),
        phonemizer_license_id=phonemizer_license_id,
        phonemizer_source="https://github.com/espeak-ng/espeak-ng",
        artifacts=tuple(artifacts),
    )


def test_tts_bundle_requires_exact_core_language_artifacts_and_selects_by_locale():
    bundle = _bundle()
    bundle.validate()
    assert len(bundle.fingerprint) == 64
    assert bundle.artifact_for("tr-TR").voice_id == "eay-tr-neutral-v1"
    assert bundle.artifact_for("fa_IR").voice_id == "eay-fa-neutral-v1"
    assert len(bundle.artifact_for("en").tokens_sha256) == 64

    broken = replace(bundle, artifacts=bundle.artifacts[:-1])
    with pytest.raises(ValueError, match="voice_tts_bundle_core_language_coverage_required"):
        broken.validate()


def test_tts_bundle_rejects_nonallowlisted_voice_artifact_license():
    bundle = _bundle(license_id="cc-by-nc-sa-4.0")
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        bundle.validate()


def test_tts_bundle_rejects_nonallowlisted_phonemizer_license_by_default():
    bundle = _bundle(phonemizer_license_id="gpl-3.0-or-later")
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        bundle.validate()


def test_tts_bundle_promotion_binds_runtime_promotion_profile_and_language_evals(tmp_path):
    db = tmp_path / "voice.db"
    tts = _tts_adapter()
    profile = _profile(tts)
    caps = _caps()
    VoiceAdapterPromotionRegistry(db).promote(
        adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="voice-reviewer",
        approval_reference="TTS-RUNTIME-001",
    )
    bundle = _bundle()
    registry = VoiceTtsBundlePromotionRegistry(db)
    promotion = registry.promote(
        bundle=bundle,
        runtime_adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="tts-bundle-reviewer",
        approval_reference="TTS-BUNDLE-001",
    )

    assert promotion.bundle_fingerprint == bundle.fingerprint
    assert len(promotion.language_capability_fingerprints) == len(CORE_LANGUAGES)
    assert registry.verify(bundle=bundle, runtime_adapter=tts, profile=profile, capabilities=caps).fingerprint == promotion.fingerprint


def test_tts_bundle_artifact_drift_cannot_reuse_existing_promotion(tmp_path):
    db = tmp_path / "voice.db"
    tts = _tts_adapter()
    profile = _profile(tts)
    caps = _caps()
    VoiceAdapterPromotionRegistry(db).promote(
        adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="voice-reviewer",
        approval_reference="TTS-RUNTIME-002",
    )
    bundle = _bundle()
    registry = VoiceTtsBundlePromotionRegistry(db)
    registry.promote(
        bundle=bundle,
        runtime_adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="tts-bundle-reviewer",
        approval_reference="TTS-BUNDLE-002",
    )

    changed_first = replace(bundle.artifacts[0], model_sha256=_hash("f"))
    changed_bundle = replace(bundle, artifacts=(changed_first,) + bundle.artifacts[1:])
    with pytest.raises(KeyError, match="voice_tts_bundle_promotion_not_found"):
        registry.verify(bundle=changed_bundle, runtime_adapter=tts, profile=profile, capabilities=caps)


def test_tts_tokens_or_phonemizer_resource_drift_cannot_reuse_promotion(tmp_path):
    db = tmp_path / "voice.db"
    tts = _tts_adapter()
    profile = _profile(tts)
    caps = _caps()
    VoiceAdapterPromotionRegistry(db).promote(
        adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="voice-reviewer",
        approval_reference="TTS-RUNTIME-003",
    )
    bundle = _bundle()
    registry = VoiceTtsBundlePromotionRegistry(db)
    registry.promote(
        bundle=bundle,
        runtime_adapter=tts,
        profile=profile,
        capabilities=caps,
        reviewer="tts-bundle-reviewer",
        approval_reference="TTS-BUNDLE-003",
    )

    token_drift = replace(bundle.artifacts[0], tokens_sha256=_hash("f"))
    changed_tokens = replace(bundle, artifacts=(token_drift,) + bundle.artifacts[1:])
    with pytest.raises(KeyError, match="voice_tts_bundle_promotion_not_found"):
        registry.verify(bundle=changed_tokens, runtime_adapter=tts, profile=profile, capabilities=caps)

    changed_resources = replace(bundle, phonemizer_data_manifest_fingerprint=_hash("d"))
    with pytest.raises(KeyError, match="voice_tts_bundle_promotion_not_found"):
        registry.verify(bundle=changed_resources, runtime_adapter=tts, profile=profile, capabilities=caps)
