from datetime import datetime, timezone

import numpy as np
import pytest

from app.local_voice_adapters import (
    ChatterboxMultilingualV3LocalBackend,
    Qwen3AsrLocalBackend,
)
from app.local_voice_runtime import TransientAudioFrame

NOW = datetime(2026, 8, 18, 12, 40, tzinfo=timezone.utc)


class _AsrOutput:
    text = "Jarvis bunu sağ ekrana at"
    confidence = 0.96


class _QwenModel:
    def __init__(self):
        self.calls = []

    def transcribe(self, **kwargs):
        self.calls.append(kwargs)
        return [_AsrOutput()]


class _ChatterboxModel:
    def __init__(self, name="first"):
        self.name = name
        self.calls = []

    def generate(self, text, **kwargs):
        self.calls.append((text, kwargs))
        return np.asarray([0.0, 0.25, -0.25, 1.0, -1.0], dtype=np.float32)


def _audio():
    return TransientAudioFrame(
        pcm16=np.asarray([0, 16384, -16384], dtype="<i2").tobytes(),
        captured_at=NOW,
        sequence=1,
        final_chunk=True,
    )


def test_qwen_asr_receives_local_numpy_audio_and_canonical_turkish_language():
    model = _QwenModel()
    backend = Qwen3AsrLocalBackend(
        model=model,
        local_asset_evidence_ref="evidence://local-model/qwen3-asr/tr-v1",
    )
    text, result = backend.transcribe(_audio(), language_code="tr")
    assert text == "Jarvis bunu sağ ekrana at"
    assert result.language_code == "tr"
    assert result.final is True
    assert result.raw_audio_retained is False
    assert result.transcript_text_retained is False
    assert len(model.calls) == 1
    call = model.calls[0]
    samples, sample_rate = call["audio"]
    assert isinstance(samples, np.ndarray)
    assert samples.dtype == np.float32
    assert sample_rate == 16000
    assert call["language"] == "Turkish"
    assert call["return_time_stamps"] is False
    assert not any(isinstance(value, str) and value.startswith(("http://", "https://")) for value in call.values())


def test_qwen_asr_unmapped_language_fails_closed_before_model_call():
    model = _QwenModel()
    backend = Qwen3AsrLocalBackend(
        model=model,
        local_asset_evidence_ref="evidence://local-model/qwen3-asr/v1",
    )
    with pytest.raises(ValueError, match="language_not_mapped"):
        backend.transcribe(_audio(), language_code="xx")
    assert model.calls == []


def test_chatterbox_turkish_generation_never_passes_voice_clone_reference():
    model = _ChatterboxModel()
    backend = ChatterboxMultilingualV3LocalBackend(
        model=model,
        local_asset_ref="local-asset://models/chatterbox-v3",
        local_asset_evidence_ref="evidence://local-model/chatterbox/tr-v1",
        sample_rate_hz=24000,
    )
    audio, result = backend.synthesize("Merhaba Erdi", language_code="tr")
    assert result.language_code == "tr"
    assert result.input_text_retained is False
    assert result.generated_audio_retained is False
    assert audio.sample_rate_hz == 24000
    assert len(audio.pcm16) == 10
    text, kwargs = model.calls[0]
    assert text == "Merhaba Erdi"
    assert kwargs == {"language_id": "tr"}
    assert "audio_prompt_path" not in kwargs
    assert "voice" not in kwargs


def test_chatterbox_bounded_generation_recycles_only_through_local_asset_builder():
    first = _ChatterboxModel("first")
    second = _ChatterboxModel("second")
    builder_calls = []

    def builder(asset_ref):
        builder_calls.append(asset_ref)
        return second

    backend = ChatterboxMultilingualV3LocalBackend(
        model=first,
        local_asset_ref="local-asset://models/chatterbox-v3",
        local_asset_evidence_ref="evidence://local-model/chatterbox/tr-v1",
        sample_rate_hz=24000,
        model_builder=builder,
        max_generations_before_recycle=1,
    )
    backend.synthesize("Bir", language_code="tr")
    backend.synthesize("İki", language_code="tr")
    assert len(first.calls) == 1
    assert len(second.calls) == 1
    assert builder_calls == ["local-asset://models/chatterbox-v3"]


def test_chatterbox_recycle_without_builder_fails_closed_instead_of_unbounded_reuse():
    backend = ChatterboxMultilingualV3LocalBackend(
        model=_ChatterboxModel(),
        local_asset_ref="local-asset://models/chatterbox-v3",
        local_asset_evidence_ref="evidence://local-model/chatterbox/tr-v1",
        sample_rate_hz=24000,
        max_generations_before_recycle=1,
    )
    backend.synthesize("Bir", language_code="tr")
    with pytest.raises(RuntimeError, match="recycle_required_but_builder_missing"):
        backend.synthesize("İki", language_code="tr")
