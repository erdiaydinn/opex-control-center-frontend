from __future__ import annotations

import hashlib
import json
import math
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .voice_response_lineage import VoiceTtsGenerationProof
from .voice_runtime_attestation import VoiceRuntimeArtifactSeal, hash_regular_file, seal_runtime_directory_manifest
from .voice_tts_bundle import VoiceTtsBundleExecutionIdentity


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class CancellationCheckpoint(Protocol):
    def checkpoint(self) -> None: ...


def _require_exact_file(path: Path, expected_sha256: str, *, code: str) -> None:
    digest, _ = hash_regular_file(Path(path))
    if digest != expected_sha256:
        raise ValueError(code)


@dataclass
class EphemeralTtsPcm:
    """Application-owned PCM16 output that is wiped when closed.

    sherpa-onnx/internal allocator copies are outside this ownership boundary; this
    class only promises best-effort zeroization of the EAY-owned output buffer.
    """

    language: str
    sample_rate_hz: int
    sample_count: int
    pcm_sha256: str
    tts_proof_fingerprint: str
    generation_duration_ms: float
    audio_duration_ms: float
    real_time_factor: float
    fingerprint: str
    _pcm: bytearray
    _closed: bool = False

    @property
    def closed(self) -> bool:
        return self._closed

    def view(self) -> memoryview:
        if self._closed:
            raise ValueError("voice_tts_pcm_closed")
        return memoryview(self._pcm).toreadonly()

    def close(self) -> None:
        if self._closed:
            return
        self._pcm[:] = b"\x00" * len(self._pcm)
        self._closed = True

    def __enter__(self) -> "EphemeralTtsPcm":
        if self._closed:
            raise ValueError("voice_tts_pcm_closed")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


