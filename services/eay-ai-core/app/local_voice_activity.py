"""Local voice-activity gate for Jarvis microphone streams.

This detector works only on transient PCM amplitude and never persists audio.
It is intentionally not speaker identity and not command authority. It simply
reduces unnecessary ASR work and marks likely utterance start/end boundaries.
Identity remains the existing session/identity evidence contract.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .local_voice_runtime import TransientAudioFrame

LOCAL_VOICE_ACTIVITY_CONTRACT = "eay-local-voice-activity-v1"


class VoiceActivityState(str, Enum):
    SILENCE = "silence"
    SPEECH = "speech"
    UTTERANCE_ENDED = "utterance_ended"


class VoiceActivityObservation(BaseModel):
    contract: str = LOCAL_VOICE_ACTIVITY_CONTRACT
    sequence: int = Field(ge=0)
    state: VoiceActivityState
    rms: float = Field(ge=0.0, le=1.0)
    speech_frames: int = Field(ge=0)
    silence_frames: int = Field(ge=0)
    raw_audio_retained: bool = False
    speaker_identity_inferred: bool = False
    command_authorized: bool = False

    @model_validator(mode="after")
    def observation_is_non_authorizing(self) -> "VoiceActivityObservation":
        if self.raw_audio_retained:
            raise ValueError("local_voice_activity_cannot_retain_audio")
        if self.speaker_identity_inferred:
            raise ValueError("local_voice_activity_cannot_infer_identity")
        if self.command_authorized:
            raise ValueError("local_voice_activity_never_authorizes_commands")
        return self


def _pcm16_rms(frame: TransientAudioFrame) -> float:
    data = frame.pcm16
    count = len(data) // 2
    if count == 0:
        return 0.0
    square_sum = 0.0
    for index in range(0, len(data), 2):
        sample = int.from_bytes(data[index:index + 2], byteorder="little", signed=True)
        normalized = sample / 32768.0
        square_sum += normalized * normalized
    return min(1.0, math.sqrt(square_sum / count))


@dataclass
class LocalVoiceActivityGate:
    rms_threshold: float = 0.015
    minimum_speech_frames: int = 2
    end_silence_frames: int = 4

    def __post_init__(self) -> None:
        if not 0.0 < self.rms_threshold < 1.0:
            raise ValueError("local_voice_activity_threshold_invalid")
        if self.minimum_speech_frames < 1 or self.end_silence_frames < 1:
            raise ValueError("local_voice_activity_frame_threshold_invalid")
        self._speech_frames = 0
        self._silence_frames = 0
        self._speech_active = False
        self._last_sequence: int | None = None

    def consume(self, frame: TransientAudioFrame) -> VoiceActivityObservation:
        if self._last_sequence is not None and frame.sequence <= self._last_sequence:
            raise ValueError("local_voice_activity_sequence_must_increase")
        self._last_sequence = frame.sequence
        rms = _pcm16_rms(frame)
        is_speech = rms >= self.rms_threshold

        if is_speech:
            self._speech_frames += 1
            self._silence_frames = 0
            if self._speech_frames >= self.minimum_speech_frames:
                self._speech_active = True
            state = VoiceActivityState.SPEECH if self._speech_active else VoiceActivityState.SILENCE
        else:
            self._silence_frames += 1
            if self._speech_active and self._silence_frames >= self.end_silence_frames:
                state = VoiceActivityState.UTTERANCE_ENDED
                self._speech_active = False
                self._speech_frames = 0
                self._silence_frames = 0
            else:
                if not self._speech_active:
                    self._speech_frames = 0
                state = VoiceActivityState.SPEECH if self._speech_active else VoiceActivityState.SILENCE

        return VoiceActivityObservation(
            sequence=frame.sequence,
            state=state,
            rms=round(rms, 6),
            speech_frames=self._speech_frames,
            silence_frames=self._silence_frames,
        )
