from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable

from .voice_release_evidence import VoiceLanguageMeasurementEvidence, seal_voice_language_measurement_evidence
from .voice_release_gate import VoiceLanguageEval
from .voice_runtime import CORE_LANGUAGES


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _valid_sha256(value: str | None) -> bool:
    return bool(value) and len(str(value)) == 64 and all(ch in "0123456789abcdef" for ch in str(value))


def _require_sha(value: str, code: str) -> str:
    value = str(value)
    if not _valid_sha256(value):
        raise ValueError(code)
    return value


def _base_language(language: str) -> str:
    return language.strip().lower().split("-", 1)[0].split("_", 1)[0]


def _nearest_rank_p95(values: Iterable[int]) -> int:
    ordered = sorted(int(value) for value in values)
    if not ordered:
        raise ValueError("voice_measurement_latency_samples_required")
    rank = max(1, math.ceil(0.95 * len(ordered)))
    return ordered[rank - 1]


@dataclass(frozen=True)
class VoiceMeasurementSample:
    language: str
    case_id_sha256: str
    reference_text_sha256: str
    hypothesis_text_sha256: str
    input_lineage_fingerprint: str
    tts_generation_proof_fingerprint: str
    streaming_result_fingerprint: str
    reference_word_count: int
    word_error_count: int
    semantic_consistent: bool
    naturalness_score: float
    citation_checks_count: int
    citation_checks_correct: int
    first_audio_ms: int
    barge_in_ms: int
    interruption_succeeded: bool
    cancel_propagation_ms: int
    approval_replay_accept_count: int
    human_review_event_sha256: str
    fingerprint: str = ""

    def _payload(self) -> dict[str, object]:
        return {
            "language": _base_language(self.language),
            "case_id_sha256": self.case_id_sha256,
            "reference_text_sha256": self.reference_text_sha256,
            "hypothesis_text_sha256": self.hypothesis_text_sha256,
            "input_lineage_fingerprint": self.input_lineage_fingerprint,
            "tts_generation_proof_fingerprint": self.tts_generation_proof_fingerprint,
            "streaming_result_fingerprint": self.streaming_result_fingerprint,
            "reference_word_count": self.reference_word_count,
            "word_error_count": self.word_error_count,
            "semantic_consistent": self.semantic_consistent,
            "naturalness_score": self.naturalness_score,
            "citation_checks_count": self.citation_checks_count,
            "citation_checks_correct": self.citation_checks_correct,
            "first_audio_ms": self.first_audio_ms,
            "barge_in_ms": self.barge_in_ms,
            "interruption_succeeded": self.interruption_succeeded,
            "cancel_propagation_ms": self.cancel_propagation_ms,
            "approval_replay_accept_count": self.approval_replay_accept_count,
            "human_review_event_sha256": self.human_review_event_sha256,
        }

    def validate(self) -> None:
        language = _base_language(self.language)
        if language not in CORE_LANGUAGES:
            raise ValueError("voice_measurement_language_not_enabled")
        for value, code in (
            (self.case_id_sha256, "voice_measurement_case_id_invalid"),
            (self.reference_text_sha256, "voice_measurement_reference_hash_invalid"),
            (self.hypothesis_text_sha256, "voice_measurement_hypothesis_hash_invalid"),
            (self.input_lineage_fingerprint, "voice_measurement_input_lineage_invalid"),
            (self.tts_generation_proof_fingerprint, "voice_measurement_tts_proof_invalid"),
            (self.streaming_result_fingerprint, "voice_measurement_streaming_result_invalid"),
            (self.human_review_event_sha256, "voice_measurement_human_review_invalid"),
        ):
            _require_sha(value, code)
        for value, code in (
            (self.reference_word_count, "voice_measurement_reference_word_count_invalid"),
            (self.word_error_count, "voice_measurement_word_error_count_invalid"),
            (self.citation_checks_count, "voice_measurement_citation_count_invalid"),
            (self.citation_checks_correct, "voice_measurement_citation_correct_invalid"),
            (self.first_audio_ms, "voice_measurement_first_audio_invalid"),
            (self.barge_in_ms, "voice_measurement_barge_in_invalid"),
            (self.cancel_propagation_ms, "voice_measurement_cancel_propagation_invalid"),
            (self.approval_replay_accept_count, "voice_measurement_approval_replay_invalid"),
        ):
            if isinstance(value, bool) or int(value) < 0:
                raise ValueError(code)
        if self.reference_word_count < 1:
            raise ValueError("voice_measurement_reference_word_count_invalid")
        if self.citation_checks_count < 1 or self.citation_checks_correct > self.citation_checks_count:
            raise ValueError("voice_measurement_citation_count_invalid")
        if not isinstance(self.semantic_consistent, bool) or not isinstance(self.interruption_succeeded, bool):
            raise ValueError("voice_measurement_boolean_metric_invalid")
        if isinstance(self.naturalness_score, bool) or not math.isfinite(float(self.naturalness_score)):
            raise ValueError("voice_measurement_naturalness_invalid")
        if not 0.0 <= float(self.naturalness_score) <= 5.0:
            raise ValueError("voice_measurement_naturalness_invalid")
        if self.fingerprint:
            if not _valid_sha256(self.fingerprint) or _sha256(self._payload()) != self.fingerprint:
                raise ValueError("voice_measurement_sample_fingerprint_drift")

    def sealed(self) -> "VoiceMeasurementSample":
        self.validate()
        payload = self._payload()
        return VoiceMeasurementSample(**{**self.__dict__, "language": _base_language(self.language), "fingerprint": _sha256(payload)})


