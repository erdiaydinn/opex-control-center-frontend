import hashlib
from pathlib import Path

import numpy as np
import pytest

from app.voice_audio_dataplane import EphemeralPcmFrameView
from app.voice_native_engines import SileroOnnxVadEngine, WhisperCppSttEngine
from app.voice_runtime_attestation import VoiceRuntimeArtifactSeal


def _hash(ch: str) -> str:
    return ch * 64


def _seal(*, kind: str, implementation: str, model_sha: str, runtime_sha: str = "a" * 64) -> VoiceRuntimeArtifactSeal:
    return VoiceRuntimeArtifactSeal(
        candidate_id="silero-vad-onnx" if kind == "vad" else "whisper-cpp-openai-whisper",
        adapter_id=f"{kind}-prod-v1",
        kind=kind,
        implementation=implementation,
        runtime_license_id="mit",
        artifact_license_id="mit",
        runtime_artifact_sha256=runtime_sha,
        runtime_artifact_size_bytes=100,
        model_or_voice_artifact_sha256=model_sha,
        adapter_fingerprint=_hash("b"),
        promotion_fingerprint=_hash("c"),
        deployment_manifest_fingerprint=_hash("d"),
        fingerprint=_hash("e"),
    )


def _pcm_frame(*, sequence: int = 0, samples: int = 512, fill: int = 1000) -> EphemeralPcmFrameView:
    pcm = np.full(samples, fill, dtype="<i2").tobytes()
    return EphemeralPcmFrameView(
        sequence=sequence,
        pcm=memoryview(pcm),
        pcm_sha256=hashlib.sha256(pcm).hexdigest(),
        duration_ms=32,
        sample_rate_hz=16000,
    )


class _Io:
    def __init__(self, name):
        self.name = name


class _FakeSileroSession:
    def __init__(self):
        self.calls = 0

    def get_inputs(self):
        return [_Io("input"), _Io("state"), _Io("sr")]

    def get_outputs(self):
        return [_Io("output"), _Io("stateN")]

    def run(self, _, inputs):
        self.calls += 1
        assert inputs["input"].shape == (1, 576)
        assert inputs["state"].shape == (2, 1, 128)
        assert int(inputs["sr"]) == 16000
        probability = np.array([[0.2 if self.calls == 1 else 0.91]], dtype=np.float32)
        state = np.ones((2, 1, 128), dtype=np.float32) * self.calls
        return [probability, state]


def test_silero_onnx_engine_scores_exact_512_sample_windows_without_file_audio(tmp_path):
    model = tmp_path / "silero.onnx"
    model.write_bytes(b"pinned-silero-model")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    session = _FakeSileroSession()
    engine = SileroOnnxVadEngine(
        runtime_seal=_seal(kind="vad", implementation="silero-vad-onnx", model_sha=model_sha),
        model_path=model,
        session_factory=lambda _: session,
        numpy_module=np,
    )

    score = engine.score(frames=(_pcm_frame(sequence=0), _pcm_frame(sequence=1)))

    assert score == pytest.approx(0.91)
    assert session.calls == 2


def test_silero_engine_rejects_non_window_audio_and_model_drift(tmp_path):
    model = tmp_path / "silero.onnx"
    model.write_bytes(b"current-model")
    actual_sha = hashlib.sha256(model.read_bytes()).hexdigest()

    with pytest.raises(ValueError, match="voice_silero_model_artifact_hash_mismatch"):
        SileroOnnxVadEngine(
            runtime_seal=_seal(kind="vad", implementation="silero-vad-onnx", model_sha=_hash("1")),
            model_path=model,
            session_factory=lambda _: _FakeSileroSession(),
            numpy_module=np,
        )

    engine = SileroOnnxVadEngine(
        runtime_seal=_seal(kind="vad", implementation="silero-vad-onnx", model_sha=actual_sha),
        model_path=model,
        session_factory=lambda _: _FakeSileroSession(),
        numpy_module=np,
    )
    with pytest.raises(ValueError, match="voice_silero_512_sample_window_required"):
        engine.score(frames=(_pcm_frame(samples=320),))


class _FakeWhisperShim:
    def __init__(self):
        self.destroyed = False
        self.last_language = None
        self.last_pcm_bytes = 0

    def abi_version(self):
        return 1

    def create(self, *, model_path: Path, threads: int):
        assert model_path.exists()
        assert threads == 3
        return object()

    def transcribe_pcm16(self, *, handle, pcm: memoryview, language: str):
        assert handle is not None
        self.last_language = language
        self.last_pcm_bytes = pcm.nbytes
        return "  Depo   performansı iyi. "

    def destroy(self, handle):
        assert handle is not None
        self.destroyed = True


def test_whisper_cpp_engine_transcribes_ram_pcm_through_stable_shim(tmp_path):
    model = tmp_path / "ggml-model.bin"
    model.write_bytes(b"pinned-whisper-model")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    shim = _FakeWhisperShim()
    engine = WhisperCppSttEngine(
        runtime_seal=_seal(kind="stt", implementation="whisper.cpp", model_sha=model_sha),
        model_path=model,
        shim=shim,
        threads=3,
    )

    text = engine.transcribe(frames=(_pcm_frame(),), language="tr")

    assert text == "Depo performansı iyi."
    assert shim.last_language == "tr"
    assert shim.last_pcm_bytes == 1024
    engine.close()
    assert shim.destroyed is True
    with pytest.raises(ValueError, match="voice_whisper_engine_closed"):
        engine.transcribe(frames=(_pcm_frame(),), language="tr")


def test_whisper_loader_rejects_runtime_or_model_hash_drift_before_execution(tmp_path):
    model = tmp_path / "ggml-model.bin"
    model.write_bytes(b"whisper-model")
    model_sha = hashlib.sha256(model.read_bytes()).hexdigest()
    shim_library = tmp_path / "eay-whisper-shim.so"
    shim_library.write_bytes(b"not-the-attested-runtime")

    with pytest.raises(ValueError, match="voice_whisper_runtime_artifact_hash_mismatch"):
        WhisperCppSttEngine.from_local_artifacts(
            runtime_seal=_seal(
                kind="stt",
                implementation="whisper.cpp",
                model_sha=model_sha,
                runtime_sha=_hash("9"),
            ),
            model_path=model,
            shim_library_path=shim_library,
        )
