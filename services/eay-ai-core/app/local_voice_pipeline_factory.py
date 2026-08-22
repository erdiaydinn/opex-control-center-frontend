"""Production builder for wake-gated Jarvis local voice input."""

from __future__ import annotations

from .local_model_pool import LocalModelCatalog, LocalModelDeployment
from .local_voice_pipeline import WakeGatedLocalVoicePipeline
from .local_voice_presence import WakePolicy
from .local_voice_presence_v7 import PreservingWakeGatedVoiceController
from .local_voice_recognizer import LocalVoiceRecognizer
from .local_voice_runtime import LocalAsrBackend, LocalVoicePolicy
from .voice_session import VoiceSession

LOCAL_VOICE_PIPELINE_FACTORY_CONTRACT = "eay-local-voice-pipeline-factory-v2"


def build_wake_gated_local_voice_pipeline(
    *,
    policy: LocalVoicePolicy,
    session: VoiceSession,
    catalog: LocalModelCatalog,
    deployments: tuple[LocalModelDeployment, ...],
    asr_backends: dict[str, LocalAsrBackend],
    wake_policy: WakePolicy | None = None,
) -> WakeGatedLocalVoicePipeline:
    if session.session_id != policy.voice_session_id:
        raise ValueError("local_voice_pipeline_factory_session_mismatch")
    recognizer = LocalVoiceRecognizer(
        policy=policy,
        catalog=catalog,
        deployments=deployments,
        asr_backends=asr_backends,
    )
    presence = PreservingWakeGatedVoiceController(
        session=session,
        policy=wake_policy,
    )
    return WakeGatedLocalVoicePipeline(
        recognizer=recognizer,
        presence=presence,
    )
