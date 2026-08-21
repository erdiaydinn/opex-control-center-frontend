from __future__ import annotations

import ctypes
import hashlib
import json
import math
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Protocol

from .voice_response_lineage import VoiceTtsGenerationProof
from .voice_runtime_attestation import VoiceRuntimeArtifactSeal, hash_regular_file, seal_runtime_directory_manifest
from .voice_tts_bundle import VoiceTtsBundleExecutionIdentity


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _require_exact_file(path: Path, expected_sha256: str, *, code: str) -> None:
    digest, _ = hash_regular_file(Path(path))
    if digest != expected_sha256:
        raise ValueError(code)


class CancellationCheckpoint(Protocol):
    def checkpoint(self) -> None: ...


class SherpaStreamingShim(Protocol):
    def abi_version(self) -> int: ...

    def create(
        self,
        *,
        model_path: Path,
        tokens_path: Path,
        phonemizer_data_dir: Path,
        num_threads: int,
        max_num_sentences: int,
    ) -> object: ...

    def sample_rate(self, handle: object) -> int: ...

    def generate(
        self,
        *,
        handle: object,
        text: str,
        sid: int,
        speed: float,
        silence_scale: float,
        on_chunk: Callable[[tuple[float, ...], float], bool],
    ) -> int: ...

    def destroy(self, handle: object) -> None: ...


class _CtypesSherpaStreamingShim:
    ABI_VERSION = 1

    def __init__(self, library_path: Path) -> None:
        self.lib = ctypes.CDLL(str(library_path))
        self._callback_type = ctypes.CFUNCTYPE(
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_float),
            ctypes.c_int32,
            ctypes.c_float,
            ctypes.c_void_p,
        )
        self.lib.eay_sherpa_tts_shim_abi_version.argtypes = []
        self.lib.eay_sherpa_tts_shim_abi_version.restype = ctypes.c_int32
        self.lib.eay_sherpa_tts_create_vits.argtypes = [
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_char_p,
            ctypes.c_int32,
            ctypes.c_int32,
        ]
        self.lib.eay_sherpa_tts_create_vits.restype = ctypes.c_void_p
        self.lib.eay_sherpa_tts_sample_rate.argtypes = [ctypes.c_void_p]
        self.lib.eay_sherpa_tts_sample_rate.restype = ctypes.c_int32
        self.lib.eay_sherpa_tts_generate.argtypes = [
            ctypes.c_void_p,
            ctypes.c_char_p,
            ctypes.c_int32,
            ctypes.c_float,
            ctypes.c_float,
            self._callback_type,
            ctypes.c_void_p,
        ]
        self.lib.eay_sherpa_tts_generate.restype = ctypes.c_int32
        self.lib.eay_sherpa_tts_destroy.argtypes = [ctypes.c_void_p]
        self.lib.eay_sherpa_tts_destroy.restype = None
        if self.abi_version() != self.ABI_VERSION:
            raise ValueError("voice_sherpa_tts_shim_abi_mismatch")

    def abi_version(self) -> int:
        return int(self.lib.eay_sherpa_tts_shim_abi_version())

    def create(
        self,
        *,
        model_path: Path,
        tokens_path: Path,
        phonemizer_data_dir: Path,
        num_threads: int,
        max_num_sentences: int,
    ) -> object:
        handle = self.lib.eay_sherpa_tts_create_vits(
            str(model_path).encode("utf-8"),
            str(tokens_path).encode("utf-8"),
            str(phonemizer_data_dir).encode("utf-8"),
            int(num_threads),
            int(max_num_sentences),
        )
        if not handle:
            raise RuntimeError("voice_sherpa_tts_context_create_failed")
        return handle

    def sample_rate(self, handle: object) -> int:
        return int(self.lib.eay_sherpa_tts_sample_rate(handle))

    def generate(
        self,
        *,
        handle: object,
        text: str,
        sid: int,
        speed: float,
        silence_scale: float,
        on_chunk: Callable[[tuple[float, ...], float], bool],
    ) -> int:
        callback_error: list[BaseException] = []

        @self._callback_type
        def _callback(samples, n, progress, _opaque):
            try:
                if not samples or int(n) <= 0:
                    return 0
                copied = tuple(float(samples[index]) for index in range(int(n)))
                return 1 if on_chunk(copied, float(progress)) else 0
            except BaseException as exc:  # never unwind Python through the C ABI
                callback_error.append(exc)
                return 0

        status = int(
            self.lib.eay_sherpa_tts_generate(
                handle,
                text.encode("utf-8"),
                int(sid),
                float(speed),
                float(silence_scale),
                _callback,
                None,
            )
        )
        if callback_error:
            raise RuntimeError("voice_sherpa_tts_callback_failed") from callback_error[0]
        return status

    def destroy(self, handle: object) -> None:
        if handle:
            self.lib.eay_sherpa_tts_destroy(handle)


