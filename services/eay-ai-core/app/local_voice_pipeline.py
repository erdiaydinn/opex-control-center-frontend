"""Wake-gated production input pipeline for Jarvis local voice.

Ordering is structural: transient PCM -> local ASR recognizer -> trusted
wake/presence gate -> VoiceSession. No caller can obtain an intent-eligible
VoiceEvent from this pipeline before the presence gate has validated wake and
trusted local identity.
"""

from __future__ import annotations

from dataclasses import dataclass

from .local_voice_presence import (
    TrustedLocalVoiceIdentity,
    TransientVoiceCommand,
    VoicePresenceReceipt,
    WakeGatedVoiceController,
)
from .local_voice_recognizer import LocalRecognitionReceipt, LocalVoiceRecognizer
from .local_voice_runtime import TransientAudioFrame, TransientTranscript

LOCAL_VOICE_PIPELINE_CONTRACT = "eay-local-voice-pipeline-v1"


@dataclass(frozen=True)
class LocalVoicePipelineResult:
    transcript: TransientTranscript
    recognition: LocalRecognitionReceipt
    command: TransientVoiceCommand | None
    presence: VoicePresenceReceipt


@dataclass
class WakeGatedLocalVoicePipeline:
    recognizer: LocalVoiceRecognizer
    presence: WakeGatedVoiceController

    def process(
        self,
        audio: TransientAudioFrame,
        *,
        identity: TrustedLocalVoiceIdentity,
    ) -> LocalVoicePipelineResult:
        transcript, recognition = self.recognizer.recognize(audio)
        command, presence = self.presence.consume(
            transcript=transcript,
            recognition=recognition,
            identity=identity,
            occurred_at=audio.captured_at,
        )
        return LocalVoicePipelineResult(
            transcript=transcript,
            recognition=recognition,
            command=command,
            presence=presence,
        )
