import pytest

from app.voice_adapter_candidates import VOICE_ADAPTER_CANDIDATES, candidate_by_id
from app.voice_adapter_promotion import adapter_fingerprint
from app.voice_runtime import CORE_LANGUAGES


def _hash(ch: str = "a") -> str:
    return ch * 64


def test_candidate_catalog_has_one_candidate_per_voice_pipeline_kind():
    assert {candidate.kind for candidate in VOICE_ADAPTER_CANDIDATES} == {"wakeword", "vad", "stt", "tts"}
    assert all(len(candidate.fingerprint) == 64 for candidate in VOICE_ADAPTER_CANDIDATES)


def test_whisper_and_silero_candidates_build_allowlisted_pinned_specs():
    whisper = candidate_by_id("whisper-cpp-openai-whisper").build_spec(
        adapter_id="stt-whisper-prod-v1",
        artifact_sha256=_hash("1"),
    )
    silero = candidate_by_id("silero-vad-onnx").build_spec(
        adapter_id="vad-silero-prod-v1",
        artifact_sha256=_hash("2"),
    )

    assert whisper.resolved_runtime_license_id == "mit"
    assert whisper.resolved_artifact_license_id == "mit"
    assert set(whisper.languages) == set(CORE_LANGUAGES)
    assert silero.resolved_runtime_license_id == "mit"
    assert len(adapter_fingerprint(whisper)) == 64
    assert len(adapter_fingerprint(silero)) == 64


def test_openwakeword_bundled_noncommercial_models_cannot_be_selected_implicitly():
    wake = candidate_by_id("openwakeword-custom-eay")
    assert wake.bundled_artifact_license_id == "cc-by-nc-sa-4.0"
    with pytest.raises(ValueError, match="voice_candidate_custom_artifact_license_required"):
        wake.build_spec(adapter_id="wake-eay-prod-v1", artifact_sha256=_hash("3"))

    custom = wake.build_spec(
        adapter_id="wake-eay-prod-v1",
        artifact_sha256=_hash("3"),
        artifact_license_id="apache-2.0",
    )
    assert custom.resolved_runtime_license_id == "apache-2.0"
    assert custom.resolved_artifact_license_id == "apache-2.0"


def test_tts_requires_per_voice_model_card_license_before_selection():
    tts = candidate_by_id("sherpa-onnx-piper-vits")
    assert set(tts.languages) == set(CORE_LANGUAGES)
    with pytest.raises(ValueError, match="voice_candidate_per_artifact_license_required"):
        tts.build_spec(adapter_id="tts-core-prod-v1", artifact_sha256=_hash("4"))

    reviewed_voice = tts.build_spec(
        adapter_id="tts-core-prod-v1",
        artifact_sha256=_hash("4"),
        artifact_license_id="mit",
    )
    assert reviewed_voice.resolved_runtime_license_id == "apache-2.0"
    assert reviewed_voice.resolved_artifact_license_id == "mit"


def test_candidate_selection_still_rejects_nonallowlisted_artifact_license():
    wake = candidate_by_id("openwakeword-custom-eay")
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        wake.build_spec(
            adapter_id="wake-eay-prod-v1",
            artifact_sha256=_hash("5"),
            artifact_license_id="cc-by-nc-sa-4.0",
        )