@dataclass
class EphemeralTtsPcmChunk:
    sequence: int
    sample_rate_hz: int
    sample_count: int
    pcm_sha256: str
    progress: float
    tts_proof_fingerprint: str
    fingerprint: str
    _pcm: bytearray
    _closed: bool = False

    @property
    def closed(self) -> bool:
        return self._closed

    def view(self) -> memoryview:
        if self._closed:
            raise ValueError("voice_tts_stream_chunk_closed")
        return memoryview(self._pcm).toreadonly()

    def close(self) -> None:
        if self._closed:
            return
        self._pcm[:] = b"\x00" * len(self._pcm)
        self._closed = True


@dataclass(frozen=True)
class VoiceTtsStreamingResult:
    language: str
    sample_rate_hz: int
    chunk_count: int
    sample_count: int
    first_audio_latency_ms: float
    generation_duration_ms: float
    audio_duration_ms: float
    real_time_factor: float
    audio_chain_fingerprint: str
    tts_proof_fingerprint: str
    fingerprint: str


class SherpaOnnxStreamingVitsTtsEngine:
    """Interruptible TTS using EAY's stable shim over sherpa's progress callback API.

    Each native chunk is copied immediately into EAY-owned PCM16, synchronously handed
    to the consumer, then zeroized before native generation continues. Returning False
    from the consumer or tripping the cancellation checkpoint returns 0 to sherpa's
    callback, causing native generation to stop rather than merely discarding a late
    whole-utterance result.
    """

    def __init__(
        self,
        *,
        runtime_seal: VoiceRuntimeArtifactSeal,
        bundle_identity: VoiceTtsBundleExecutionIdentity,
        language: str,
        model_path: Path,
        config_path: Path,
        tokens_path: Path,
        model_card_path: Path,
        phonemizer_data_dir: Path,
        shim: SherpaStreamingShim,
        num_threads: int = 2,
        max_num_sentences: int = 1,
    ) -> None:
        runtime_seal.validate()
        bundle_identity.validate()
        if runtime_seal.kind != "tts" or runtime_seal.implementation != "sherpa-onnx-vits":
            raise ValueError("voice_sherpa_stream_runtime_contract_mismatch")
        if runtime_seal.adapter_id != bundle_identity.runtime_adapter_id:
            raise ValueError("voice_sherpa_stream_runtime_adapter_mismatch")
        if runtime_seal.promotion_fingerprint != bundle_identity.runtime_adapter_promotion_fingerprint:
            raise ValueError("voice_sherpa_stream_runtime_promotion_mismatch")
        if int(shim.abi_version()) != 1:
            raise ValueError("voice_sherpa_tts_shim_abi_mismatch")
        if not 1 <= int(num_threads) <= 64:
            raise ValueError("voice_sherpa_stream_thread_count_invalid")
        if not 1 <= int(max_num_sentences) <= 128:
            raise ValueError("voice_sherpa_stream_sentence_limit_invalid")

        self.runtime_seal = runtime_seal
        self.bundle_identity = bundle_identity
        self.language_identity = bundle_identity.artifact_for(language)
        self.language = self.language_identity.language
        self.model_path = Path(model_path)
        self.config_path = Path(config_path)
        self.tokens_path = Path(tokens_path)
        self.model_card_path = Path(model_card_path)
        self.phonemizer_data_dir = Path(phonemizer_data_dir)
        self.shim = shim
        self.num_threads = int(num_threads)
        self.max_num_sentences = int(max_num_sentences)

        _require_exact_file(self.model_path, self.language_identity.model_sha256, code="voice_sherpa_stream_model_hash_mismatch")
        _require_exact_file(self.config_path, self.language_identity.config_sha256, code="voice_sherpa_stream_config_hash_mismatch")
        _require_exact_file(self.tokens_path, self.language_identity.tokens_sha256, code="voice_sherpa_stream_tokens_hash_mismatch")
        _require_exact_file(self.model_card_path, self.language_identity.model_card_sha256, code="voice_sherpa_stream_model_card_hash_mismatch")
        resource_manifest = seal_runtime_directory_manifest(self.phonemizer_data_dir, logical_name="espeak-ng-data")
        if resource_manifest.fingerprint != bundle_identity.phonemizer_data_manifest_fingerprint:
            raise ValueError("voice_sherpa_stream_phonemizer_manifest_mismatch")
        self.phonemizer_manifest_fingerprint = resource_manifest.fingerprint

        self._handle = self.shim.create(
            model_path=self.model_path,
            tokens_path=self.tokens_path,
            phonemizer_data_dir=self.phonemizer_data_dir,
            num_threads=self.num_threads,
            max_num_sentences=self.max_num_sentences,
        )
        self.sample_rate_hz = int(self.shim.sample_rate(self._handle))
        if not 8_000 <= self.sample_rate_hz <= 96_000:
            self.shim.destroy(self._handle)
            self._handle = None
            raise ValueError("voice_sherpa_stream_sample_rate_invalid")
        self._closed = False

    @classmethod
    def from_local_artifacts(
        cls,
        *,
        runtime_seal: VoiceRuntimeArtifactSeal,
        bundle_identity: VoiceTtsBundleExecutionIdentity,
        language: str,
        model_path: Path,
        config_path: Path,
        tokens_path: Path,
        model_card_path: Path,
        phonemizer_data_dir: Path,
        shim_library_path: Path,
        num_threads: int = 2,
        max_num_sentences: int = 1,
    ) -> "SherpaOnnxStreamingVitsTtsEngine":
        runtime_seal.validate()
        _require_exact_file(
            Path(shim_library_path),
            runtime_seal.runtime_artifact_sha256,
            code="voice_sherpa_stream_runtime_artifact_hash_mismatch",
        )
        return cls(
            runtime_seal=runtime_seal,
            bundle_identity=bundle_identity,
            language=language,
            model_path=model_path,
            config_path=config_path,
            tokens_path=tokens_path,
            model_card_path=model_card_path,
            phonemizer_data_dir=phonemizer_data_dir,
            shim=_CtypesSherpaStreamingShim(Path(shim_library_path)),
            num_threads=num_threads,
            max_num_sentences=max_num_sentences,
        )

    def _validate_proof(self, proof: VoiceTtsGenerationProof) -> None:
        proof.validate()
        if proof.language != self.language:
            raise ValueError("voice_sherpa_stream_proof_language_mismatch")
        if proof.deployment_manifest_fingerprint != self.runtime_seal.deployment_manifest_fingerprint:
            raise ValueError("voice_sherpa_stream_deployment_manifest_mismatch")
        if proof.tts_bundle_execution_identity_fingerprint != self.bundle_identity.fingerprint:
            raise ValueError("voice_sherpa_stream_bundle_identity_mismatch")
        if proof.tts_adapter_promotion_fingerprint != self.runtime_seal.promotion_fingerprint:
            raise ValueError("voice_sherpa_stream_promotion_mismatch")
        checks = (
            (proof.tts_language_artifact_fingerprint, self.language_identity.fingerprint, "voice_sherpa_stream_language_artifact_mismatch"),
            (proof.tts_voice_model_sha256, self.language_identity.model_sha256, "voice_sherpa_stream_model_proof_mismatch"),
            (proof.tts_voice_config_sha256, self.language_identity.config_sha256, "voice_sherpa_stream_config_proof_mismatch"),
            (proof.tts_voice_tokens_sha256, self.language_identity.tokens_sha256, "voice_sherpa_stream_tokens_proof_mismatch"),
            (proof.tts_voice_model_card_sha256, self.language_identity.model_card_sha256, "voice_sherpa_stream_model_card_proof_mismatch"),
            (proof.tts_voice_license_id_sha256, self.language_identity.artifact_license_id_sha256, "voice_sherpa_stream_license_proof_mismatch"),
            (proof.tts_phonemizer_data_manifest_fingerprint, self.bundle_identity.phonemizer_data_manifest_fingerprint, "voice_sherpa_stream_phonemizer_proof_mismatch"),
            (proof.tts_phonemizer_license_id_sha256, self.bundle_identity.phonemizer_license_id_sha256, "voice_sherpa_stream_phonemizer_license_proof_mismatch"),
            (proof.tts_phonemizer_source_sha256, self.bundle_identity.phonemizer_source_sha256, "voice_sherpa_stream_phonemizer_source_proof_mismatch"),
        )
        for actual, expected, code in checks:
            if actual != expected:
                raise ValueError(code)

    def stream_synthesize(
        self,
        *,
        text: str,
        proof: VoiceTtsGenerationProof,
        on_pcm_chunk: Callable[[EphemeralTtsPcmChunk], bool],
        cancellation: CancellationCheckpoint | None = None,
        speed: float = 1.0,
        sid: int = 0,
        silence_scale: float = 0.2,
        max_audio_seconds: float = 300.0,
    ) -> VoiceTtsStreamingResult:
        if self._closed:
            raise ValueError("voice_sherpa_stream_engine_closed")
        self._validate_proof(proof)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("voice_sherpa_stream_text_required")
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != proof.response_text_sha256:
            raise ValueError("voice_sherpa_stream_text_hash_mismatch")
        if not callable(on_pcm_chunk):
            raise ValueError("voice_sherpa_stream_chunk_consumer_required")
        if not 0.25 <= float(speed) <= 4.0:
            raise ValueError("voice_sherpa_stream_speed_invalid")
        if not 0 <= int(sid) <= 1_000_000:
            raise ValueError("voice_sherpa_stream_speaker_id_invalid")
        if not 0.0 <= float(silence_scale) <= 2.0:
            raise ValueError("voice_sherpa_stream_silence_scale_invalid")
        if not 0.1 <= float(max_audio_seconds) <= 600.0:
            raise ValueError("voice_sherpa_stream_max_audio_seconds_invalid")
        if cancellation is not None:
            cancellation.checkpoint()

        started = time.perf_counter()
        first_audio_latency_ms: float | None = None
        sequence = 0
        sample_count = 0
        audio_chain = "0" * 64
        stopped = False

        def _native_chunk(samples: tuple[float, ...], progress: float) -> bool:
            nonlocal first_audio_latency_ms, sequence, sample_count, audio_chain, stopped
            try:
                if cancellation is not None:
                    cancellation.checkpoint()
            except RuntimeError:
                stopped = True
                return False
            if not samples:
                stopped = True
                return False
            if not math.isfinite(float(progress)):
                stopped = True
                return False
            next_sample_count = sample_count + len(samples)
            if next_sample_count / self.sample_rate_hz > float(max_audio_seconds):
                stopped = True
                return False

            owned = bytearray(len(samples) * 2)
            try:
                for index, sample in enumerate(samples):
                    value = float(sample)
                    if not math.isfinite(value):
                        raise ValueError("voice_sherpa_stream_nonfinite_sample")
                    value = max(-1.0, min(1.0, value))
                    pcm16 = -32768 if value <= -1.0 else int(round(value * 32767.0))
                    struct.pack_into("<h", owned, index * 2, pcm16)
                pcm_sha = hashlib.sha256(owned).hexdigest()
                payload = {
                    "sequence": sequence,
                    "sample_rate_hz": self.sample_rate_hz,
                    "sample_count": len(samples),
                    "pcm_sha256": pcm_sha,
                    "progress": float(progress),
                    "tts_proof_fingerprint": proof.fingerprint,
                    "previous_audio_chain_fingerprint": audio_chain,
                }
                chunk = EphemeralTtsPcmChunk(
                    sequence=sequence,
                    sample_rate_hz=self.sample_rate_hz,
                    sample_count=len(samples),
                    pcm_sha256=pcm_sha,
                    progress=float(progress),
                    tts_proof_fingerprint=proof.fingerprint,
                    fingerprint=_sha256(payload),
                    _pcm=owned,
                )
                if first_audio_latency_ms is None:
                    first_audio_latency_ms = (time.perf_counter() - started) * 1000.0
                try:
                    keep_going = bool(on_pcm_chunk(chunk))
                finally:
                    chunk.close()
                audio_chain = _sha256(
                    {
                        "previous_audio_chain_fingerprint": audio_chain,
                        "chunk_fingerprint": chunk.fingerprint,
                    }
                )
                sequence += 1
                sample_count = next_sample_count
                if not keep_going:
                    stopped = True
                    return False
                return True
            except Exception:
                owned[:] = b"\x00" * len(owned)
                raise

        status = self.shim.generate(
            handle=self._handle,
            text=text,
            sid=int(sid),
            speed=float(speed),
            silence_scale=float(silence_scale),
            on_chunk=_native_chunk,
        )
        generation_duration_ms = (time.perf_counter() - started) * 1000.0
        if status < 0:
            raise RuntimeError(f"voice_sherpa_stream_generation_failed:{status}")
        if status == 1 or stopped:
            raise RuntimeError("voice_sherpa_stream_generation_cancelled")
        if status != 0:
            raise RuntimeError(f"voice_sherpa_stream_generation_status_invalid:{status}")
        if first_audio_latency_ms is None or sequence < 1 or sample_count < 1:
            raise ValueError("voice_sherpa_stream_no_audio_generated")
        if cancellation is not None:
            cancellation.checkpoint()

        audio_duration_ms = sample_count / self.sample_rate_hz * 1000.0
        rtf = generation_duration_ms / audio_duration_ms
        payload = {
            "language": self.language,
            "sample_rate_hz": self.sample_rate_hz,
            "chunk_count": sequence,
            "sample_count": sample_count,
            "first_audio_latency_ms": first_audio_latency_ms,
            "generation_duration_ms": generation_duration_ms,
            "audio_duration_ms": audio_duration_ms,
            "real_time_factor": rtf,
            "audio_chain_fingerprint": audio_chain,
            "tts_proof_fingerprint": proof.fingerprint,
        }
        return VoiceTtsStreamingResult(**payload, fingerprint=_sha256(payload))

    def close(self) -> None:
        if self._closed:
            return
        self.shim.destroy(self._handle)
        self._handle = None
        self._closed = True

    def __enter__(self) -> "SherpaOnnxStreamingVitsTtsEngine":
        if self._closed:
            raise ValueError("voice_sherpa_stream_engine_closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
