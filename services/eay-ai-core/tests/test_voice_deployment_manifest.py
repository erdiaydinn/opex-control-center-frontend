from dataclasses import replace

import pytest

from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_deployment_manifest import _seal_adapter_identity
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile


def _hash(ch: str) -> str:
    return ch * 64


def _profile():
    adapters = (
        VoiceAdapterSpec("wake-v1", "wakeword", "wake", True, True, "apache-2.0", CORE_LANGUAGES, _hash("1")),
        VoiceAdapterSpec("vad-v1", "vad", "vad", True, True, "apache-2.0", CORE_LANGUAGES, _hash("2")),
        VoiceAdapterSpec("stt-v1", "stt", "stt", True, True, "apache-2.0", CORE_LANGUAGES, _hash("3")),
        VoiceAdapterSpec("tts-v1", "tts", "tts", True, True, "apache-2.0", CORE_LANGUAGES, _hash("4")),
    )
    profile = VoiceProfile("jarvis-prod-v1", ("EAY",), CORE_LANGUAGES, 16000, True, True, True, "eay-natural-v1", False, adapters)
    profile.validate()
    return profile


def _promotion(profile, adapter):
    return VoiceAdapterPromotion(
        adapter_id=adapter.adapter_id,
        kind=adapter.kind,
        adapter_artifact_sha256=str(adapter.artifact_sha256),
        adapter_fingerprint=adapter_fingerprint(adapter),
        profile_fingerprint=profile.fingerprint,
        language_capability_fingerprints=tuple(_hash(ch) for ch in "56789"),
        reviewer="reviewer",
        approval_reference="VOICE-APPROVAL",
        promoted_at="2026-08-11T00:00:00+00:00",
        fingerprint=_hash("a"),
    )


def test_adapter_deployment_identity_binds_artifact_promotion_and_profile():
    profile = _profile()
    adapter = profile.adapters[2]
    identity = _seal_adapter_identity(adapter=adapter, profile=profile, promotion=_promotion(profile, adapter))
    assert identity.kind == "stt"
    assert identity.artifact_sha256 == _hash("3")
    assert identity.profile_fingerprint == profile.fingerprint
    assert len(identity.fingerprint) == 64


def test_adapter_deployment_identity_rejects_artifact_drift():
    profile = _profile()
    adapter = profile.adapters[2]
    promotion = _promotion(profile, adapter)
    drift = replace(adapter, artifact_sha256=_hash("d"))
    with pytest.raises(ValueError, match="voice_deployment_adapter_fingerprint_drift"):
        _seal_adapter_identity(adapter=drift, profile=profile, promotion=promotion)


def test_adapter_deployment_identity_rejects_profile_drift():
    profile = _profile()
    adapter = profile.adapters[2]
    promotion = _promotion(profile, adapter)
    changed = replace(profile, voice_identity_id="different-voice")
    with pytest.raises(ValueError, match="voice_deployment_profile_drift"):
        _seal_adapter_identity(adapter=adapter, profile=changed, promotion=promotion)
