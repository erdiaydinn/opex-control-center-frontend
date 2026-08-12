from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Literal

from .license_gate import assert_model_license_allowed
from .voice_runtime import CORE_LANGUAGES, AdapterKind, VoiceAdapterSpec


CandidateStatus = Literal[
    "eligible_with_pinned_artifact",
    "custom_artifact_required",
    "per_artifact_review_required",
]


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


@dataclass(frozen=True)
class VoiceAdapterCandidate:
    candidate_id: str
    kind: AdapterKind
    implementation: str
    runtime_license_id: str
    bundled_artifact_license_id: str
    official_sources: tuple[str, ...]
    languages: tuple[str, ...]
    status: CandidateStatus
    source_verified_on: str
    notes: str

    def validate(self) -> None:
        if len(self.candidate_id.strip()) < 3 or len(self.implementation.strip()) < 3:
            raise ValueError("voice_candidate_identity_required")
        if not self.official_sources or any(not url.startswith("https://") for url in self.official_sources):
            raise ValueError("voice_candidate_official_source_required")
        unknown = sorted(set(self.languages) - set(CORE_LANGUAGES))
        if unknown:
            raise ValueError(f"voice_candidate_unknown_language:{','.join(unknown)}")
        if not self.source_verified_on.strip():
            raise ValueError("voice_candidate_source_verification_date_required")
        assert_model_license_allowed(self.runtime_license_id)
        if self.status == "eligible_with_pinned_artifact":
            assert_model_license_allowed(self.bundled_artifact_license_id)

    @property
    def fingerprint(self) -> str:
        self.validate()
        return _sha256(
            {
                "candidate_id": self.candidate_id,
                "kind": self.kind,
                "implementation": self.implementation,
                "runtime_license_id": self.runtime_license_id.strip().lower(),
                "bundled_artifact_license_id": self.bundled_artifact_license_id.strip().lower(),
                "official_sources": self.official_sources,
                "languages": self.languages,
                "status": self.status,
                "source_verified_on": self.source_verified_on,
                "notes": self.notes,
            }
        )

    def build_spec(
        self,
        *,
        adapter_id: str,
        artifact_sha256: str,
        artifact_license_id: str | None = None,
    ) -> VoiceAdapterSpec:
        self.validate()
        if not _valid_sha256(artifact_sha256):
            raise ValueError("voice_candidate_artifact_sha256_required")

        chosen_artifact_license = (artifact_license_id or "").strip().lower()
        if self.status == "eligible_with_pinned_artifact":
            if chosen_artifact_license and chosen_artifact_license != self.bundled_artifact_license_id.strip().lower():
                raise ValueError("voice_candidate_artifact_license_mismatch")
            chosen_artifact_license = self.bundled_artifact_license_id.strip().lower()
        elif self.status == "custom_artifact_required":
            if not chosen_artifact_license:
                raise ValueError("voice_candidate_custom_artifact_license_required")
        elif self.status == "per_artifact_review_required":
            if not chosen_artifact_license:
                raise ValueError("voice_candidate_per_artifact_license_required")

        assert_model_license_allowed(chosen_artifact_license)
        spec = VoiceAdapterSpec(
            adapter_id=adapter_id,
            kind=self.kind,
            implementation=self.implementation,
            local=True,
            streaming=True,
            license_id=chosen_artifact_license,
            languages=self.languages,
            artifact_sha256=artifact_sha256,
            runtime_license_id=self.runtime_license_id,
            artifact_license_id=chosen_artifact_license,
        )
        spec.validate()
        return spec


# Authoritative-source snapshot verified 2026-08-12. These records are discovery
# candidates only: exact downloaded binary/model hashes and human promotions are still
# mandatory before deployment.
VOICE_ADAPTER_CANDIDATES: tuple[VoiceAdapterCandidate, ...] = (
    VoiceAdapterCandidate(
        candidate_id="whisper-cpp-openai-whisper",
        kind="stt",
        implementation="whisper.cpp",
        runtime_license_id="mit",
        bundled_artifact_license_id="mit",
        official_sources=(
            "https://github.com/ggml-org/whisper.cpp",
            "https://github.com/openai/whisper",
        ),
        languages=CORE_LANGUAGES,
        status="eligible_with_pinned_artifact",
        source_verified_on="2026-08-12",
        notes="whisper.cpp runtime and OpenAI Whisper code/model weights are MIT; exact converted model bytes remain hash-pinned.",
    ),
    VoiceAdapterCandidate(
        candidate_id="silero-vad-onnx",
        kind="vad",
        implementation="silero-vad-onnx",
        runtime_license_id="mit",
        bundled_artifact_license_id="mit",
        official_sources=("https://github.com/snakers4/silero-vad",),
        languages=CORE_LANGUAGES,
        status="eligible_with_pinned_artifact",
        source_verified_on="2026-08-12",
        notes="Silero VAD is published under MIT and supports local ONNX execution; VAD is language-agnostic for the EAY core language set.",
    ),
    VoiceAdapterCandidate(
        candidate_id="openwakeword-custom-eay",
        kind="wakeword",
        implementation="openwakeword-custom",
        runtime_license_id="apache-2.0",
        bundled_artifact_license_id="cc-by-nc-sa-4.0",
        official_sources=("https://github.com/dscripka/openWakeWord",),
        languages=("en",),
        status="custom_artifact_required",
        source_verified_on="2026-08-12",
        notes="openWakeWord code is Apache-2.0 and bundled pretrained models are CC BY-NC-SA 4.0. The upstream project currently documents English language support; EAY therefore does not claim TR/DE/AR/FA wakeword coverage from this candidate. Commercial deployment requires a separately licensed custom artifact and explicit multilingual evaluation before any broader language claim.",
    ),
    VoiceAdapterCandidate(
        candidate_id="sherpa-onnx-piper-vits",
        kind="tts",
        implementation="sherpa-onnx-vits",
        runtime_license_id="apache-2.0",
        bundled_artifact_license_id="per-model-card",
        official_sources=(
            "https://github.com/k2-fsa/sherpa-onnx",
            "https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md",
        ),
        languages=CORE_LANGUAGES,
        status="per_artifact_review_required",
        source_verified_on="2026-08-12",
        notes="sherpa-onnx runtime is Apache-2.0 and can execute VITS/Piper voices; Piper lists TR/EN/DE/AR/FA voices, but each voice MODEL_CARD may impose different terms, so every selected voice artifact requires an allow-listed license before promotion.",
    ),
)


def candidate_by_id(candidate_id: str) -> VoiceAdapterCandidate:
    normalized = candidate_id.strip()
    for candidate in VOICE_ADAPTER_CANDIDATES:
        if candidate.candidate_id == normalized:
            return candidate
    raise KeyError("voice_adapter_candidate_not_found")