@dataclass(frozen=True)
class VoiceMeasurementAggregate:
    language: str
    sample_fingerprints: tuple[str, ...]
    raw_measurement_manifest_sha256: str
    human_review_manifest_sha256: str
    evaluation: VoiceLanguageEval
    fingerprint: str

    def validate(self) -> None:
        if self.language not in CORE_LANGUAGES or self.evaluation.language != self.language:
            raise ValueError("voice_measurement_aggregate_language_mismatch")
        self.evaluation.validate()
        if not self.sample_fingerprints or len(set(self.sample_fingerprints)) != len(self.sample_fingerprints):
            raise ValueError("voice_measurement_aggregate_samples_invalid")
        if tuple(sorted(self.sample_fingerprints)) != self.sample_fingerprints:
            raise ValueError("voice_measurement_aggregate_samples_not_canonical")
        for value in self.sample_fingerprints:
            _require_sha(value, "voice_measurement_aggregate_sample_fingerprint_invalid")
        _require_sha(self.raw_measurement_manifest_sha256, "voice_measurement_aggregate_manifest_invalid")
        _require_sha(self.human_review_manifest_sha256, "voice_measurement_aggregate_human_review_invalid")
        _require_sha(self.fingerprint, "voice_measurement_aggregate_fingerprint_invalid")
        payload = {
            "language": self.language,
            "sample_fingerprints": self.sample_fingerprints,
            "raw_measurement_manifest_sha256": self.raw_measurement_manifest_sha256,
            "human_review_manifest_sha256": self.human_review_manifest_sha256,
            "evaluation_fingerprint": self.evaluation.sealed().fingerprint,
        }
        if _sha256(payload) != self.fingerprint:
            raise ValueError("voice_measurement_aggregate_fingerprint_drift")


