from __future__ import annotations

from dataclasses import dataclass

from .canary_evals import CanaryDecision, CanaryMetrics, evaluate_canary


@dataclass(frozen=True)
class RagReleaseMetrics:
    sample_size: int
    pass_rate: float
    temporal_validity_rate: float
    legal_source_rate: float
    duplicate_evidence_rate: float


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


def evaluate_release(
    canary: CanaryMetrics,
    rag: RagReleaseMetrics,
    *,
    current_percent: int,
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
