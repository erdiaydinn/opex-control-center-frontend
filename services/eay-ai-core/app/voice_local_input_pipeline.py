from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .voice_audio_dataplane import VoiceAudioBufferReceipt, VoiceAudioDataPlane
from .voice_input_lineage import VoiceInputLineageTracker, VoiceSttInputProof, VoiceWakeInputProof
from .voice_local_audio_adapter import PinnedLocalSttAdapter, PinnedLocalVadAdapter, VoiceTransientSttResult, VoiceVadExecutionResult
from .voice_runtime import CORE_LANGUAGES


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceLocalUtteranceProof:
    session_id: str
    language: str
    deployment_manifest_fingerprint: str
    wake_proof_fingerprint: str
    input_lineage_fingerprint: str
    audio_chain_fingerprint: str
    audio_frame_count: int
    audio_duration_ms: int
    vad_result_fingerprint: str
    stt_result_fingerprint: str
    stt_runtime_seal_fingerprint: str
    text_sha256: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceTransientUtterance:
    """Transient text plus hash-only proof; callers must not persist ``text`` in audit."""

    text: str
    text_sha256: str
    proof: VoiceLocalUtteranceProof


class VoiceLocalInputPipeline:
    """Own one wake/VAD/STT microphone path under a pinned deployment manifest.

    PCM ownership remains in ``VoiceAudioDataPlane``. Every accepted frame is sealed
    into ``VoiceInputLineageTracker`` immediately. VAD only inspects RAM. Once speech
    has been observed, finalize_utterance consumes all buffered PCM through STT,
    wipes it, and returns transient text with a hash-only end-to-end proof.
    """

    def __init__(
        self,
        *,
        session_id: str,
        language: str,
        deployment_manifest_fingerprint: str,
        input_lineage: VoiceInputLineageTracker,
        vad: PinnedLocalVadAdapter,
        stt: PinnedLocalSttAdapter,
        max_utterance_ms: int = 30_000,
        max_buffer_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        language = language.strip().lower()
        if language not in CORE_LANGUAGES:
            raise ValueError("voice_local_pipeline_language_not_enabled")
        if input_lineage.session_id != session_id or input_lineage.language != language:
            raise ValueError("voice_local_pipeline_input_lineage_identity_mismatch")
        if input_lineage.deployment_manifest_fingerprint != deployment_manifest_fingerprint:
            raise ValueError("voice_local_pipeline_input_lineage_manifest_mismatch")
        if vad.runtime_seal.deployment_manifest_fingerprint != deployment_manifest_fingerprint:
            raise ValueError("voice_local_pipeline_vad_manifest_mismatch")
        if stt.runtime_seal.deployment_manifest_fingerprint != deployment_manifest_fingerprint:
            raise ValueError("voice_local_pipeline_stt_manifest_mismatch")
        if not 1000 <= int(max_utterance_ms) <= 120_000:
            raise ValueError("voice_local_pipeline_utterance_limit_invalid")

        self.session_id = session_id
        self.language = language
        self.deployment_manifest_fingerprint = deployment_manifest_fingerprint
        self.input_lineage = input_lineage
        self.vad = vad
        self.stt = stt
        self.max_utterance_ms = int(max_utterance_ms)
        self.audio = VoiceAudioDataPlane(
            session_id=session_id,
            deployment_manifest_fingerprint=deployment_manifest_fingerprint,
            max_buffer_bytes=max_buffer_bytes,
        )
        self._wake: VoiceWakeInputProof | None = None
        self._latest_vad: VoiceVadExecutionResult | None = None
        self._speech_seen = False
        self._utterance_duration_ms = 0

    def wake(self) -> VoiceWakeInputProof:
        if self.audio.snapshot().buffered_frame_count:
            raise ValueError("voice_local_pipeline_wake_with_buffered_audio")
        self._wake = self.input_lineage.seal_wake()
        self._latest_vad = None
        self._speech_seen = False
        self._utterance_duration_ms = 0
        return self._wake

    def push_pcm(
        self,
        *,
        sequence: int,
        pcm: bytearray,
        duration_ms: int,
        sample_rate_hz: int = 16000,
    ) -> VoiceAudioBufferReceipt:
        if self._wake is None:
            raise ValueError("voice_local_pipeline_wake_required")
        projected = self._utterance_duration_ms + int(duration_ms)
        if projected > self.max_utterance_ms:
            self.audio.discard_all()
            self._utterance_duration_ms = 0
            self._speech_seen = False
            self._latest_vad = None
            raise ValueError("voice_local_pipeline_utterance_duration_exceeded")
        receipt = self.audio.push_owned_pcm(
            sequence=sequence,
            pcm=pcm,
            duration_ms=duration_ms,
            sample_rate_hz=sample_rate_hz,
        )
        self.input_lineage.seal_audio_frame(receipt.frame)
        self._utterance_duration_ms = projected
        return receipt

    def detect_speech(self, *, threshold: float = 0.5) -> VoiceVadExecutionResult:
        buffered = self.audio.snapshot().buffered_frame_count
        if buffered < 1:
            raise ValueError("voice_local_pipeline_audio_required")
        # Inspect the full current utterance. Concrete Silero execution is stateless
        # across callbacks so no raw recurrent audio/context escapes the RAM boundary.
        result = self.vad.detect(audio=self.audio, max_frames=buffered, threshold=threshold)
        self._latest_vad = result
        self._speech_seen = self._speech_seen or result.speech_detected
        return result

    def finalize_utterance(self) -> VoiceTransientUtterance:
        if self._wake is None:
            raise ValueError("voice_local_pipeline_wake_required")
        if self._latest_vad is None:
            raise ValueError("voice_local_pipeline_vad_required")
        if not self._speech_seen:
            raise ValueError("voice_local_pipeline_speech_not_detected")
        buffered = self.audio.snapshot().buffered_frame_count
        if buffered < 1:
            raise ValueError("voice_local_pipeline_audio_required")

        stt_result: VoiceTransientSttResult = self.stt.transcribe(
            audio=self.audio,
            max_frames=buffered,
            language=self.language,
        )
        input_proof: VoiceSttInputProof = self.input_lineage.seal_stt_final(text_sha256=stt_result.text_sha256)
        if input_proof.deployment_manifest_fingerprint != self.deployment_manifest_fingerprint:
            raise ValueError("voice_local_pipeline_final_manifest_mismatch")
        if input_proof.stt_identity_fingerprint != self.input_lineage.stt_identity_fingerprint:
            raise ValueError("voice_local_pipeline_stt_identity_drift")

        payload = {
            "session_id": self.session_id,
            "language": self.language,
            "deployment_manifest_fingerprint": self.deployment_manifest_fingerprint,
            "wake_proof_fingerprint": self._wake.fingerprint,
            "input_lineage_fingerprint": input_proof.fingerprint,
            "audio_chain_fingerprint": input_proof.audio_chain_fingerprint,
            "audio_frame_count": input_proof.audio_frame_count,
            "audio_duration_ms": input_proof.audio_duration_ms,
            "vad_result_fingerprint": self._latest_vad.fingerprint,
            "stt_result_fingerprint": stt_result.fingerprint,
            "stt_runtime_seal_fingerprint": stt_result.runtime_seal_fingerprint,
            "text_sha256": stt_result.text_sha256,
        }
        proof = VoiceLocalUtteranceProof(**payload, fingerprint=_sha256(payload))
        self._latest_vad = None
        self._speech_seen = False
        self._utterance_duration_ms = 0
        return VoiceTransientUtterance(text=stt_result.text, text_sha256=stt_result.text_sha256, proof=proof)

    def discard_utterance(self) -> None:
        self.audio.discard_all()
        self._latest_vad = None
        self._speech_seen = False
        self._utterance_duration_ms = 0
        # Reset the hash-chain under the same wake identity without storing audio.
        if self._wake is not None:
            self._wake = self.input_lineage.seal_wake()

    def close(self) -> None:
        self.audio.close()
