from __future__ import annotations

import ctypes
from array import array
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol

from .voice_audio_dataplane import EphemeralPcmFrameView
from .voice_runtime import CORE_LANGUAGES
from .voice_runtime_attestation import VoiceRuntimeArtifactSeal, hash_regular_file


def _require_exact_artifact(path: Path, expected_sha256: str, *, code: str) -> None:
    digest, _ = hash_regular_file(Path(path))
    if digest != expected_sha256:
        raise ValueError(code)


def _require_16k_pcm(frames: tuple[EphemeralPcmFrameView, ...]) -> None:
    if not frames:
        raise ValueError("voice_native_audio_frames_required")
    if any(frame.sample_rate_hz != 16000 for frame in frames):
        raise ValueError("voice_native_audio_16khz_required")


class SileroOnnxVadEngine:
    """Concrete, fileless-audio Silero VAD ONNX engine.

    The ONNX model bytes are re-hashed before the session is created. Audio is passed
    to ONNX Runtime from RAM; this class never writes WAV/PCM files. To avoid retaining
    raw audio between callbacks, recurrent state and context are recreated per score()
    call and the caller must supply complete 512-sample (32 ms @ 16 kHz) windows.
    """

    REQUIRED_INPUTS = frozenset({"input", "state", "sr"})

    def __init__(
        self,
        *,
        runtime_seal: VoiceRuntimeArtifactSeal,
        model_path: Path,
        session_factory: Callable[[str], Any] | None = None,
        numpy_module: Any | None = None,
    ) -> None:
        runtime_seal.validate()
        if runtime_seal.kind != "vad" or runtime_seal.implementation != "silero-vad-onnx":
            raise ValueError("voice_silero_runtime_contract_mismatch")
        _require_exact_artifact(
            Path(model_path),
            runtime_seal.model_or_voice_artifact_sha256,
            code="voice_silero_model_artifact_hash_mismatch",
        )
        self.runtime_seal = runtime_seal
        self.model_path = Path(model_path)

        if numpy_module is None:
            try:
                import numpy as np  # type: ignore
            except ImportError as exc:  # pragma: no cover - deployment dependency path
                raise RuntimeError("voice_silero_numpy_dependency_missing") from exc
            numpy_module = np
        self.np = numpy_module

        if session_factory is None:
            try:
                import onnxruntime as ort  # type: ignore
            except ImportError as exc:  # pragma: no cover - deployment dependency path
                raise RuntimeError("voice_silero_onnxruntime_dependency_missing") from exc

            def _factory(path: str):
                options = ort.SessionOptions()
                options.inter_op_num_threads = 1
                options.intra_op_num_threads = 1
                providers = set(ort.get_available_providers())
                if "CPUExecutionProvider" not in providers:
                    raise RuntimeError("voice_silero_cpu_provider_required")
                return ort.InferenceSession(path, providers=["CPUExecutionProvider"], sess_options=options)

            session_factory = _factory

        self.session = session_factory(str(self.model_path))
        input_names = {item.name for item in self.session.get_inputs()}
        if not self.REQUIRED_INPUTS.issubset(input_names):
            raise ValueError("voice_silero_onnx_input_contract_drift")
        if len(self.session.get_outputs()) < 2:
            raise ValueError("voice_silero_onnx_output_contract_drift")

    def score(self, *, frames: tuple[EphemeralPcmFrameView, ...]) -> float:
        _require_16k_pcm(frames)
        np = self.np
        pcm_parts = [np.frombuffer(frame.pcm, dtype="<i2") for frame in frames]
        sample_count = sum(int(part.size) for part in pcm_parts)
        if sample_count < 512 or sample_count % 512 != 0:
            raise ValueError("voice_silero_512_sample_window_required")

        samples = np.concatenate(pcm_parts).astype(np.float32, copy=False) / np.float32(32768.0)
        state = np.zeros((2, 1, 128), dtype=np.float32)
        context = np.zeros((1, 64), dtype=np.float32)
        probabilities: list[float] = []
        try:
            for offset in range(0, sample_count, 512):
                chunk = samples[offset : offset + 512].reshape(1, 512)
                model_input = np.concatenate((context, chunk), axis=1).astype(np.float32, copy=False)
                outputs = self.session.run(
                    None,
                    {
                        "input": model_input,
                        "state": state,
                        "sr": np.array(16000, dtype=np.int64),
                    },
                )
                if len(outputs) < 2:
                    raise ValueError("voice_silero_onnx_output_contract_drift")
                probability_raw, next_state = outputs[0], outputs[1]
                flattened = np.asarray(probability_raw).reshape(-1)
                if flattened.size < 1:
                    raise ValueError("voice_silero_probability_missing")
                probability = float(flattened[-1])
                if probability < 0.0 or probability > 1.0:
                    raise ValueError("voice_silero_probability_invalid")
                probabilities.append(probability)
                state = np.asarray(next_state, dtype=np.float32)
                if state.shape != (2, 1, 128):
                    raise ValueError("voice_silero_state_contract_drift")
                context = model_input[:, -64:].copy()
            return max(probabilities)
        finally:
            # Best effort for application-owned NumPy buffers. This is not a claim
            # that ORT/OS/internal allocator copies can be erased by Python.
            try:
                samples.fill(0)
                state.fill(0)
                context.fill(0)
            except Exception:
                pass


class WhisperShim(Protocol):
    def abi_version(self) -> int: ...
    def create(self, *, model_path: Path, threads: int) -> Any: ...
    def transcribe_pcm16(self, *, handle: Any, pcm: memoryview, language: str) -> str: ...
    def destroy(self, handle: Any) -> None: ...


