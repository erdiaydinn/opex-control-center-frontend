from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high", "critical", "unknown"]


class EvalEvidence(BaseModel):
    id: str
    layer: Literal["legal", "company", "standard", "operational"]
    authority_level: Literal["binding", "company", "voluntary", "operational"]


class GuardrailEvalRequest(BaseModel):
    legal_status: str
    legal_citations: list[str] = Field(default_factory=list)
    all_citations: list[str] = Field(default_factory=list)
    evidence: list[EvalEvidence] = Field(default_factory=list)
    risk: RiskLevel = "unknown"
    requires_human_review: bool = False


class CheckResult(BaseModel):
    check: str
    passed: bool
    detail: str


class GuardrailEvalResult(BaseModel):
    passed: bool
    score: float
    checks: list[CheckResult]


def evaluate_guardrails(payload: GuardrailEvalRequest) -> GuardrailEvalResult:
    evidence_ids = {item.id for item in payload.evidence}
    binding_legal_ids = {
        item.id for item in payload.evidence
        if item.layer == "legal" and item.authority_level == "binding"
    }

    citation_ok = all(citation in evidence_ids for citation in payload.all_citations)
    legal_citation_ok = all(citation in binding_legal_ids for citation in payload.legal_citations)

    has_binding_legal = bool(binding_legal_ids)
    legal_claim_ok = has_binding_legal or payload.legal_status.lower() in {
        "insufficient", "unknown", "not_found", "not-applicable", "not_applicable"
    }

    human_review_ok = payload.risk not in {"high", "critical"} or payload.requires_human_review

    checks = [
        CheckResult(
            check="citation_allowlist",
            passed=citation_ok,
            detail="Every citation must resolve to retrieved evidence.",
        ),
        CheckResult(
            check="binding_legal_citations",
            passed=legal_citation_ok,
            detail="Legal citations may only reference binding LEGAL evidence.",
        ),
        CheckResult(
            check="no_definitive_law_without_binding_source",
            passed=legal_claim_ok,
            detail="Without binding legal evidence the legal finding must remain insufficient/unknown.",
        ),
        CheckResult(
            check="high_risk_human_gate",
            passed=human_review_ok,
            detail="High/critical risk outputs require human review.",
        ),
    ]
    passed_count = sum(1 for item in checks if item.passed)
    return GuardrailEvalResult(
        passed=passed_count == len(checks),
        score=passed_count / len(checks),
        checks=checks,
    )


router = APIRouter(prefix="/v1/evals", tags=["evals"])


@router.post("/guardrails", response_model=GuardrailEvalResult)
def guardrail_eval(payload: GuardrailEvalRequest):
    return evaluate_guardrails(payload)
