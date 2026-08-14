import pytest
from fastapi.testclient import TestClient

from app.entrypoint import app
from app.voice_deployment_binding import (
    VoiceDeploymentExecutionBindings,
    clear_voice_deployment_bindings,
    configure_voice_deployment_bindings,
    require_voice_deployment_bindings,
)
from app.voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity


def _hash(ch: str) -> str:
    return ch * 64


def _synthetic_binding() -> VoiceDeploymentExecutionBindings:
    model = VoiceModelExecutionIdentity(
        artifact_sha256=_hash("1"),
        artifact_provenance_fingerprint=_hash("2"),
        training_job_fingerprint=_hash("3"),
        artifact_format="gguf",
        build_reference_sha256=_hash("4"),
        fingerprint=_hash("5"),
    )
    tts = VoiceTtsExecutionIdentity(
        adapter_id="tts-test-v1",
        implementation="sherpa-onnx-vits",
        license_id="apache-2.0",
        license_id_sha256=_hash("6"),
        artifact_sha256=_hash("7"),
        adapter_fingerprint=_hash("8"),
        promotion_fingerprint=_hash("9"),
        profile_fingerprint=_hash("a"),
        language_capability_fingerprints=(_hash("b"),),
        fingerprint=_hash("c"),
    )
    return VoiceDeploymentExecutionBindings(
        model=model,
        tts=tts,
        deployment_manifest_fingerprint=_hash("0"),
    )


def test_production_websocket_rejects_registry_verified_but_unreleased_binding(monkeypatch):
    clear_voice_deployment_bindings()
    configure_voice_deployment_bindings(_synthetic_binding())
    monkeypatch.setenv("EAY_VOICE_RUNTIME_MODE", "production")
    try:
        with pytest.raises(Exception):
            with TestClient(app).websocket_connect("/v1/voice/ws/prod-unreleased?language=tr"):
                pass
        with pytest.raises(ValueError, match="voice_deployment_production_release_required"):
            require_voice_deployment_bindings(require_production_release=True)
    finally:
        clear_voice_deployment_bindings()


def test_invalid_runtime_mode_fails_closed_before_websocket_accept(monkeypatch):
    clear_voice_deployment_bindings()
    configure_voice_deployment_bindings(_synthetic_binding())
    monkeypatch.setenv("EAY_VOICE_RUNTIME_MODE", "typo-production")
    try:
        with pytest.raises(Exception):
            with TestClient(app).websocket_connect("/v1/voice/ws/prod-invalid-mode?language=tr"):
                pass
    finally:
        clear_voice_deployment_bindings()
