from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class HistoricalLegalEvalCase:
    case_id: str
    temporal_resolved: bool
    model_called: bool
    expected_active_instrument_ids: tuple[str, ...]
    observed_legal_instrument_ids: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalLegalEvalResult:
    case_id: str
    passed: bool
    violations: tuple[str, ...]


@dataclass(frozen=True)
class HistoricalLegalEvalMetrics:
    sample_size: int
    pass_rate: float
    active_source_accuracy_rate: float
    inactive_source_leak_rate: float
    unresolved_model_call_rate: float


def evaluate_historical_legal_case(case: HistoricalLegalEvalCase) -> HistoricalLegalEvalResult:
    """Evaluate historical legal retrieval without invoking a model.

    The temporal resolver remains the authority for which legal instruments are active.
    This evaluator checks that retrieval/citation provenance respects that resolved set
    and that unresolved legal timelines never reach model execution.
    """
    violations: list[str] = []
    expected = set(case.expected_active_instrument_ids)
    observed = set(case.observed_legal_instrument_ids)

    if not case.temporal_resolved:
        if case.model_called:
            violations.append("model_called_with_unresolved_legal_timeline")
        if observed:
            violations.append("legal_evidence_emitted_with_unresolved_timeline")
    else:
        inactive = observed - expected
        if inactive:
            violations.append("inactive_legal_source_leak:" + ",".join(sorted(inactive)))
        missing = expected - observed
        if missing:
            violations.append("expected_active_legal_source_missing:" + ",".join(sorted(missing)))

    return HistoricalLegalEvalResult(
        case_id=case.case_id,
        passed=not violations,
        violations=tuple(violations),
    )


def aggregate_historical_legal_evals(
    cases: Iterable[HistoricalLegalEvalCase],
) -> HistoricalLegalEvalMetrics:
    case_list = list(cases)
    if not case_list:
        return HistoricalLegalEvalMetrics(
            sample_size=0,
            pass_rate=0.0,
            active_source_accuracy_rate=0.0,
            inactive_source_leak_rate=0.0,
            unresolved_model_call_rate=0.0,
        )

    results = [evaluate_historical_legal_case(case) for case in case_list]
    resolved = [case for case in case_list if case.temporal_resolved]
    unresolved = [case for case in case_list if not case.temporal_resolved]

    active_correct = 0
    inactive_leak_count = 0
    for case in resolved:
        expected = set(case.expected_active_instrument_ids)
        observed = set(case.observed_legal_instrument_ids)
        if observed == expected:
            active_correct += 1
        if observed - expected:
            inactive_leak_count += 1

    unresolved_model_calls = sum(1 for case in unresolved if case.model_called)
    return HistoricalLegalEvalMetrics(
        sample_size=len(case_list),
        pass_rate=sum(1 for result in results if result.passed) / len(case_list),
        active_source_accuracy_rate=(active_correct / len(resolved)) if resolved else 1.0,
        inactive_source_leak_rate=(inactive_leak_count / len(resolved)) if resolved else 0.0,
        unresolved_model_call_rate=(unresolved_model_calls / len(unresolved)) if unresolved else 0.0,
    )
