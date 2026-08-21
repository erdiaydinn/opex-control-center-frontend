import pytest

from app.voice_adapter_promotion import adapter_fingerprint
from app.voice_runtime import CORE_LANGUAGES, VoiceAdapterSpec


def _spec(*, runtime_license: str, artifact_license: str) -> VoiceAdapterSpec:
    return VoiceAdapterSpec(
        adapter_id="voice-license-split-v1",
        kind="wakeword",
        implementation="local-runtime",
        local=True,
        streaming=True,
        license_id=artifact_license,
        languages=CORE_LANGUAGES,
        artifact_sha256="a" * 64,
        runtime_license_id=runtime_license,
        artifact_license_id=artifact_license,
    )


def test_permissive_runtime_cannot_bless_noncommercial_model_artifact():
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        adapter_fingerprint(
            _spec(runtime_license="apache-2.0", artifact_license="cc-by-nc-sa-4.0")
        )


def test_allowlisted_artifact_cannot_bless_nonallowlisted_runtime():
    with pytest.raises(ValueError, match="model_license_not_allowlisted"):
        adapter_fingerprint(
            _spec(runtime_license="gpl-3.0", artifact_license="mit")
        )


def test_both_runtime_and_artifact_must_be_allowlisted():
    fingerprint = adapter_fingerprint(
        _spec(runtime_license="apache-2.0", artifact_license="mit")
    )
    assert len(fingerprint) == 64
