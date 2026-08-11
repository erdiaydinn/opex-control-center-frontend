from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable

from .voice_runtime import CORE_LANGUAGES


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VoiceLanguageEval:
    language: str
    sample_count: int
    stt_word_error_rate: float
    semantic_consistency_rate: float
    human_naturalness_score: float
    citation_readback_accuracy: float
    p95_first_audio_ms: int
    p95_barge_in_ms: int
    interruption_success_rate: float = 1.0
    p95_cancel_propagation_ms: int = 0
    approval_replay_accept_count: int = 0
    fingerprint: str = ""

    def sealed(self) -> "VoiceLanguageEval":
        fp = _sha256(
            {
                "language": self.language,
                "sample_count": self.sample_count,
                "stt_word_error_rate": self.stt_word_error_rate,
                "semantic_consistency_rate": self.semantic_consistency_rate,
                "human_naturalness_score": self.human_naturalness_score,
                "citation_readback_accuracy": self.citation_readback_accuracy,
                "p95_first_audio_ms": self.p95_first_audio_ms,
                "p95_barge_in_ms": self.p95_barge_in_ms,
                "interruption_success_rate": self.interruption_success_rate,
                "p95_cancel_propagation_ms": self.p95_cancel_propagation_ms,
                "approval_replay_accept_count": self.approval_replay_accept_count,
            }
        )
        return VoiceLanguageEval(**{**self.__dict__, "fingerprint": fp})


@dataclass(frozen=True)
class VoiceReleaseDecision:
    approved: bool
    violations: tuple[str, ...]
    language_fingerprints: tuple[str, ...]
    fingerprint: str


def evaluate_voice_release(cases: Iterable[VoiceLanguageEval]) -> VoiceReleaseDecision:
    sealed = tuple(case.sealed() for case in cases)
    violations: list[str] = []
    by_language = {case.language: case for case in sealed}

    missing = sorted(set(CORE_LANGUAGES) - set(by_language))
    extra = sorted(set(by_language) - set(CORE_LANGUAGES))
    if missing:
        violations.append(f"voice_eval_missing_languages:{','.join(missing)}")
    if extra:
        violations.append(f"voice_eval_unknown_languages:{','.join(extra)}")
    if len(by_language) != len(sealed):
        violations.append("voice_eval_duplicate_language")

    for language in CORE_LANGUAGES:
        case = by_language.get(language)
        if case is None:
            continue
        if case.sample_count < 50:
            violations.append(f"voice_eval_{language}:insufficient_samples")
        if not 0.0 <= case.stt_word_error_rate <= 0.12:
            violations.append(f"voice_eval_{language}:stt_wer_too_high")
        if case.semantic_consistency_rate < 0.98:
            violations.append(f"voice_eval_{language}:semantic_consistency_too_low")
        if case.human_naturalness_score < 4.0 or case.human_naturalness_score > 5.0:
            violations.append(f"voice_eval_{language}:naturalness_below_target")
        if case.citation_readback_accuracy < 0.995:
            violations.append(f"voice_eval_{language}:citation_readback_inaccurate")
        if case.p95_first_audio_ms > 900:
            violations.append(f"voice_eval_{language}:first_audio_latency_too_high")
        if case.p95_barge_in_ms > 300:
            violations.append(f"voice_eval_{language}:barge_in_latency_too_high")
        if not 0.0 <= case.interruption_success_rate <= 1.0 or case.interruption_success_rate < 0.995:
            violations.append(f"voice_eval_{language}:interruption_success_too_low")
        if case.p95_cancel_propagation_ms < 0 or case.p95_cancel_propagation_ms > 250:
            violations.append(f"voice_eval_{language}:cancel_propagation_too_slow")
        if case.approval_replay_accept_count != 0:
            violations.append(f"voice_eval_{language}:approval_replay_accepted")

    language_fingerprints = tuple(sorted(case.fingerprint for case in sealed))
    fingerprint = _sha256(
        {
            "approved": not violations,
            "violations": violations,
            "language_fingerprints": language_fingerprints,
        }
    )
    return VoiceReleaseDecision(
        approved=not violations,
        violations=tuple(violations),
        language_fingerprints=language_fingerprints,
        fingerprint=fingerprint,
    )
