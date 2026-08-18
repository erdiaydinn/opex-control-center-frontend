"""Production construction boundary for Jarvis local voice.

Application code should construct local voice only through this builder. It
always returns ``HardenedLocalVoiceRuntime`` with an ephemeral HMAC key; the
base runtime remains a testable contract implementation but is not the
production entrypoint.
"""

from __future__ import annotations

from .local_model_pool import LocalModelCatalog, LocalModelDeployment
from .local_voice_privacy_runtime import HardenedLocalVoiceRuntime
from .local_voice_runtime import (
    LocalAsrBackend,
    LocalPlaybackBackend,
    LocalTtsBackend,
    LocalVoicePolicy,
)
from .voice_session import VoiceSession

LOCAL_VOICE_FACTORY_CONTRACT = "eay-local-voice-factory-v1"


def build_production_local_voice_runtime(
    *,
    policy: LocalVoicePolicy,
    session: VoiceSession,
    catalog: LocalModelCatalog,
    deployments: tuple[LocalModelDeployment, ...],
    asr_backends: dict[str, LocalAsrBackend],
    tts_backends: dict[str, LocalTtsBackend],
    playback: LocalPlaybackBackend,
) -> HardenedLocalVoiceRuntime:
    return HardenedLocalVoiceRuntime(
        policy=policy,
        session=session,
        catalog=catalog,
        deployments=deployments,
        asr_backends=asr_backends,
        tts_backends=tts_backends,
        playback=playback,
    )