def aggregate_voice_measurements(samples: Iterable[VoiceMeasurementSample]) -> VoiceMeasurementAggregate:
    sealed = tuple(sample.sealed() for sample in samples)
    if not sealed:
        raise ValueError("voice_measurement_samples_required")
    languages = {_base_language(sample.language) for sample in sealed}
    if len(languages) != 1:
        raise ValueError("voice_measurement_mixed_languages_forbidden")
    language = next(iter(languages))
    sample_fps = tuple(sorted(sample.fingerprint for sample in sealed))
    if len(set(sample_fps)) != len(sample_fps):
        raise ValueError("voice_measurement_duplicate_sample_forbidden")

    total_reference_words = sum(sample.reference_word_count for sample in sealed)
    total_word_errors = sum(sample.word_error_count for sample in sealed)
    total_citations = sum(sample.citation_checks_count for sample in sealed)
    correct_citations = sum(sample.citation_checks_correct for sample in sealed)
    evaluation = VoiceLanguageEval(
        language=language,
        sample_count=len(sealed),
        stt_word_error_rate=total_word_errors / total_reference_words,
        semantic_consistency_rate=sum(1 for sample in sealed if sample.semantic_consistent) / len(sealed),
        human_naturalness_score=sum(float(sample.naturalness_score) for sample in sealed) / len(sealed),
        citation_readback_accuracy=correct_citations / total_citations,
        p95_first_audio_ms=_nearest_rank_p95(sample.first_audio_ms for sample in sealed),
        p95_barge_in_ms=_nearest_rank_p95(sample.barge_in_ms for sample in sealed),
        interruption_success_rate=sum(1 for sample in sealed if sample.interruption_succeeded) / len(sealed),
        p95_cancel_propagation_ms=_nearest_rank_p95(sample.cancel_propagation_ms for sample in sealed),
        approval_replay_accept_count=sum(sample.approval_replay_accept_count for sample in sealed),
    ).sealed()
    raw_manifest = _sha256({"language": language, "sample_fingerprints": sample_fps})
    human_review_manifest = _sha256(
        {
            "language": language,
            "human_review_event_sha256": tuple(sorted(sample.human_review_event_sha256 for sample in sealed)),
        }
    )
    payload = {
        "language": language,
        "sample_fingerprints": sample_fps,
        "raw_measurement_manifest_sha256": raw_manifest,
        "human_review_manifest_sha256": human_review_manifest,
        "evaluation_fingerprint": evaluation.fingerprint,
    }
    aggregate = VoiceMeasurementAggregate(
        language=language,
        sample_fingerprints=sample_fps,
        raw_measurement_manifest_sha256=raw_manifest,
        human_review_manifest_sha256=human_review_manifest,
        evaluation=evaluation,
        fingerprint=_sha256(payload),
    )
    aggregate.validate()
    return aggregate


def seal_language_release_evidence_from_measurements(
    *,
    samples: Iterable[VoiceMeasurementSample],
    deployment_manifest_fingerprint: str,
    model_execution_identity_fingerprint: str,
    tts_bundle_execution_identity_fingerprint: str,
    runtime_attestation_bundle_fingerprint: str,
    eval_suite_sha256: str,
    measurement_harness_sha256: str,
    runtime_environment_fingerprint: str,
    reviewer: str,
    approval_reference: str,
    measured_at: datetime | None = None,
) -> tuple[VoiceMeasurementAggregate, VoiceLanguageMeasurementEvidence]:
    aggregate = aggregate_voice_measurements(samples)
    evidence = seal_voice_language_measurement_evidence(
        evaluation=aggregate.evaluation,
        deployment_manifest_fingerprint=deployment_manifest_fingerprint,
        model_execution_identity_fingerprint=model_execution_identity_fingerprint,
        tts_bundle_execution_identity_fingerprint=tts_bundle_execution_identity_fingerprint,
        runtime_attestation_bundle_fingerprint=runtime_attestation_bundle_fingerprint,
        eval_suite_sha256=eval_suite_sha256,
        measurement_harness_sha256=measurement_harness_sha256,
        runtime_environment_fingerprint=runtime_environment_fingerprint,
        raw_measurement_manifest_sha256=aggregate.raw_measurement_manifest_sha256,
        human_review_manifest_sha256=aggregate.human_review_manifest_sha256,
        reviewer=reviewer,
        approval_reference=approval_reference,
        measured_at=measured_at,
    )
    return aggregate, evidence
