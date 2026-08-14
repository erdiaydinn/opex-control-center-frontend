from __future__ import annotations

from dataclasses import dataclass

from .canary_evals import CanaryDecision, CanaryMetrics, evaluate_canary
from .historical_legal_rag_evals import HistoricalLegalRagEvalResult
from .safety_evals import SafetyEvalResult


@dataclass(frozen=True)
class RagReleaseMetrics:
    sample_size: int
    pass_rate: float
    temporal_validity_rate: float
    legal_source_rate: float
    duplicate_evidence_rate: float


@dataclass(frozen=True)
class HistoricalLegalReleaseMetrics:
    sample_size: int
    pass_rate: float
    source_match_rate: float
    fingerprint_validity_rate: float
    inactive_legal_leak_rate: float
    temporal_block_bypass_rate: float

    @classmethod
    def from_eval(cls, result: HistoricalLegalRagEvalResult) -> "HistoricalLegalReleaseMetrics":
        return cls(
            sample_size=result.sample_size,
            pass_rate=result.pass_rate,
            source_match_rate=result.source_match_rate,
            fingerprint_validity_rate=result.fingerprint_validity_rate,
            inactive_legal_leak_rate=result.inactive_legal_leak_rate,
            temporal_block_bypass_rate=result.temporal_block_bypass_rate,
        )


@dataclass(frozen=True)
class SafetyReleaseMetrics:
    sample_size: int
    pass_rate: float
    teacher_rejection_bypass_rate: float
    citation_loss_rate: float
    temporal_block_bypass_rate: float
    tool_answer_mismatch_rate: float
    fingerprint: str

    @classmethod
    def from_eval(cls, result: SafetyEvalResult) -> "SafetyReleaseMetrics":
        return cls(
            sample_size=result.sample_size,
            pass_rate=result.pass_rate,
            teacher_rejection_bypass_rate=result.teacher_rejection_bypass_rate,
            citation_loss_rate=result.citation_loss_rate,
            temporal_block_bypass_rate=result.temporal_block_bypass_rate,
            tool_answer_mismatch_rate=result.tool_answer_mismatch_rate,
            fingerprint=result.fingerprint,
        )


@dataclass(frozen=True)
class ReleaseDecision:
    promote: bool
    recommended_percent: int
    violations: tuple[str, ...]


class ReleasePolicy:
    min_rag_samples = 100
    min_rag_pass_rate = 0.99
    min_temporal_validity_rate = 1.0
    min_legal_source_rate = 1.0
    max_duplicate_evidence_rate = 0.0

    min_historical_legal_samples = 20
    min_historical_legal_pass_rate = 1.0
    min_historical_source_match_rate = 1.0
    min_historical_fingerprint_validity_rate = 1.0
    max_inactive_legal_leak_rate = 0.0
    max_temporal_block_bypass_rate = 0.0

    # Cross-layer safety failures are never averaged away by aggregate RAG/canary wins.
    min_safety_eval_samples = 20
    min_safety_eval_pass_rate = 1.0
    max_teacher_rejection_bypass_rate = 0.0
    max_citation_loss_rate = 0.0
    max_safety_temporal_block_bypass_rate = 0.0
    max_tool_answer_mismatch_rate = 0.0


def evaluate_release(
    canary: CanaryMetrics,
    rag: RagReleaseMetrics,
    *,
    current_percent: int,
    historical_legal: HistoricalLegalReleaseMetrics | None = None,
    safety: SafetyReleaseMetrics | None = None,
) -> ReleaseDecision:
    canary_decision: CanaryDecision = evaluate_canary(canary, current_percent)
    violations = list(canary_decision.violations)
    if rag.sample_size < ReleasePolicy.min_rag_samples:
        violations.append("rag_insufficient_sample_size")
    if rag.pass_rate < ReleasePolicy.min_rag_pass_rate:
        violations.append("rag_pass_rate_too_low")
    if rag.temporal_validity_rate < ReleasePolicy.min_temporal_validity_rate:
        violations.append("rag_temporal_validity_failed")
    if rag.legal_source_rate < ReleasePolicy.min_legal_source_rate:
        violations.append("rag_legal_source_grounding_failed")
    if rag.duplicate_evidence_rate > ReleasePolicy.max_duplicate_evidence_rate:
        violations.append("rag_duplicate_evidence_detected")

    if historical_legal is None:
        violations.append("historical_legal_eval_missing")
    else:
        if historical_legal.sample_size < ReleasePolicy.min_historical_legal_samples:
            violations.append("historical_legal_insufficient_sample_size")
        if historical_legal.pass_rate < ReleasePolicy.min_historical_legal_pass_rate:
            violations.append("historical_legal_pass_rate_failed")
        if historical_legal.source_match_rate < ReleasePolicy.min_historical_source_match_rate:
            violations.append("historical_legal_source_match_failed")
        if historical_legal.fingerprint_validity_rate < ReleasePolicy.min_historical_fingerprint_validity_rate:
            violations.append("historical_legal_fingerprint_invalid")
        if historical_legal.inactive_legal_leak_rate > ReleasePolicy.max_inactive_legal_leak_rate:
            violations.append("inactive_legal_source_leak_detected")
        if historical_legal.temporal_block_bypass_rate > ReleasePolicy.max_temporal_block_bypass_rate:
            violations.append("temporal_legal_block_bypass_detected")

    if safety is None:
        violations.append("cross_layer_safety_eval_missing")
    else:
        if safety.sample_size < ReleasePolicy.min_safety_eval_samples:
            violations.append("cross_layer_safety_insufficient_sample_size")
        if safety.pass_rate < ReleasePolicy.min_safety_eval_pass_rate:
            violations.append("cross_layer_safety_pass_rate_failed")
        if safety.teacher_rejection_bypass_rate > ReleasePolicy.max_teacher_rejection_bypass_rate:
            violations.append("teacher_quality_rejection_bypass_detected")
        if safety.citation_loss_rate > ReleasePolicy.max_citation_loss_rate:
            violations.append("citation_loss_detected")
        if safety.temporal_block_bypass_rate > ReleasePolicy.max_safety_temporal_block_bypass_rate:
            violations.append("cross_layer_temporal_block_bypass_detected")
        if safety.tool_answer_mismatch_rate > ReleasePolicy.max_tool_answer_mismatch_rate:
            violations.append("tool_answer_mismatch_detected")
        if len(safety.fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in safety.fingerprint):
            violations.append("cross_layer_safety_fingerprint_invalid")

    if violations:
        return ReleaseDecision(
            promote=False,
            recommended_percent=max(1, min(current_percent, 5)),
            violations=tuple(dict.fromkeys(violations)),
        )
    return ReleaseDecision(
        promote=True,
        recommended_percent=canary_decision.recommended_percent,
        violations=(),
    )
