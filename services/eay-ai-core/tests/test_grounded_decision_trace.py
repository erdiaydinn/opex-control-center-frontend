from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.grounded_decision_trace import (
    DECISION_TRACE_CONTRACT,
    build_grounded_decision_trace,
)


def finding(status: str, summary: str, citations=None):
    return SimpleNamespace(
        status=status,
        summary=summary,
        citations=list(citations or []),
    )


def evidence(evidence_id: str, layer: str, authority: str, score: float):
    return SimpleNamespace(
        id=evidence_id,
        layer=layer,
        authority_level=authority,
        score=score,
        effective_from=date(2026, 8, 1),
        effective_to=None,
    )


def answer():
    return SimpleNamespace(
        legal=finding("supported", "Law requires X.", ["law-1"]),
        company=finding("supported", "Company requires X plus Y.", ["company-1"]),
        standards=finding("insufficient", "", []),
        operational=finding("supported", "Observed KPI deteriorated.", ["ops-1"]),
        recommendation="Apply company rule and monitor KPI.",
        confidence=0.71,
        requires_human_review=True,
    )


def test_trace_maps_structured_claims_to_only_real_evidence_ids() -> None:
    request = SimpleNamespace(
        message="Şirket kuralı mevzuattan daha katı mı ve operasyon etkisi nedir?",
        as_of=date(2026, 8, 17),
        layers=["legal", "company", "operational"],
    )
    plan = SimpleNamespace(
        active_layers=["legal", "company", "operational"],
        inferred_required_layers=["legal", "company", "operational"],
    )
    quality = SimpleNamespace(
        required_layers=["legal", "company", "operational"],
        missing_required_layers=[],
        evidence_sufficient=True,
    )
    critic = SimpleNamespace(
        verdict="PASS",
        issues=[],
        revision_applied=False,
    )

    trace = build_grounded_decision_trace(
        request=request,
        answer=answer(),
        evidence=[
            evidence("law-1", "legal", "binding", 0.95),
            evidence("company-1", "company", "company", 0.87),
            evidence("ops-1", "operational", "operational", 0.90),
        ],
        evidence_plan=plan,
        decision_quality=quality,
        critic=critic,
    )

    assert trace.contract == DECISION_TRACE_CONTRACT
    assert len(trace.question_fingerprint) == 64
    assert len(trace.trace_fingerprint) == 64
    assert trace.production_authority is False
    assert trace.required_layers == ["legal", "company", "operational"]
    assert trace.missing_required_layers == []
    assert trace.recommendation_basis_evidence_ids == [
        "company-1",
        "law-1",
        "ops-1",
    ]
    assert trace.recommendation_basis_state == "supported_findings_present"
    claims = {item.layer: item for item in trace.claims}
    assert claims["legal"].support_state == "supported"
    assert claims["company"].support_state == "supported"
    assert claims["standard"].support_state == "no_claim"
    assert claims["operational"].support_state == "supported"


def test_unknown_citation_is_exposed_not_silently_accepted() -> None:
    response = answer()
    response.operational = finding(
        "supported",
        "Operational claim references one invalid evidence id.",
        ["ops-1", "invented-id"],
    )
    trace = build_grounded_decision_trace(
        request=SimpleNamespace(
            message="What changed?",
            as_of=date(2026, 8, 17),
            layers=["operational"],
        ),
        answer=response,
        evidence=[evidence("ops-1", "operational", "operational", 0.9)],
    )

    operational = next(item for item in trace.claims if item.layer == "operational")
    assert operational.support_state == "partially_supported"
    assert operational.valid_citation_ids == ["ops-1"]
    assert operational.invalid_citation_ids == ["invented-id"]
    assert "invented-id" not in trace.recommendation_basis_evidence_ids


def test_missing_required_layer_and_critic_issue_remain_observable() -> None:
    quality = SimpleNamespace(
        required_layers=["legal", "company"],
        missing_required_layers=["company"],
        evidence_sufficient=False,
    )
    critic = SimpleNamespace(
        verdict="REJECT",
        issues=[SimpleNamespace(code="missing_company_evidence")],
        revision_applied=True,
    )
    trace = build_grounded_decision_trace(
        request=SimpleNamespace(
            message="Is our company policy stricter than law?",
            as_of=date(2026, 8, 17),
            layers=["legal", "company"],
        ),
        answer=answer(),
        evidence=[evidence("law-1", "legal", "binding", 0.95)],
        decision_quality=quality,
        critic=critic,
    )

    assert trace.evidence_sufficient is False
    assert trace.missing_required_layers == ["company"]
    assert trace.critic_verdict == "REJECT"
    assert trace.critic_issue_codes == ["missing_company_evidence"]
    assert trace.critic_revision_applied is True
    company = next(item for item in trace.claims if item.layer == "company")
    assert company.support_state == "unsupported"


def test_trace_fingerprint_is_deterministic_and_question_text_is_not_serialized() -> None:
    request = SimpleNamespace(
        message="Sensitive internal operational question",
        as_of=date(2026, 8, 17),
        layers=["operational"],
    )
    first = build_grounded_decision_trace(
        request=request,
        answer=answer(),
        evidence=[evidence("ops-1", "operational", "operational", 0.9)],
    )
    second = build_grounded_decision_trace(
        request=request,
        answer=answer(),
        evidence=[evidence("ops-1", "operational", "operational", 0.9)],
    )

    assert first.trace_fingerprint == second.trace_fingerprint
    serialized = first.model_dump_json()
    assert "Sensitive internal operational question" not in serialized
    assert first.question_fingerprint in serialized