class _CtypesWhisperShim:
    ABI_VERSION = 1

    def __init__(self, library_path: Path) -> None:
        self.lib = ctypes.CDLL(str(library_path))
        self.lib.eay_whisper_shim_abi_version.argtypes = []
        self.lib.eay_whisper_shim_abi_version.restype = ctypes.c_int
        self.lib.eay_whisper_create.argtypes = [ctypes.c_char_p, ctypes.c_int]
        self.lib.eay_whisper_create.restype = ctypes.c_void_p
        self.lib.eay_whisper_transcribe_pcm16.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_int16),
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self.lib.eay_whisper_transcribe_pcm16.restype = ctypes.c_int
        self.lib.eay_whisper_destroy.argtypes = [ctypes.c_void_p]
        self.lib.eay_whisper_destroy.restype = None
        if self.abi_version() != self.ABI_VERSION:
            raise ValueError("voice_whisper_shim_abi_mismatch")

    def abi_version(self) -> int:
        return int(self.lib.eay_whisper_shim_abi_version())

    def create(self, *, model_path: Path, threads: int) -> Any:
        handle = self.lib.eay_whisper_create(str(model_path).encode("utf-8"), int(threads))
        if not handle:
            raise RuntimeError("voice_whisper_context_create_failed")
        return handle

    def transcribe_pcm16(self, *, handle: Any, pcm: memoryview, language: str) -> str:
        if pcm.nbytes % 2:
            raise ValueError("voice_whisper_pcm16_alignment_invalid")
        raw = pcm.cast("B")
        sample_count = raw.nbytes // 2
        pcm_array = (ctypes.c_int16 * sample_count).from_buffer_copy(raw)
        output = ctypes.create_string_buffer(32768)
        try:
            code = int(
                self.lib.eay_whisper_transcribe_pcm16(
                    handle,
                    pcm_array,
                    sample_count,
                    language.encode("ascii"),
                    output,
                    len(output),
                )
            )
            if code != 0:
                raise RuntimeError(f"voice_whisper_inference_failed:{code}")
            return output.value.decode("utf-8", errors="strict")
        finally:
            ctypes.memset(ctypes.addressof(pcm_array), 0, ctypes.sizeof(pcm_array))
            ctypes.memset(ctypes.addressof(output), 0, ctypes.sizeof(output))

    def destroy(self, handle: Any) -> None:
        if handle:
            self.lib.eay_whisper_destroy(handle)


@dataclass
class WhisperCppSttEngine:
    """In-memory PCM16 whisper.cpp STT backed by the EAY stable C ABI shim."""

    runtime_seal: VoiceRuntimeArtifactSeal
    model_path: Path
    shim: WhisperShim
    threads: int = 4

    def __post_init__(self) -> None:
        self.runtime_seal.validate()
        if self.runtime_seal.kind != "stt" or self.runtime_seal.implementation != "whisper.cpp":
            raise ValueError("voice_whisper_runtime_contract_mismatch")
        if not 1 <= int(self.threads) <= 64:
            raise ValueError("voice_whisper_thread_count_invalid")
        _require_exact_artifact(
            Path(self.model_path),
            self.runtime_seal.model_or_voice_artifact_sha256,
            code="voice_whisper_model_artifact_hash_mismatch",
        )
        if int(self.shim.abi_version()) != 1:
            raise ValueError("voice_whisper_shim_abi_mismatch")
        self._handle = self.shim.create(model_path=Path(self.model_path), threads=int(self.threads))
        self._closed = False

    @classmethod
    def from_local_artifacts(
        cls,
        *,
        runtime_seal: VoiceRuntimeArtifactSeal,
        model_path: Path,
        shim_library_path: Path,
        threads: int = 4,
    ) -> "WhisperCppSttEngine":
        runtime_seal.validate()
        _require_exact_artifact(
            Path(shim_library_path),
            runtime_seal.runtime_artifact_sha256,
            code="voice_whisper_runtime_artifact_hash_mismatch",
        )
        return cls(
            runtime_seal=runtime_seal,
            model_path=Path(model_path),
            shim=_CtypesWhisperShim(Path(shim_library_path)),
            threads=threads,
        )

    def transcribe(self, *, frames: tuple[EphemeralPcmFrameView, ...], language: str) -> str:
        if self._closed:
            raise ValueError("voice_whisper_engine_closed")
        language = language.strip().lower()
        if language not in CORE_LANGUAGES:
            raise ValueError("voice_whisper_language_not_enabled")
        _require_16k_pcm(frames)
        total_bytes = sum(frame.pcm.nbytes for frame in frames)
        if total_bytes <= 0 or total_bytes > 16_000 * 2 * 120:
            raise ValueError("voice_whisper_audio_window_invalid")

        owned = bytearray(total_bytes)
        cursor = 0
        try:
            for frame in frames:
                raw = frame.pcm.cast("B")
                owned[cursor : cursor + raw.nbytes] = raw
                cursor += raw.nbytes
            text = self.shim.transcribe_pcm16(handle=self._handle, pcm=memoryview(owned).toreadonly(), language=language)
            return " ".join(str(text).strip().split())
        finally:
            owned[:] = b"\x00" * len(owned)

    def close(self) -> None:
        if self._closed:
            return
        self.shim.destroy(self._handle)
        self._handle = None
        self._closed = True

    def __enter__(self) -> "WhisperCppSttEngine":
        if self._closed:
            raise ValueError("voice_whisper_engine_closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
