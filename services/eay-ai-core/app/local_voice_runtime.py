"""Privacy-safe local realtime voice composition for Jarvis.

Raw microphone PCM and transcript text remain transient process-memory objects.
Only opaque transcript/evidence references, local model selections, timing and
voice-session state are serializable. Partial ASR results can never create
intent. A final utterance becomes intent-eligible only when exact principal and
identity evidence are supplied to the existing VoiceSession contract.

TTS is local-first through the same evidence/licence/language-gated local model
pool. Speech playback is explicitly interruptible: barge-in stops the active
local playback before updating the VoiceSession state.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, model_validator

from .local_model_pool import (
    LocalCapability,
    LocalModelCatalog,
    LocalModelDeployment,
    LocalModelSelection,
    LocalModelTask,
    select_local_model,
)
from .voice_session import (
    VoiceEvent,
    VoiceEventKind,
    VoiceSession,
    VoiceTransition,
    apply_voice_event,
)

LOCAL_VOICE_RUNTIME_CONTRACT = "eay-local-voice-runtime-v1"


@dataclass(frozen=True)
class TransientAudioFrame:
    """PCM bytes that must never cross the persistence/audit boundary."""

    pcm16: bytes = field(repr=False)
    captured_at: datetime
    sequence: int
    sample_rate_hz: int = 16000
    channels: int = 1
    final_chunk: bool = False

    def __post_init__(self) -> None:
        if self.captured_at.tzinfo is None or self.captured_at.utcoffset() is None:
            raise ValueError("local_voice_audio_requires_timezone")
        if self.sequence < 0:
            raise ValueError("local_voice_audio_sequence_invalid")
        if self.sample_rate_hz not in {8000, 16000, 24000, 32000, 48000}:
            raise ValueError("local_voice_audio_sample_rate_unsupported")
        if self.channels != 1:
            raise ValueError("local_voice_audio_mono_required")
        if len(self.pcm16) == 0 or len(self.pcm16) % 2:
            raise ValueError("local_voice_audio_pcm16_invalid")


@dataclass(frozen=True)
class TransientTranscript:
    """ASR text is available to immediate intent resolution but not persistence."""

    text: str = field(repr=False)
    transcript_ref: str
    language_code: str
    confidence: float
    final: bool

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("local_voice_transcript_empty")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("local_voice_transcript_confidence_invalid")


@dataclass(frozen=True)
class TransientSpeechAudio:
    pcm16: bytes = field(repr=False)
    sample_rate_hz: int
    channels: int = 1

    def __post_init__(self) -> None:
        if not self.pcm16 or len(self.pcm16) % 2:
            raise ValueError("local_voice_tts_pcm16_invalid")
        if self.sample_rate_hz <= 0 or self.channels != 1:
            raise ValueError("local_voice_tts_audio_format_invalid")


class LocalAsrResult(BaseModel):
    language_code: str = Field(min_length=2, max_length=16)
    confidence: float = Field(ge=0.0, le=1.0)
    final: bool
    backend_evidence_ref: str = Field(min_length=1)
    local_processing: bool = True
    raw_audio_retained: bool = False
    transcript_text_retained: bool = False

    @model_validator(mode="after")
    def result_is_local_and_private(self) -> "LocalAsrResult":
        if not self.local_processing:
            raise ValueError("local_voice_asr_must_process_locally")
        if self.raw_audio_retained or self.transcript_text_retained:
            raise ValueError("local_voice_asr_cannot_retain_content")
        return self


class LocalAsrBackend(Protocol):
    def transcribe(
        self,
        audio: TransientAudioFrame,
        *,
        language_code: str,
    ) -> tuple[str, LocalAsrResult]: ...


class LocalTtsResult(BaseModel):
    language_code: str
    backend_evidence_ref: str = Field(min_length=1)
    local_processing: bool = True
    input_text_retained: bool = False
    generated_audio_retained: bool = False

    @model_validator(mode="after")
    def result_is_local_and_private(self) -> "LocalTtsResult":
        if not self.local_processing:
            raise ValueError("local_voice_tts_must_process_locally")
        if self.input_text_retained or self.generated_audio_retained:
            raise ValueError("local_voice_tts_cannot_retain_content")
        return self


class LocalTtsBackend(Protocol):
    def synthesize(
        self,
        text: str,
        *,
        language_code: str,
    ) -> tuple[TransientSpeechAudio, LocalTtsResult]: ...


class LocalPlaybackHandle(BaseModel):
    playback_ref: str = Field(min_length=1)
    started_at: datetime
    local_device_ref: str = Field(min_length=1)
    active: bool = True
    audio_retained: bool = False

    @model_validator(mode="after")
    def handle_is_private(self) -> "LocalPlaybackHandle":
        if self.started_at.tzinfo is None or self.started_at.utcoffset() is None:
            raise ValueError("local_voice_playback_requires_timezone")
        if self.audio_retained:
            raise ValueError("local_voice_playback_cannot_retain_audio")
        return self


class LocalPlaybackBackend(Protocol):
    def start(self, audio: TransientSpeechAudio, *, started_at: datetime) -> LocalPlaybackHandle: ...
    def stop(self, playback_ref: str) -> LocalPlaybackHandle: ...


class LocalVoicePolicy(BaseModel):
    voice_session_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    language_code: str = Field(min_length=2, max_length=16)
    minimum_asr_benchmark: float = Field(default=0.80, ge=0.0, le=1.0)
    minimum_tts_benchmark: float = Field(default=0.80, ge=0.0, le=1.0)
    raw_audio_persistence_allowed: bool = False
    transcript_persistence_allowed: bool = False
    external_speech_processing_allowed: bool = False

    @model_validator(mode="after")
    def policy_is_local_private(self) -> "LocalVoicePolicy":
        if self.language_code != self.language_code.casefold():
            raise ValueError("local_voice_language_code_must_be_lowercase")
        if self.raw_audio_persistence_allowed or self.transcript_persistence_allowed:
            raise ValueError("local_voice_policy_cannot_persist_voice_content")
        if self.external_speech_processing_allowed:
            raise ValueError("local_voice_policy_is_local_only")
        return self


class LocalVoiceTurnReceipt(BaseModel):
    contract: str = LOCAL_VOICE_RUNTIME_CONTRACT
    voice_session_id: str
    sequence: int
    asr_selection: LocalModelSelection
    transcript_ref: str
    language_code: str
    final: bool
    intent_eligible: bool
    voice_event_id: str
    voice_state: str
    backend_evidence_ref: str
    raw_audio_retained: bool = False
    transcript_text_retained: bool = False
    paid_frontier_used: bool = False

    @model_validator(mode="after")
    def receipt_is_content_free(self) -> "LocalVoiceTurnReceipt":
        if self.raw_audio_retained or self.transcript_text_retained:
            raise ValueError("local_voice_turn_receipt_cannot_retain_content")
        if self.paid_frontier_used:
            raise ValueError("local_voice_runtime_never_spends_frontier_tokens")
        return self


class LocalSpeechReceipt(BaseModel):
    contract: str = LOCAL_VOICE_RUNTIME_CONTRACT
    voice_session_id: str
    tts_selection: LocalModelSelection
    playback_ref: str
    local_device_ref: str
    backend_evidence_ref: str
    language_code: str
    input_text_retained: bool = False
    generated_audio_retained: bool = False
    paid_frontier_used: bool = False

    @model_validator(mode="after")
    def receipt_is_content_free(self) -> "LocalSpeechReceipt":
        if self.input_text_retained or self.generated_audio_retained:
            raise ValueError("local_voice_speech_receipt_cannot_retain_content")
        if self.paid_frontier_used:
            raise ValueError("local_voice_runtime_never_spends_frontier_tokens")
        return self


class BargeInReceipt(BaseModel):
    contract: str = LOCAL_VOICE_RUNTIME_CONTRACT
    voice_session_id: str
    playback_ref: str | None = None
    playback_stopped: bool
    voice_transition: VoiceTransition
    raw_audio_retained: bool = False


class LocalVoiceRuntime:
    def __init__(
        self,
        *,
        policy: LocalVoicePolicy,
        session: VoiceSession,
        catalog: LocalModelCatalog,
        deployments: tuple[LocalModelDeployment, ...],
        asr_backends: dict[str, LocalAsrBackend],
        tts_backends: dict[str, LocalTtsBackend],
        playback: LocalPlaybackBackend,
    ) -> None:
        if session.session_id != policy.voice_session_id:
            raise ValueError("local_voice_session_policy_mismatch")
        self.policy = policy
        self.session = session
        self.catalog = catalog
        self.deployments = deployments
        self.asr_backends = dict(asr_backends)
        self.tts_backends = dict(tts_backends)
        self.playback = playback
        self._active_playback: LocalPlaybackHandle | None = None
        self._seen_sequences: set[int] = set()

    def _select_asr(self) -> LocalModelSelection:
        return select_local_model(
            task=LocalModelTask(
                task_ref=f"voice-asr:{self.policy.voice_session_id}",
                task_class="STREAMING_ASR",
                required_capabilities=frozenset(
                    {LocalCapability.AUDIO, LocalCapability.ASR, LocalCapability.MULTILINGUAL}
                ),
                minimum_benchmark_score=self.policy.minimum_asr_benchmark,
                language_code=self.policy.language_code,
            ),
            deployments=self.deployments,
            catalog=self.catalog,
        )

    def _select_tts(self) -> LocalModelSelection:
        return select_local_model(
            task=LocalModelTask(
                task_ref=f"voice-tts:{self.policy.voice_session_id}",
                task_class="TURKISH_TTS" if self.policy.language_code == "tr" else "VOICE_SYNTHESIS",
                required_capabilities=frozenset(
                    {LocalCapability.AUDIO, LocalCapability.TTS, LocalCapability.MULTILINGUAL}
                ),
                minimum_benchmark_score=self.policy.minimum_tts_benchmark,
                language_code=self.policy.language_code,
            ),
            deployments=self.deployments,
            catalog=self.catalog,
        )

    @staticmethod
    def _transcript_ref(session_id: str, sequence: int, text: str) -> str:
        digest = hashlib.sha256(f"{session_id}|{sequence}|{text}".encode("utf-8")).hexdigest()
        return f"transcript://local/{digest}"

    def transcribe(
        self,
        audio: TransientAudioFrame,
        *,
        identity_verified: bool,
    ) -> tuple[TransientTranscript, LocalVoiceTurnReceipt]:
        if audio.sequence in self._seen_sequences:
            raise ValueError("local_voice_audio_sequence_duplicate")
        self._seen_sequences.add(audio.sequence)
        selection = self._select_asr()
        if not selection.local_execution_available or not selection.deployment_id:
            raise RuntimeError("local_voice_verified_asr_unavailable")
        backend = self.asr_backends.get(selection.deployment_id)
        if backend is None:
            raise RuntimeError("local_voice_selected_asr_backend_missing")
        text, result = backend.transcribe(audio, language_code=self.policy.language_code)
        if result.language_code.casefold() != self.policy.language_code:
            raise RuntimeError("local_voice_asr_language_mismatch")
        final = bool(result.final and audio.final_chunk)
        transcript_ref = self._transcript_ref(self.policy.voice_session_id, audio.sequence, text)
        transient = TransientTranscript(
            text=text,
            transcript_ref=transcript_ref,
            language_code=result.language_code.casefold(),
            confidence=result.confidence,
            final=final,
        )
        event_kind = VoiceEventKind.FINAL_UTTERANCE if final else VoiceEventKind.PARTIAL_UTTERANCE
        event_id = f"voice-local:{self.policy.voice_session_id}:{audio.sequence}"
        event = VoiceEvent(
            event_id=event_id,
            session_id=self.policy.voice_session_id,
            occurred_at=audio.captured_at,
            kind=event_kind,
            principal_ref=self.policy.principal_ref if final else None,
            transcript_ref=transcript_ref,
            identity_verified=bool(final and identity_verified),
            identity_evidence_ref=self.policy.identity_evidence_ref if final and identity_verified else None,
        )
        self.session, transition = apply_voice_event(self.session, event)
        return transient, LocalVoiceTurnReceipt(
            voice_session_id=self.policy.voice_session_id,
            sequence=audio.sequence,
            asr_selection=selection,
            transcript_ref=transcript_ref,
            language_code=transient.language_code,
            final=final,
            intent_eligible=transition.intent_accepted,
            voice_event_id=event_id,
            voice_state=self.session.state.value,
            backend_evidence_ref=result.backend_evidence_ref,
        )

    def speak(self, text: str, *, started_at: datetime) -> LocalSpeechReceipt:
        if not text.strip():
            raise ValueError("local_voice_tts_text_required")
        selection = self._select_tts()
        if not selection.local_execution_available or not selection.deployment_id:
            raise RuntimeError("local_voice_verified_tts_unavailable")
        backend = self.tts_backends.get(selection.deployment_id)
        if backend is None:
            raise RuntimeError("local_voice_selected_tts_backend_missing")
        audio, result = backend.synthesize(text, language_code=self.policy.language_code)
        if result.language_code.casefold() != self.policy.language_code:
            raise RuntimeError("local_voice_tts_language_mismatch")
        handle = self.playback.start(audio, started_at=started_at)
        self._active_playback = handle
        event = VoiceEvent(
            event_id=f"voice-local-speech:{handle.playback_ref}",
            session_id=self.policy.voice_session_id,
            occurred_at=started_at,
            kind=VoiceEventKind.ASSISTANT_SPEECH_STARTED,
        )
        self.session, _ = apply_voice_event(self.session, event)
        return LocalSpeechReceipt(
            voice_session_id=self.policy.voice_session_id,
            tts_selection=selection,
            playback_ref=handle.playback_ref,
            local_device_ref=handle.local_device_ref,
            backend_evidence_ref=result.backend_evidence_ref,
            language_code=result.language_code.casefold(),
        )

    def finish_speech(self, *, occurred_at: datetime) -> VoiceTransition:
        event = VoiceEvent(
            event_id=f"voice-local-speech-finished:{int(occurred_at.timestamp() * 1000)}",
            session_id=self.policy.voice_session_id,
            occurred_at=occurred_at,
            kind=VoiceEventKind.ASSISTANT_SPEECH_FINISHED,
        )
        self.session, transition = apply_voice_event(self.session, event)
        self._active_playback = None
        return transition

    def barge_in(self, *, occurred_at: datetime) -> BargeInReceipt:
        playback_ref: str | None = None
        stopped = False
        if self._active_playback is not None and self._active_playback.active:
            playback_ref = self._active_playback.playback_ref
            stopped_handle = self.playback.stop(playback_ref)
            stopped = not stopped_handle.active
            if not stopped:
                raise RuntimeError("local_voice_barge_in_playback_stop_failed")
            self._active_playback = stopped_handle
        event = VoiceEvent(
            event_id=f"voice-local-barge-in:{int(occurred_at.timestamp() * 1000)}",
            session_id=self.policy.voice_session_id,
            occurred_at=occurred_at,
            kind=VoiceEventKind.BARGE_IN,
        )
        self.session, transition = apply_voice_event(self.session, event)
        return BargeInReceipt(
            voice_session_id=self.policy.voice_session_id,
            playback_ref=playback_ref,
            playback_stopped=stopped,
            voice_transition=transition,
        )
