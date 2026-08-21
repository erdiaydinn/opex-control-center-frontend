from datetime import datetime, timezone

import pytest

from app.model_artifact_provenance import ArtifactRecord
from app.voice_adapter_promotion import VoiceAdapterPromotion, adapter_fingerprint
from app.voice_execution_identity import seal_model_execution_identity, seal_tts_execution_identity
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec, VoiceProfile


def _hash(ch: str) -> str:
    return ch * 64


def _profile(tts_artifact: str = _hash("4"), tts_license: str = "apache-2.0") -> tuple[VoiceProfile, VoiceAdapterSpec]:
    adapters = (
        VoiceAdapterSpec("wake-v1", "wakeword", "wake-local", True, True, "apache-2.0", CORE_LANGUAGES, _hash("1")),
        VoiceAdapterSpec("vad-v1", "vad", "vad-local", True, True, "apache-2.0", CORE_LANGUAGES, _hash("2")),
        VoiceAdapterSpec("stt-v1", "stt", "stt-local", True, True, "apache-2.0", CORE_LANGUAGES, _hash("3")),
        VoiceAdapterSpec("tts-v1", "tts", "tts-local-v1", True, True, tts_license, CORE_LANGUAGES, tts_artifact),
    )
    profile = VoiceProfile(
        profile_id="eay-jarvis-test-v1",
        wake_phrases=("EAY",),
        languages=CORE_LANGUAGES,
        sample_rate_hz=16000,
        full_duplex=True,
        barge_in=True,
        local_first=True,
        voice_identity_id="eay-test-natural-v1",
        clone_reference_voice=False,
        adapters=adapters,
    )
    profile.validate()
    return profile, adapters[-1]


def _promotion(profile: VoiceProfile, adapter: VoiceAdapterSpec) -> VoiceAdapterPromotion:
    return VoiceAdapterPromotion(
        adapter_id=adapter.adapter_id,
        kind="tts",
        adapter_artifact_sha256=str(adapter.artifact_sha256),
        adapter_fingerprint=adapter_fingerprint(adapter),
        profile_fingerprint=profile.fingerprint,
        language_capability_fingerprints=tuple(_hash(ch) for ch in "56789"),
        reviewer="reviewer",
        approval_reference="VOICE-123",
        promoted_at="2026-08-11T00:00:00+00:00",
        fingerprint=_hash("a"),
    )


def test_model_execution_identity_binds_artifact_training_and_build():
    record = ArtifactRecord(
        id="artifact-1",
        fingerprint=_hash("a"),
        training_job_fingerprint=_hash("b"),
        artifact_sha256=_hash("c"),
        format="GGUF",
        created_by="builder",
        build_reference="ci://build/123",
        created_at=datetime.now(timezone.utc),
    )
    identity = seal_model_execution_identity(record)
    assert identity.artifact_sha256 == _hash("c")
    assert identity.training_job_fingerprint == _hash("b")
    assert identity.artifact_format == "gguf"
    assert len(identity.build_reference_sha256) == 64
    assert len(identity.fingerprint) == 64


def test_tts_execution_identity_binds_exact_promotion_license_and_artifact():
    profile, adapter = _profile()
    identity = seal_tts_execution_identity(adapter=adapter, profile=profile, promotion=_promotion(profile, adapter))
    assert identity.artifact_sha256 == _hash("4")
    assert identity.license_id == "apache-2.0"
    assert identity.adapter_id == "tts-v1"
    assert identity.profile_fingerprint == profile.fingerprint
    assert len(identity.fingerprint) == 64


def test_tts_execution_identity_rejects_artifact_drift_after_promotion():
    profile, adapter = _profile()
    promotion = _promotion(profile, adapter)
    drift_profile, drift_adapter = _profile(tts_artifact=_hash("d"))
    with pytest.raises(ValueError, match="voice_tts_execution_artifact_drift"):
        seal_tts_execution_identity(adapter=drift_adapter, profile=drift_profile, promotion=promotion)


def test_tts_execution_identity_rejects_license_drift_after_promotion():
    profile, adapter = _profile()
    promotion = _promotion(profile, adapter)
    drift_profile, drift_adapter = _profile(tts_license="mit")
    with pytest.raises(ValueError, match="voice_tts_execution_adapter_drift"):
        seal_tts_execution_identity(adapter=drift_adapter, profile=drift_profile, promotion=promotion)