class SherpaOnnxVitsTtsEngine:
    """Pinned, fileless-output sherpa-onnx VITS/Piper execution boundary.

    The runtime, model, tokens, config/model-card provenance and shared phonemizer
    directory must all match the already promoted deployment lineage before the engine
    is created. Synthesis returns only EAY-owned PCM in memory; it never writes WAV.
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
        sherpa_module: Any | None = None,
        num_threads: int = 2,
        max_num_sentences: int = 1,
    ) -> None:
        runtime_seal.validate()
        bundle_identity.validate()
        if runtime_seal.kind != "tts" or runtime_seal.implementation != "sherpa-onnx-vits":
            raise ValueError("voice_sherpa_tts_runtime_contract_mismatch")
        if runtime_seal.adapter_id != bundle_identity.runtime_adapter_id:
            raise ValueError("voice_sherpa_tts_runtime_adapter_mismatch")
        if runtime_seal.promotion_fingerprint != bundle_identity.runtime_adapter_promotion_fingerprint:
            raise ValueError("voice_sherpa_tts_runtime_promotion_mismatch")
        if not 1 <= int(num_threads) <= 64:
            raise ValueError("voice_sherpa_tts_thread_count_invalid")
        if not 1 <= int(max_num_sentences) <= 128:
            raise ValueError("voice_sherpa_tts_sentence_limit_invalid")

        self.runtime_seal = runtime_seal
        self.bundle_identity = bundle_identity
        self.language_identity = bundle_identity.artifact_for(language)
        self.language = self.language_identity.language
        self.model_path = Path(model_path)
        self.config_path = Path(config_path)
        self.tokens_path = Path(tokens_path)
        self.model_card_path = Path(model_card_path)
        self.phonemizer_data_dir = Path(phonemizer_data_dir)
        self.num_threads = int(num_threads)
        self.max_num_sentences = int(max_num_sentences)

        _require_exact_file(
            self.model_path,
            self.language_identity.model_sha256,
            code="voice_sherpa_tts_model_hash_mismatch",
        )
        _require_exact_file(
            self.config_path,
            self.language_identity.config_sha256,
            code="voice_sherpa_tts_config_hash_mismatch",
        )
        _require_exact_file(
            self.tokens_path,
            self.language_identity.tokens_sha256,
            code="voice_sherpa_tts_tokens_hash_mismatch",
        )
        _require_exact_file(
            self.model_card_path,
            self.language_identity.model_card_sha256,
            code="voice_sherpa_tts_model_card_hash_mismatch",
        )
        phonemizer_manifest = seal_runtime_directory_manifest(
            self.phonemizer_data_dir,
            logical_name="espeak-ng-data",
        )
        if phonemizer_manifest.fingerprint != bundle_identity.phonemizer_data_manifest_fingerprint:
            raise ValueError("voice_sherpa_tts_phonemizer_manifest_mismatch")
        self.phonemizer_manifest_fingerprint = phonemizer_manifest.fingerprint

        if sherpa_module is None:
            try:
                import sherpa_onnx as sherpa_module  # type: ignore
            except ImportError as exc:  # pragma: no cover - deployment dependency path
                raise RuntimeError("voice_sherpa_tts_dependency_missing") from exc
        self.sherpa = sherpa_module

        vits = self.sherpa.OfflineTtsVitsModelConfig(
            model=str(self.model_path),
            lexicon="",
            data_dir=str(self.phonemizer_data_dir),
            tokens=str(self.tokens_path),
        )
        model = self.sherpa.OfflineTtsModelConfig(
            vits=vits,
            provider="cpu",
            debug=False,
            num_threads=self.num_threads,
        )
        config = self.sherpa.OfflineTtsConfig(
            model=model,
            rule_fsts="",
            max_num_sentences=self.max_num_sentences,
        )
        if not bool(config.validate()):
            raise ValueError("voice_sherpa_tts_config_validation_failed")
        self._tts = self.sherpa.OfflineTts(config)

    def _validate_proof(self, proof: VoiceTtsGenerationProof) -> None:
        proof.validate()
        if proof.language != self.language:
            raise ValueError("voice_sherpa_tts_proof_language_mismatch")
        if proof.deployment_manifest_fingerprint != self.runtime_seal.deployment_manifest_fingerprint:
            raise ValueError("voice_sherpa_tts_deployment_manifest_mismatch")
        if proof.tts_bundle_execution_identity_fingerprint != self.bundle_identity.fingerprint:
            raise ValueError("voice_sherpa_tts_bundle_identity_mismatch")
        if proof.tts_adapter_promotion_fingerprint != self.runtime_seal.promotion_fingerprint:
            raise ValueError("voice_sherpa_tts_promotion_mismatch")
        checks = (
            (proof.tts_language_artifact_fingerprint, self.language_identity.fingerprint, "voice_sherpa_tts_language_artifact_mismatch"),
            (proof.tts_voice_model_sha256, self.language_identity.model_sha256, "voice_sherpa_tts_model_proof_mismatch"),
            (proof.tts_voice_config_sha256, self.language_identity.config_sha256, "voice_sherpa_tts_config_proof_mismatch"),
            (proof.tts_voice_tokens_sha256, self.language_identity.tokens_sha256, "voice_sherpa_tts_tokens_proof_mismatch"),
            (proof.tts_voice_model_card_sha256, self.language_identity.model_card_sha256, "voice_sherpa_tts_model_card_proof_mismatch"),
            (proof.tts_voice_license_id_sha256, self.language_identity.artifact_license_id_sha256, "voice_sherpa_tts_license_proof_mismatch"),
            (
                proof.tts_phonemizer_data_manifest_fingerprint,
                self.bundle_identity.phonemizer_data_manifest_fingerprint,
                "voice_sherpa_tts_phonemizer_proof_mismatch",
            ),
            (
                proof.tts_phonemizer_license_id_sha256,
                self.bundle_identity.phonemizer_license_id_sha256,
                "voice_sherpa_tts_phonemizer_license_proof_mismatch",
            ),
            (
                proof.tts_phonemizer_source_sha256,
                self.bundle_identity.phonemizer_source_sha256,
                "voice_sherpa_tts_phonemizer_source_proof_mismatch",
            ),
        )
        for actual, expected, code in checks:
            if actual != expected:
                raise ValueError(code)

    def synthesize(
        self,
        *,
        text: str,
        proof: VoiceTtsGenerationProof,
        speed: float = 1.0,
        sid: int = 0,
        silence_scale: float = 0.2,
        cancellation: CancellationCheckpoint | None = None,
        max_audio_seconds: float = 300.0,
    ) -> EphemeralTtsPcm:
        self._validate_proof(proof)
        if not isinstance(text, str) or not text.strip():
            raise ValueError("voice_sherpa_tts_text_required")
        text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if text_sha != proof.response_text_sha256:
            raise ValueError("voice_sherpa_tts_text_hash_mismatch")
        if not 0.25 <= float(speed) <= 4.0:
            raise ValueError("voice_sherpa_tts_speed_invalid")
        if not 0 <= int(sid) <= 1_000_000:
            raise ValueError("voice_sherpa_tts_speaker_id_invalid")
        if not 0.0 <= float(silence_scale) <= 2.0:
            raise ValueError("voice_sherpa_tts_silence_scale_invalid")
        if not 0.1 <= float(max_audio_seconds) <= 600.0:
            raise ValueError("voice_sherpa_tts_max_audio_seconds_invalid")
        if cancellation is not None:
            cancellation.checkpoint()

        gen_config = self.sherpa.GenerationConfig()
        gen_config.sid = int(sid)
        gen_config.speed = float(speed)
        gen_config.silence_scale = float(silence_scale)
        started = time.perf_counter()
        audio = self._tts.generate(text, gen_config)
        generation_duration_ms = (time.perf_counter() - started) * 1000.0
        if cancellation is not None:
            cancellation.checkpoint()

        samples = getattr(audio, "samples", None)
        sample_rate = int(getattr(audio, "sample_rate", 0) or 0)
        if samples is None:
            raise ValueError("voice_sherpa_tts_audio_samples_missing")
        try:
            sample_count = len(samples)
        except TypeError as exc:
            raise ValueError("voice_sherpa_tts_audio_samples_invalid") from exc
        if sample_count < 1:
            raise ValueError("voice_sherpa_tts_audio_empty")
        if not 8_000 <= sample_rate <= 96_000:
            raise ValueError("voice_sherpa_tts_sample_rate_invalid")
        audio_duration_seconds = sample_count / sample_rate
        if audio_duration_seconds > float(max_audio_seconds):
            raise ValueError("voice_sherpa_tts_audio_duration_exceeded")

        owned = bytearray(sample_count * 2)
        try:
            for index, sample in enumerate(samples):
                value = float(sample)
                if not math.isfinite(value):
                    raise ValueError("voice_sherpa_tts_nonfinite_sample")
                value = max(-1.0, min(1.0, value))
                pcm16 = -32768 if value <= -1.0 else int(round(value * 32767.0))
                struct.pack_into("<h", owned, index * 2, pcm16)
            pcm_sha256 = hashlib.sha256(owned).hexdigest()
            payload = {
                "language": self.language,
                "sample_rate_hz": sample_rate,
                "sample_count": sample_count,
                "pcm_sha256": pcm_sha256,
                "tts_proof_fingerprint": proof.fingerprint,
                "tts_bundle_execution_identity_fingerprint": self.bundle_identity.fingerprint,
                "phonemizer_data_manifest_fingerprint": self.phonemizer_manifest_fingerprint,
            }
            audio_duration_ms = audio_duration_seconds * 1000.0
            rtf = (generation_duration_ms / 1000.0) / audio_duration_seconds
            return EphemeralTtsPcm(
                language=self.language,
                sample_rate_hz=sample_rate,
                sample_count=sample_count,
                pcm_sha256=pcm_sha256,
                tts_proof_fingerprint=proof.fingerprint,
                generation_duration_ms=generation_duration_ms,
                audio_duration_ms=audio_duration_ms,
                real_time_factor=rtf,
                fingerprint=_sha256(payload),
                _pcm=owned,
            )
        except Exception:
            owned[:] = b"\x00" * len(owned)
            raise
