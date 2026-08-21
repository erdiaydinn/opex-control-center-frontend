from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Literal

from .voice_runtime import CORE_LANGUAGES, VoiceState, VoiceStateMachine


StreamEvent = Literal[
    "wake_detected",
    "audio_frame",
    "vad_speech_started",
    "vad_speech_ended",
    "stt_partial",
    "stt_final",
    "response_started",
    "tts_chunk",
    "barge_in",
    "response_finished",
    "cancelled",
]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AudioFrame:
    sequence: int
    pcm_sha256: str
    duration_ms: int
    sample_rate_hz: int

    def validate(self) -> None:
        if self.sequence < 0:
            raise ValueError("voice_stream_sequence_invalid")
        if len(self.pcm_sha256) != 64 or any(ch not in "0123456789abcdef" for ch in self.pcm_sha256):
            raise ValueError("voice_stream_pcm_sha256_invalid")
        if not 1 <= self.duration_ms <= 200:
            raise ValueError("voice_stream_frame_duration_invalid")
        if self.sample_rate_hz not in {16000, 24000, 48000}:
            raise ValueError("voice_stream_sample_rate_unsupported")


@dataclass(frozen=True)
class StreamingTurn:
    session_id: str
    language: str
    state: VoiceState
    last_sequence: int
    buffered_ms: int
    stt_partial_sha256: str | None
    stt_final_sha256: str | None
    response_id: str | None
    cancelled_response_id: str | None
    fingerprint: str


@dataclass
class VoiceStreamingOrchestrator:
    session_id: str
    language: str
    max_buffer_ms: int = 2000
    machine: VoiceStateMachine = field(default_factory=lambda: VoiceStateMachine(barge_in=True))
    _last_sequence: int = -1
    _buffered_ms: int = 0
    _stt_partial_sha256: str | None = None
    _stt_final_sha256: str | None = None
    _response_id: str | None = None
    _cancelled_response_id: str | None = None

    def __post_init__(self) -> None:
        self.session_id = self.session_id.strip()
        self.language = self.language.strip().lower()
        if len(self.session_id) < 3:
            raise ValueError("voice_stream_session_id_required")
        if self.language not in CORE_LANGUAGES:
            raise ValueError("voice_stream_language_not_enabled")
        if self.max_buffer_ms < 200 or self.max_buffer_ms > 10000:
            raise ValueError("voice_stream_buffer_limit_invalid")

    def wake(self) -> StreamingTurn:
        self.machine.wake()
        return self.snapshot()

    def push_audio(self, frame: AudioFrame) -> StreamingTurn:
        frame.validate()
        if self.machine.state != VoiceState.LISTENING:
            raise ValueError("voice_stream_audio_not_listening")
        if frame.sequence != self._last_sequence + 1:
            raise ValueError("voice_stream_sequence_gap_or_replay")
        if self._buffered_ms + frame.duration_ms > self.max_buffer_ms:
            raise ValueError("voice_stream_backpressure_limit")
        self._last_sequence = frame.sequence
        self._buffered_ms += frame.duration_ms
        return self.snapshot()

    def consume_audio(self, duration_ms: int) -> StreamingTurn:
        if duration_ms < 0:
            raise ValueError("voice_stream_consume_invalid")
        self._buffered_ms = max(0, self._buffered_ms - duration_ms)
        return self.snapshot()

    def stt_partial(self, text: str) -> StreamingTurn:
        if self.machine.state != VoiceState.LISTENING:
            raise ValueError("voice_stream_stt_partial_invalid_state")
        normalized = " ".join(text.strip().split())
        if not normalized:
            raise ValueError("voice_stream_stt_partial_empty")
        self._stt_partial_sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        return self.snapshot()

    def stt_final(self, text: str) -> StreamingTurn:
        if self.machine.state != VoiceState.LISTENING:
            raise ValueError("voice_stream_stt_final_invalid_state")
        normalized = " ".join(text.strip().split())
        if not normalized:
            raise ValueError("voice_stream_stt_final_empty")
        self._stt_final_sha256 = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        self._stt_partial_sha256 = None
        self._buffered_ms = 0
        self.machine.end_utterance()
        return self.snapshot()

    def begin_response(self, response_id: str) -> StreamingTurn:
        response_id = response_id.strip()
        if len(response_id) < 3:
            raise ValueError("voice_stream_response_id_required")
        if self._response_id is not None:
            raise ValueError("voice_stream_response_already_active")
        self.machine.begin_speaking()
        self._response_id = response_id
        self._cancelled_response_id = None
        return self.snapshot()

    def barge_in(self) -> StreamingTurn:
        if self._response_id is None:
            raise ValueError("voice_stream_no_active_response")
        active = self._response_id
        self.machine.interrupt()
        self._cancelled_response_id = active
        self._response_id = None
        self.machine.resume_listening()
        return self.snapshot()

    def finish_response(self) -> StreamingTurn:
        if self.machine.state != VoiceState.SPEAKING or self._response_id is None:
            raise ValueError("voice_stream_finish_invalid_state")
        self._response_id = None
        self.machine.state = VoiceState.IDLE
        return self.snapshot()

    def snapshot(self) -> StreamingTurn:
        payload = {
            "session_id": self.session_id,
            "language": self.language,
            "state": self.machine.state.value,
            "last_sequence": self._last_sequence,
            "buffered_ms": self._buffered_ms,
            "stt_partial_sha256": self._stt_partial_sha256,
            "stt_final_sha256": self._stt_final_sha256,
            "response_id": self._response_id,
            "cancelled_response_id": self._cancelled_response_id,
        }
        return StreamingTurn(
            session_id=self.session_id,
            language=self.language,
            state=self.machine.state,
            last_sequence=self._last_sequence,
            buffered_ms=self._buffered_ms,
            stt_partial_sha256=self._stt_partial_sha256,
            stt_final_sha256=self._stt_final_sha256,
            response_id=self._response_id,
            cancelled_response_id=self._cancelled_response_id,
            fingerprint=_sha256(payload),
        )
