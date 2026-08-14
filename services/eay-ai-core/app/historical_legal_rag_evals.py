from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class HistoricalLegalRagCase:
    """One deterministic historical legal retrieval observation.

    `expected_source_ids` is the reviewed set of legal instrument IDs that are allowed
    to support the answer for this case/date. `retrieved_source_ids` contains only the
    legal sources actually supplied to the model after temporal filtering.

    Blocked cases represent an intentionally unresolved temporal graph. They must not
    call the model and must not supply legal evidence.
    """

    case_id: str
    as_of: date
    expected_source_ids: tuple[str, ...]
    retrieved_source_ids: tuple[str, ...]
    temporal_resolution_fingerprint: str
    resolution_blocked: bool = False
    model_called: bool = True


@dataclass(frozen=True)
class HistoricalLegalRagEvalResult:
    sample_size: int
    passed_cases: int
    pass_rate: float
    source_match_rate: float
    fingerprint_validity_rate: float
    inactive_legal_leak_rate: float
    temporal_block_bypass_rate: float
    failures: tuple[str, ...]


def evaluate_historical_legal_rag(
    cases: list[HistoricalLegalRagCase] | tuple[HistoricalLegalRagCase, ...],
) -> HistoricalLegalRagEvalResult:
    failures: list[str] = []
    passed_cases = 0
    source_match_ok = 0
    fingerprint_ok = 0
    inactive_leak_cases = 0
    blocked_cases = 0
    bypass_cases = 0

    for case in cases:
        case_failures: list[str] = []
        expected = set(case.expected_source_ids)
        retrieved = set(case.retrieved_source_ids)

        fingerprint_valid = (
            len(case.temporal_resolution_fingerprint) == 64
            and all(ch in "0123456789abcdef" for ch in case.temporal_resolution_fingerprint.lower())
        )
        if fingerprint_valid:
            fingerprint_ok += 1
        else:
            case_failures.append(f"invalid_temporal_fingerprint:{case.case_id}")

        if case.resolution_blocked:
            blocked_cases += 1
            if case.model_called:
                bypass_cases += 1
                case_failures.append(f"temporal_block_model_bypass:{case.case_id}")
            if retrieved:
                inactive_leak_cases += 1
                case_failures.append(f"blocked_case_has_legal_evidence:{case.case_id}")
            # A blocked case has no admissible legal source set by definition.
            if not retrieved:
                source_match_ok += 1
        else:
            if not case.model_called:
                case_failures.append(f"resolved_case_model_not_called:{case.case_id}")
            leaked = retrieved - expected
            if leaked:
                inactive_leak_cases += 1
                case_failures.append(
                    f"inactive_legal_source_leak:{case.case_id}:" + ",".join(sorted(leaked))
                )
            # Exact expected retrieval is deliberate for the curated eval corpus. It
            # catches both stale-source leakage and silent failure to retrieve the
            # reviewed source for that historical question/date.
            if retrieved == expected:
                source_match_ok += 1
            else:
                missing = expected - retrieved
                if missing:
                    case_failures.append(
                        f"expected_legal_source_missing:{case.case_id}:"
                        + ",".join(sorted(missing))
                    )

        if not case_failures:
            passed_cases += 1
        failures.extend(case_failures)

    sample_size = len(cases)
    denominator = sample_size or 1
    blocked_denominator = blocked_cases or 1
    return HistoricalLegalRagEvalResult(
        sample_size=sample_size,
        passed_cases=passed_cases,
        pass_rate=passed_cases / denominator if sample_size else 0.0,
        source_match_rate=source_match_ok / denominator if sample_size else 0.0,
        fingerprint_validity_rate=fingerprint_ok / denominator if sample_size else 0.0,
        inactive_legal_leak_rate=inactive_leak_cases / denominator if sample_size else 0.0,
        temporal_block_bypass_rate=bypass_cases / blocked_denominator if blocked_cases else 0.0,
        failures=tuple(failures),
    )
