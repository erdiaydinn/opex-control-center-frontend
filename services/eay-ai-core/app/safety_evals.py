from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafetyEvalCase:
    case_id: str
    teacher_required: bool = False
    teacher_quality_accepted: bool = True
    expected_evidence_ids: tuple[str, ...] = ()
    cited_evidence_ids: tuple[str, ...] = ()
    temporal_resolution_blocked: bool = False
    model_called: bool = False
    expected_tool_answer: str | None = None
    actual_tool_answer: str | None = None


@dataclass(frozen=True)
class SafetyEvalCaseResult:
    case_id: str
    passed: bool
    violations: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class SafetyEvalResult:
    sample_size: int
    pass_rate: float
    teacher_rejection_bypass_rate: float
    citation_loss_rate: float
    temporal_block_bypass_rate: float
    tool_answer_mismatch_rate: float
    fingerprint: str
    cases: tuple[SafetyEvalCaseResult, ...]


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.split()).casefold()


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def evaluate_safety_evals(cases: Iterable[SafetyEvalCase]) -> SafetyEvalResult:
    """Deterministically evaluate cross-layer failures that must never reach promotion.

    This intentionally avoids an LLM-as-judge. It checks objective invariants spanning
    teacher quality, evidence preservation, temporal legal blocking and tool-answer
    consistency. Any bypass is release-blocking rather than averaged away by other wins.
    """

    materialized = tuple(cases)
    results: list[SafetyEvalCaseResult] = []
    teacher_bypass = 0
    citation_loss = 0
    temporal_bypass = 0
    tool_mismatch = 0

    for case in materialized:
        violations: list[str] = []
        if case.teacher_required and not case.teacher_quality_accepted:
            violations.append("teacher_quality_rejection_bypassed")
            teacher_bypass += 1

        expected = {item.strip() for item in case.expected_evidence_ids if item.strip()}
        cited = {item.strip() for item in case.cited_evidence_ids if item.strip()}
        if expected and not expected.issubset(cited):
            violations.append("citation_evidence_lost")
            citation_loss += 1

        if case.temporal_resolution_blocked and case.model_called:
            violations.append("temporal_legal_block_bypassed")
            temporal_bypass += 1

        expected_tool = _norm(case.expected_tool_answer)
        actual_tool = _norm(case.actual_tool_answer)
        if expected_tool is not None and expected_tool != actual_tool:
            violations.append("tool_answer_mismatch")
            tool_mismatch += 1

        payload = {
            "case_id": case.case_id,
            "teacher_required": case.teacher_required,
            "teacher_quality_accepted": case.teacher_quality_accepted,
            "expected_evidence_ids": sorted(expected),
            "cited_evidence_ids": sorted(cited),
            "temporal_resolution_blocked": case.temporal_resolution_blocked,
            "model_called": case.model_called,
            "expected_tool_answer": expected_tool,
            "actual_tool_answer": actual_tool,
            "violations": violations,
        }
        results.append(
            SafetyEvalCaseResult(
                case_id=case.case_id,
                passed=not violations,
                violations=tuple(violations),
                fingerprint=_fingerprint(payload),
            )
        )

    count = len(materialized)
    passed = sum(1 for item in results if item.passed)
    denominator = count or 1
    aggregate_payload = {
        "sample_size": count,
        "case_fingerprints": [item.fingerprint for item in results],
        "teacher_rejection_bypass_rate": teacher_bypass / denominator,
        "citation_loss_rate": citation_loss / denominator,
        "temporal_block_bypass_rate": temporal_bypass / denominator,
        "tool_answer_mismatch_rate": tool_mismatch / denominator,
    }
    return SafetyEvalResult(
        sample_size=count,
        pass_rate=passed / denominator if count else 0.0,
        teacher_rejection_bypass_rate=teacher_bypass / denominator,
        citation_loss_rate=citation_loss / denominator,
        temporal_block_bypass_rate=temporal_bypass / denominator,
        tool_answer_mismatch_rate=tool_mismatch / denominator,
        fingerprint=_fingerprint(aggregate_payload),
        cases=tuple(results),
    )
