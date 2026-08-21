from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .main import Evidence


@dataclass(frozen=True)
class RagEvalResult:
    passed: bool
    failures: tuple[str, ...]
    legal_count: int
    company_count: int


def evaluate_evidence(evidence: list[Evidence], *, as_of: date, legal_required: bool = False) -> RagEvalResult:
    failures: list[str] = []
    seen: set[str] = set()
    legal_count = 0
    company_count = 0
    for item in evidence:
        if item.id in seen:
            failures.append(f"duplicate_evidence:{item.id}")
        seen.add(item.id)
        if item.effective_from and item.effective_from > as_of:
            failures.append(f"future_evidence:{item.id}")
        if item.effective_to and item.effective_to < as_of:
            failures.append(f"expired_evidence:{item.id}")
        if item.layer == "legal":
            legal_count += 1
            if item.authority_level != "binding":
                failures.append(f"legal_not_binding:{item.id}")
            if not item.source_url:
                failures.append(f"legal_missing_source:{item.id}")
        if item.layer == "company":
            company_count += 1
            if item.authority_level != "company":
                failures.append(f"company_wrong_authority:{item.id}")
    if legal_required and legal_count == 0:
        failures.append("required_legal_evidence_missing")
    return RagEvalResult(not failures, tuple(failures), legal_count, company_count)
