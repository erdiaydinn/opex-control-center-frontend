from __future__ import annotations

from types import SimpleNamespace

from app.grounded_reasoning import (
    DECISION_QUALITY_CONTRACT,
    assess_and_calibrate_grounded_answer,
    infer_required_layers,
)


def section(status: str, citations: list[str] | None = None):
    return SimpleNamespace(status=status, citations=list(citations or []))


def answer(
    *,
    confidence: float = 0.95,
    risk: str = "low",
    human_review: bool = False,
    legal=None,
    company=None,
    standards=None,
    operational=None,
):
    return SimpleNamespace(
        confidence=confidence,
        risk=risk,
        requires_human_review=human_review,
        legal=legal or section("insufficient"),
        company=company or section("insufficient"),
        standards=standards or section("insufficient"),
        operational=operational or section("insufficient"),
    )


def request(message: str, layers=None):
    return SimpleNamespace(
        message=message,
        layers=list(layers or ["legal", "company", "standard", "operational"]),
    )


def evidence(
    evidence_id: str,
    layer: str,
    *,
    authority: str = "operational",
):
    return SimpleNamespace(
        id=evidence_id,
        layer=layer,
        authority_level=authority,
    )


def test_required_layers_follow_question_not_search_allowlist() -> None:
    assert infer_required_layers("NSFR neden yükseldi?") == ["operational"]
    assert infer_required_layers("Bu yasal olarak zorunlu mu?") == ["legal"]
    mixed = infer_required_layers("Şirket politikamız mevzuattan daha katı mı?")
    assert mixed == ["legal", "company"]


def test_missing_binding_legal_evidence_caps_confidence_and_requires_review() -> None:
    model_answer = answer(
        confidence=0.99,
        risk="medium",
        legal=section("applicable"),
    )
    report = assess_and_calibrate_grounded_answer(
        request("Bu işlem yasal olarak zorunlu mu?"),
        model_answer,
        [],
    )

    assert report.contract == DECISION_QUALITY_CONTRACT
    assert "binding_legal_evidence_missing" in report.blockers
    assert report.evidence_sufficient is False
    assert report.confidence_cap == 0.20
    assert model_answer.confidence == 0.20
    assert model_answer.requires_human_review is True


def test_high_risk_operational_answer_forces_human_review_even_with_evidence() -> None:
    model_answer = answer(
        confidence=0.90,
        risk="high",
        operational=section("supported", ["ops-1"]),
    )
    report = assess_and_calibrate_grounded_answer(
        request("NSFR KPI neden yükseldi?", ["operational"]),
        model_answer,
        [evidence("ops-1", "operational")],
    )

    assert report.blockers == []
    assert report.evidence_sufficient is True
    assert report.human_review_required is True
    assert model_answer.requires_human_review is True
    assert model_answer.confidence == 0.85


def test_uncited_claim_is_blocked_and_overconfidence_is_reduced() -> None:
    model_answer = answer(
        confidence=0.97,
        company=section("required", []),
    )
    report = assess_and_calibrate_grounded_answer(
        request("Şirket politikamız ne diyor?", ["company"]),
        model_answer,
        [evidence("company-1", "company", authority="company")],
    )

    assert "uncited_company_finding" in report.blockers
    assert report.evidence_sufficient is False
    assert report.confidence_cap == 0.60
    assert model_answer.confidence == 0.60
    assert model_answer.requires_human_review is True


def test_well_grounded_binding_legal_answer_retains_high_but_bounded_confidence() -> None:
    model_answer = answer(
        confidence=0.99,
        legal=section("applicable", ["law-1", "law-2"]),
    )
    report = assess_and_calibrate_grounded_answer(
        request("Mevzuata göre bu zorunlu mu?", ["legal"]),
        model_answer,
        [
            evidence("law-1", "legal", authority="binding"),
            evidence("law-2", "legal", authority="binding"),
        ],
    )

    assert report.blockers == []
    assert report.binding_legal_count == 2
    assert report.evidence_coverage_pct == 100.0
    assert report.evidence_sufficient is True
    assert report.confidence_cap == 0.92
    assert model_answer.confidence == 0.92
