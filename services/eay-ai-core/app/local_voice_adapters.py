"""Concrete local-only speech adapters for Jarvis.

Adapters receive already-loaded local model objects. They never resolve model
IDs, URLs, tokens or remote assets and therefore cannot silently download model
weights at inference time. Deployment code owns model loading from an approved
local asset and supplies evidence refs.

Qwen3-ASR receives transient mono PCM converted to an in-memory float32 array.
Chatterbox Multilingual V3 receives text plus an explicit language id. Voice
cloning/reference audio is deliberately outside this adapter. Chatterbox models
may be recycled after a bounded number of generations via an injected local
builder to contain long-running backend resource drift without claiming an
upstream bug is fixed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .local_voice_runtime import (
    LocalAsrResult,
    LocalTtsResult,
    TransientAudioFrame,
    TransientSpeechAudio,
)

LOCAL_VOICE_ADAPTERS_CONTRACT = "eay-local-voice-adapters-v1"

_QWEN_LANGUAGE_NAMES = {
    "tr": "Turkish",
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
    "ja": "Japanese",
    "ko": "Korean",
    "zh": "Chinese",
}


def _pcm16_to_float32(audio: TransientAudioFrame):
    import numpy as np

    samples = np.frombuffer(audio.pcm16, dtype="<i2").astype(np.float32)
    return samples / 32768.0


def _extract_asr_text(output: Any) -> str:
    if output is None:
        raise RuntimeError("local_voice_qwen_asr_empty_output")
    first = output[0] if isinstance(output, (list, tuple)) else output
    if isinstance(first, dict):
        text = first.get("text")
    else:
        text = getattr(first, "text", None)
        if text is None and isinstance(first, str):
            text = first
    if not isinstance(text, str) or not text.strip():
        raise RuntimeError("local_voice_qwen_asr_text_missing")
    return text.strip()


class Qwen3AsrLocalBackend:
    """Adapter around an already-loaded Qwen3-ASR model object."""

    def __init__(self, *, model: Any, local_asset_evidence_ref: str) -> None:
        if model is None:
            raise ValueError("local_voice_qwen_asr_model_required")
        if not local_asset_evidence_ref.startswith("evidence://"):
            raise ValueError("local_voice_qwen_asr_local_asset_evidence_required")
        self._model = model
        self._asset_evidence_ref = local_asset_evidence_ref

    def transcribe(
        self,
        audio: TransientAudioFrame,
        *,
        language_code: str,
    ) -> tuple[str, LocalAsrResult]:
        language = _QWEN_LANGUAGE_NAMES.get(language_code.casefold())
        if language is None:
            raise ValueError("local_voice_qwen_asr_language_not_mapped")
        samples = _pcm16_to_float32(audio)
        output = self._model.transcribe(
            audio=(samples, audio.sample_rate_hz),
            language=language,
            return_time_stamps=False,
        )
        text = _extract_asr_text(output)
        confidence = getattr(output[0], "confidence", None) if isinstance(output, (list, tuple)) and output else None
        if not isinstance(confidence, (float, int)):
            confidence = 1.0
        return text, LocalAsrResult(
            language_code=language_code.casefold(),
            confidence=min(1.0, max(0.0, float(confidence))),
            final=audio.final_chunk,
            backend_evidence_ref=self._asset_evidence_ref,
        )


ChatterboxModelBuilder = Callable[[str], Any]


class ChatterboxMultilingualV3LocalBackend:
    """Turkish-capable local TTS adapter without voice-cloning input."""

    def __init__(
        self,
        *,
        model: Any,
        local_asset_ref: str,
        local_asset_evidence_ref: str,
        sample_rate_hz: int,
        model_builder: ChatterboxModelBuilder | None = None,
        max_generations_before_recycle: int = 100,
    ) -> None:
        if model is None:
            raise ValueError("local_voice_chatterbox_model_required")
        if not local_asset_ref.startswith("local-asset://"):
            raise ValueError("local_voice_chatterbox_local_asset_ref_required")
        if not local_asset_evidence_ref.startswith("evidence://"):
            raise ValueError("local_voice_chatterbox_local_asset_evidence_required")
        if sample_rate_hz <= 0:
            raise ValueError("local_voice_chatterbox_sample_rate_invalid")
        if max_generations_before_recycle < 1 or max_generations_before_recycle > 10000:
            raise ValueError("local_voice_chatterbox_recycle_threshold_invalid")
        self._model = model
        self._local_asset_ref = local_asset_ref
        self._asset_evidence_ref = local_asset_evidence_ref
        self._sample_rate_hz = sample_rate_hz
        self._builder = model_builder
        self._max_generations = max_generations_before_recycle
        self._generation_count = 0

    def _recycle_if_needed(self) -> None:
        if self._generation_count < self._max_generations:
            return
        if self._builder is None:
            raise RuntimeError("local_voice_chatterbox_recycle_required_but_builder_missing")
        replacement = self._builder(self._local_asset_ref)
        if replacement is None:
            raise RuntimeError("local_voice_chatterbox_recycle_builder_failed")
        self._model = replacement
        self._generation_count = 0

    @staticmethod
    def _waveform_to_pcm16(waveform: Any) -> bytes:
        import numpy as np

        value = waveform
        if hasattr(value, "detach"):
            value = value.detach()
        if hasattr(value, "cpu"):
            value = value.cpu()
        if hasattr(value, "numpy"):
            value = value.numpy()
        array = np.asarray(value, dtype=np.float32).reshape(-1)
        if array.size == 0 or not np.isfinite(array).all():
            raise RuntimeError("local_voice_chatterbox_waveform_invalid")
        array = np.clip(array, -1.0, 1.0)
        return (array * 32767.0).astype("<i2").tobytes()

    def synthesize(
        self,
        text: str,
        *,
        language_code: str,
    ) -> tuple[TransientSpeechAudio, LocalTtsResult]:
        if not text.strip():
            raise ValueError("local_voice_chatterbox_text_required")
        self._recycle_if_needed()
        # Deliberately no audio_prompt_path / voice-cloning reference.
        waveform = self._model.generate(text, language_id=language_code.casefold())
        self._generation_count += 1
        pcm16 = self._waveform_to_pcm16(waveform)
        return TransientSpeechAudio(
            pcm16=pcm16,
            sample_rate_hz=self._sample_rate_hz,
        ), LocalTtsResult(
            language_code=language_code.casefold(),
            backend_evidence_ref=self._asset_evidence_ref,
        )
