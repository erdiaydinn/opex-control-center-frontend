from app.voice_adapter_candidates import candidate_by_id
from app.voice_runtime import CORE_LANGUAGES


def test_openwakeword_candidate_does_not_overclaim_upstream_language_support():
    wake = candidate_by_id("openwakeword-custom-eay")
    assert wake.languages == ("en",)
    assert set(wake.languages) != set(CORE_LANGUAGES)
    assert wake.status == "custom_artifact_required"
