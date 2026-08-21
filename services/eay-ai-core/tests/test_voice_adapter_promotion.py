from dataclasses import replace

import pytest

from app.language_capability import evaluate_language_capability
from app.voice_adapter_promotion import VoiceAdapterPromotionRegistry
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile


def _caps():
    return [
        evaluate_language_capability(
            language=language,
            eval_pack_version="voice-v1",
            eval_score=0.95,
            safety_score=0.995,
            domain_score=0.92,
            human_approved=True,
        )
        for language in CORE_LANGUAGES
    ]


def _adapter(*, artifact="a" * 64, license_id="apache-2.0"):
    return VoiceAdapterSpec(
        adapter_id="stt-local-prod-v1",
        kind="stt",
        implementation="local-stt-runtime",
        local=True,
        streaming=True,
        license_id=license_id,
        languages=CORE_LANGUAGES,
        artifact_sha256=artifact,
    )


def _profile(adapter):
    peers = (
        VoiceAdapterSpec("wake-prod-v1", "wakeword", "wake", True, True, "apache-2.0", CORE_LANGUAGES, "b" * 64),
        VoiceAdapterSpec("vad-prod-v1", "vad", "vad", True, True, "apache-2.0", CORE_LANGUAGES, "c" * 64),
        adapter,
        VoiceAdapterSpec("tts-prod-v1", "tts", "tts", True, True, "apache-2.0", CORE_LANGUAGES, "d" * 64),
    )
    return VoiceProfile(
        profile_id="eay-jarvis-prod-v1",
        wake_phrases=("EAY", "Hey EAY", "Jarvis"),
        languages=CORE_LANGUAGES,
        sample_rate_hz=16000,
        full_duplex=True,
        barge_in=True,
        local_first=True,
        voice_identity_id="eay-natural-neutral-v1",
        clone_reference_voice=False,
        adapters=peers,
    )


def test_voice_adapter_promotion_requires_exact_artifact_and_human_lineage(tmp_path):
    adapter = _adapter()
    profile = _profile(adapter)
    registry = VoiceAdapterPromotionRegistry(tmp_path / "voice.db")

    promotion = registry.promote(
        adapter=adapter,
        profile=profile,
        capabilities=_caps(),
        reviewer="voice-reviewer",
        approval_reference="VOICE-APPROVAL-001",
    )

    assert len(promotion.fingerprint) == 64
    assert promotion.adapter_artifact_sha256 == "a" * 64
    assert len(promotion.language_capability_fingerprints) == len(CORE_LANGUAGES)
    assert registry.verify(adapter=adapter, profile=profile, capabilities=_caps()).fingerprint == promotion.fingerprint


def test_voice_adapter_promotion_rejects_placeholder_or_unapproved_license(tmp_path):
    registry = VoiceAdapterPromotionRegistry(tmp_path / "voice.db")
    adapter = _adapter(license_id="deployment-review-required")
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        registry.promote(
            adapter=adapter,
            profile=_profile(adapter),
            capabilities=_caps(),
            reviewer="voice-reviewer",
            approval_reference="VOICE-APPROVAL-002",
        )


def test_voice_adapter_artifact_drift_invalidates_existing_promotion(tmp_path):
    registry = VoiceAdapterPromotionRegistry(tmp_path / "voice.db")
    adapter = _adapter()
    profile = _profile(adapter)
    registry.promote(
        adapter=adapter,
        profile=profile,
        capabilities=_caps(),
        reviewer="voice-reviewer",
        approval_reference="VOICE-APPROVAL-003",
    )

    changed = replace(adapter, artifact_sha256="e" * 64)
    changed_profile = _profile(changed)
    with pytest.raises(ValueError, match="voice_adapter_artifact_or_contract_drift"):
        registry.verify(adapter=changed, profile=changed_profile, capabilities=_caps())


def test_language_eval_drift_invalidates_voice_adapter_promotion(tmp_path):
    registry = VoiceAdapterPromotionRegistry(tmp_path / "voice.db")
    adapter = _adapter()
    profile = _profile(adapter)
    registry.promote(
        adapter=adapter,
        profile=profile,
        capabilities=_caps(),
        reviewer="voice-reviewer",
        approval_reference="VOICE-APPROVAL-004",
    )

    changed = _caps()
    changed[0] = evaluate_language_capability(
        language=CORE_LANGUAGES[0],
        eval_pack_version="voice-v2",
        eval_score=0.96,
        safety_score=0.996,
        domain_score=0.93,
        human_approved=True,
    )
    with pytest.raises(ValueError, match="voice_adapter_language_capability_drift"):
        registry.verify(adapter=adapter, profile=profile, capabilities=changed)


def test_reference_voice_clone_can_never_be_promoted(tmp_path):
    adapter = _adapter()
    unsafe_profile = replace(_profile(adapter), clone_reference_voice=True)
    registry = VoiceAdapterPromotionRegistry(tmp_path / "voice.db")
    with pytest.raises(ValueError, match="voice_reference_clone_forbidden"):
        registry.promote(
            adapter=adapter,
            profile=unsafe_profile,
            capabilities=_caps(),
            reviewer="voice-reviewer",
            approval_reference="VOICE-APPROVAL-005",
        )
