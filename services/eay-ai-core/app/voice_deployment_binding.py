from __future__ import annotations

from dataclasses import dataclass

from .voice_execution_identity import VoiceModelExecutionIdentity, VoiceTtsExecutionIdentity


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceDeploymentExecutionBindings:
    """Server-owned exact execution identities for one deployed voice runtime.

    These values are intentionally not accepted from WebSocket clients. Deployment
    startup must construct them from verified model-artifact provenance and a verified
    TTS adapter promotion, then install the immutable binding before spoken responses
    can start.
    """

    model: VoiceModelExecutionIdentity
    tts: VoiceTtsExecutionIdentity

    def validate(self) -> None:
        if not _valid_sha256(self.model.fingerprint) or not _valid_sha256(self.model.artifact_sha256):
            raise ValueError("voice_deployment_model_identity_invalid")
        if not _valid_sha256(self.tts.fingerprint) or not _valid_sha256(self.tts.artifact_sha256):
            raise ValueError("voice_deployment_tts_identity_invalid")
        if not _valid_sha256(self.tts.promotion_fingerprint):
            raise ValueError("voice_deployment_tts_promotion_invalid")


_BINDINGS: VoiceDeploymentExecutionBindings | None = None


def configure_voice_deployment_bindings(bindings: VoiceDeploymentExecutionBindings) -> None:
    global _BINDINGS
    bindings.validate()
    _BINDINGS = bindings


def clear_voice_deployment_bindings() -> None:
    global _BINDINGS
    _BINDINGS = None


def require_voice_deployment_bindings() -> VoiceDeploymentExecutionBindings:
    if _BINDINGS is None:
        raise ValueError("voice_execution_identity_unconfigured")
    _BINDINGS.validate()
    return _BINDINGS
