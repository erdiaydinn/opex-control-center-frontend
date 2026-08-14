from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from typing import Protocol

from .voice_audio_dataplane import EphemeralPcmFrameView, VoiceAudioDataPlane
from .voice_runtime import CORE_LANGUAGES
from .voice_runtime_attestation import VoiceRuntimeArtifactSeal


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _audio_input_fingerprint(
    *,
    frames: tuple[EphemeralPcmFrameView, ...],
    runtime_seal_fingerprint: str,
    deployment_manifest_fingerprint: str,
) -> str:
    return _sha256(
        {
            "runtime_seal_fingerprint": runtime_seal_fingerprint,
            "deployment_manifest_fingerprint": deployment_manifest_fingerprint,
            "frames": [
                {
                    "sequence": frame.sequence,
                    "pcm_sha256": frame.pcm_sha256,
                    "duration_ms": frame.duration_ms,
                    "sample_rate_hz": frame.sample_rate_hz,
                }
                for frame in frames
            ],
        }
    )


class InMemoryVadEngine(Protocol):
    def score(self, *, frames: tuple[EphemeralPcmFrameView, ...]) -> float: ...


class InMemorySttEngine(Protocol):
    def transcribe(self, *, frames: tuple[EphemeralPcmFrameView, ...], language: str) -> str: ...


@dataclass(frozen=True)
class VoiceVadExecutionResult:
    speech_probability: float
    speech_detected: bool
    threshold: float
    input_audio_fingerprint: str
    runtime_seal_fingerprint: str
    deployment_manifest_fingerprint: str
    fingerprint: str


@dataclass(frozen=True)
class VoiceTransientSttResult:
    """Transient STT result; only ``text_sha256`` belongs in audit/provenance stores."""

    text: str
    text_sha256: str
    language: str
    input_audio_fingerprint: str
    runtime_seal_fingerprint: str
    deployment_manifest_fingerprint: str
    fingerprint: str


class PinnedLocalVadAdapter:
    def __init__(self, *, runtime_seal: VoiceRuntimeArtifactSeal, engine: InMemoryVadEngine) -> None:
        runtime_seal.validate()
        if runtime_seal.kind != "vad":
            raise ValueError("voice_local_vad_runtime_kind_mismatch")
        self.runtime_seal = runtime_seal
        self.engine = engine

    def detect(
        self,
        *,
        audio: VoiceAudioDataPlane,
        max_frames: int,
        threshold: float = 0.5,
    ) -> VoiceVadExecutionResult:
        if audio.deployment_manifest_fingerprint != self.runtime_seal.deployment_manifest_fingerprint:
            raise ValueError("voice_local_vad_deployment_manifest_mismatch")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("voice_local_vad_threshold_invalid")

        def _run(frames: tuple[EphemeralPcmFrameView, ...]) -> VoiceVadExecutionResult:
            input_fp = _audio_input_fingerprint(
                frames=frames,
                runtime_seal_fingerprint=self.runtime_seal.fingerprint,
                deployment_manifest_fingerprint=audio.deployment_manifest_fingerprint,
            )
            score = float(self.engine.score(frames=frames))
            if not math.isfinite(score) or not 0.0 <= score <= 1.0:
                raise ValueError("voice_local_vad_score_invalid")
            payload = {
                "speech_probability": score,
                "speech_detected": score >= threshold,
                "threshold": threshold,
                "input_audio_fingerprint": input_fp,
                "runtime_seal_fingerprint": self.runtime_seal.fingerprint,
                "deployment_manifest_fingerprint": audio.deployment_manifest_fingerprint,
            }
            return VoiceVadExecutionResult(**payload, fingerprint=_sha256(payload))

        # VAD inspects without consuming: the same utterance audio must remain available
        # to STT. STT is the one-shot consumer that wipes accepted PCM afterward.
        return audio.inspect_next(max_frames=max_frames, processor=_run)


class PinnedLocalSttAdapter:
    def __init__(self, *, runtime_seal: VoiceRuntimeArtifactSeal, engine: InMemorySttEngine) -> None:
        runtime_seal.validate()
        if runtime_seal.kind != "stt":
            raise ValueError("voice_local_stt_runtime_kind_mismatch")
        self.runtime_seal = runtime_seal
        self.engine = engine

    def transcribe(
        self,
        *,
        audio: VoiceAudioDataPlane,
        max_frames: int,
        language: str,
    ) -> VoiceTransientSttResult:
        language = language.strip().lower()
        if language not in CORE_LANGUAGES:
            raise ValueError("voice_local_stt_language_not_enabled")
        if audio.deployment_manifest_fingerprint != self.runtime_seal.deployment_manifest_fingerprint:
            raise ValueError("voice_local_stt_deployment_manifest_mismatch")

        def _run(frames: tuple[EphemeralPcmFrameView, ...]) -> VoiceTransientSttResult:
            input_fp = _audio_input_fingerprint(
                frames=frames,
                runtime_seal_fingerprint=self.runtime_seal.fingerprint,
                deployment_manifest_fingerprint=audio.deployment_manifest_fingerprint,
            )
            text = " ".join(str(self.engine.transcribe(frames=frames, language=language)).strip().split())
            if not text:
                raise ValueError("voice_local_stt_empty_transcript")
            text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
            payload = {
                "text_sha256": text_sha,
                "language": language,
                "input_audio_fingerprint": input_fp,
                "runtime_seal_fingerprint": self.runtime_seal.fingerprint,
                "deployment_manifest_fingerprint": audio.deployment_manifest_fingerprint,
            }
            return VoiceTransientSttResult(text=text, **payload, fingerprint=_sha256(payload))

        return audio.process_next(max_frames=max_frames, processor=_run)
