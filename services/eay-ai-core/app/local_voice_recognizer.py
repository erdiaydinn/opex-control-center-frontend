"""Local ASR recognition stage without VoiceSession side effects.

This is the first half of the wake-gated production voice pipeline. It selects
an evidence-backed local ASR model, transcribes transient PCM, and returns a
transient transcript plus a content-free receipt. It deliberately does not
create VoiceEvents or mutate VoiceSession state; wake/presence/identity policy
must run first.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from pydantic import BaseModel, Field, model_validator

from .local_model_pool import (
    LocalCapability,
    LocalModelCatalog,
    LocalModelDeployment,
    LocalModelSelection,
    LocalModelTask,
    select_local_model,
)
from .local_voice_runtime import (
    LocalAsrBackend,
    LocalVoicePolicy,
    TransientAudioFrame,
    TransientTranscript,
)

LOCAL_VOICE_RECOGNIZER_CONTRACT = "eay-local-voice-recognizer-v1"


class LocalRecognitionReceipt(BaseModel):
    contract: str = LOCAL_VOICE_RECOGNIZER_CONTRACT
    voice_session_id: str
    sequence: int = Field(ge=0)
    asr_selection: LocalModelSelection
    transcript_ref: str = Field(min_length=1)
    language_code: str = Field(min_length=2)
    confidence: float = Field(ge=0.0, le=1.0)
    final: bool
    backend_evidence_ref: str = Field(min_length=1)
    voice_event_created: bool = False
    intent_eligible: bool = False
    raw_audio_retained: bool = False
    transcript_text_retained: bool = False
    paid_frontier_used: bool = False

    @model_validator(mode="after")
    def receipt_stops_before_intent_boundary(self) -> "LocalRecognitionReceipt":
        if self.voice_event_created or self.intent_eligible:
            raise ValueError("local_voice_recognizer_cannot_create_intent")
        if self.raw_audio_retained or self.transcript_text_retained:
            raise ValueError("local_voice_recognizer_cannot_retain_content")
        if self.paid_frontier_used:
            raise ValueError("local_voice_recognizer_never_spends_frontier_tokens")
        return self


class LocalVoiceRecognizer:
    def __init__(
        self,
        *,
        policy: LocalVoicePolicy,
        catalog: LocalModelCatalog,
        deployments: tuple[LocalModelDeployment, ...],
        asr_backends: dict[str, LocalAsrBackend],
        transcript_hmac_key: bytes | None = None,
    ) -> None:
        self.policy = policy
        self.catalog = catalog
        self.deployments = deployments
        self.asr_backends = dict(asr_backends)
        key = transcript_hmac_key if transcript_hmac_key is not None else secrets.token_bytes(32)
        if len(key) < 32:
            raise ValueError("local_voice_recognizer_hmac_key_too_short")
        self._hmac_key = bytes(key)
        self._seen_sequences: set[int] = set()

    def _select_asr(self) -> LocalModelSelection:
        return select_local_model(
            task=LocalModelTask(
                task_ref=f"voice-recognizer:{self.policy.voice_session_id}",
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

    def _transcript_ref(self, *, sequence: int, text: str) -> str:
        digest = hmac.new(
            self._hmac_key,
            f"{self.policy.voice_session_id}|{sequence}|{text}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return f"transcript://local-wake-gated/{digest}"

    def recognize(
        self,
        audio: TransientAudioFrame,
    ) -> tuple[TransientTranscript, LocalRecognitionReceipt]:
        if audio.sequence in self._seen_sequences:
            raise ValueError("local_voice_recognizer_sequence_duplicate")
        self._seen_sequences.add(audio.sequence)
        selection = self._select_asr()
        if not selection.local_execution_available or not selection.deployment_id:
            raise RuntimeError("local_voice_recognizer_verified_asr_unavailable")
        backend = self.asr_backends.get(selection.deployment_id)
        if backend is None:
            raise RuntimeError("local_voice_recognizer_selected_backend_missing")
        text, result = backend.transcribe(audio, language_code=self.policy.language_code)
        if result.language_code.casefold() != self.policy.language_code:
            raise RuntimeError("local_voice_recognizer_language_mismatch")
        final = bool(result.final and audio.final_chunk)
        transcript_ref = self._transcript_ref(sequence=audio.sequence, text=text)
        transient = TransientTranscript(
            text=text,
            transcript_ref=transcript_ref,
            language_code=result.language_code.casefold(),
            confidence=result.confidence,
            final=final,
        )
        return transient, LocalRecognitionReceipt(
            voice_session_id=self.policy.voice_session_id,
            sequence=audio.sequence,
            asr_selection=selection,
            transcript_ref=transcript_ref,
            language_code=transient.language_code,
            confidence=transient.confidence,
            final=transient.final,
            backend_evidence_ref=result.backend_evidence_ref,
        )
