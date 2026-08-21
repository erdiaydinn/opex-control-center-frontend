from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from app.grounded_critic import (
    CRITIC_CONTRACT,
    apply_critic_constraints,
    build_critic_prompt,
    normalize_critic_report,
    should_run_grounded_critic,
    unavailable_critic_report,
)


def request(message: str):
    return SimpleNamespace(message=message, as_of=date(2026, 8, 17))


def quality(*, sufficient=True, layers=None):
    return SimpleNamespace(
        evidence_sufficient=sufficient,
        required_layers=list(layers or []),
        model_dump=lambda mode="json": {
            "evidence_sufficient": sufficient,
            "required_layers": list(layers or []),
        },
    )


def answer(*, confidence=0.82, risk="low"):
    return SimpleNamespace(
        confidence=confidence,
        risk=risk,
        requires_human_review=False,
        model_dump=lambda mode="json": {
            "answer": "Evidence-bound candidate",
            "confidence": confidence,
            "risk": risk,
        },
    )


def test_critic_skips_when_evidence_is_not_sufficient(monkeypatch) -> None:
    monkeypatch.setenv("EAY_GROUNDED_CRITIC_ENABLED", "1")
    assert should_run_grounded_critic(
        request("Mevzuata göre zorunlu mu?"),
        answer(confidence=0.95),
        quality(sufficient=False, layers=["legal"]),
    ) is False


def test_critic_runs_for_legal_company_high_risk_and_complex_queries(monkeypatch) -> None:
    monkeypatch.setenv("EAY_GROUNDED_CRITIC_ENABLED", "1")
    assert should_run_grounded_critic(
        request("Bu mevzuata göre zorunlu mu?"),
        answer(),
        quality(layers=["legal"]),
    ) is True
    assert should_run_grounded_critic(
        request("Şirket politikamız ne diyor?"),
        answer(),
        quality(layers=["company"]),
    ) is True
    assert should_run_grounded_critic(
        request("Bu operasyon kararını uygulayalım mı?"),
        answer(risk="high"),
        quality(layers=["operational"]),
    ) is True
    assert should_run_grounded_critic(
        request("NSFR neden yükseldi, kök neden nedir?"),
        answer(),
        quality(layers=["operational"]),
    ) is True


def test_critic_feature_flag_can_disable_second_pass(monkeypatch) -> None:
    monkeypatch.setenv("EAY_GROUNDED_CRITIC_ENABLED", "0")
    assert should_run_grounded_critic(
        request("Bu mevzuata göre zorunlu mu?"),
        answer(confidence=0.99),
        quality(layers=["legal"]),
    ) is False


def test_verifier_can_never_raise_confidence() -> None:
    report = normalize_critic_report(
        {
            "verdict": "PASS",
            "issue_codes": [],
            "confidence_cap": 0.99,
            "requires_human_review": False,
            "revision_instructions": [],
        },
        current_confidence=0.81,
    )
    assert report.contract == CRITIC_CONTRACT
    assert report.confidence_cap == 0.81


def test_pass_with_issues_is_downgraded_to_revise() -> None:
    report = normalize_critic_report(
        {
            "verdict": "PASS",
            "issue_codes": ["citation_gap"],
            "confidence_cap": 0.8,
            "requires_human_review": False,
            "revision_instructions": ["Attach the supported evidence ID."],
        },
        current_confidence=0.9,
    )
    assert report.verdict == "REVISE"


def test_reject_is_human_review_and_max_half_confidence() -> None:
    report = normalize_critic_report(
        {
            "verdict": "REJECT",
            "issue_codes": ["legal_overclaim"],
            "confidence_cap": 0.9,
            "requires_human_review": False,
            "revision_instructions": ["Remove the unsupported legal conclusion."],
        },
        current_confidence=0.88,
    )
    assert report.requires_human_review is True
    assert report.confidence_cap == 0.5


def test_unavailable_high_assurance_critic_fails_closed() -> None:
    report = unavailable_critic_report(current_confidence=0.91, high_assurance=True)
    assert report.verdict == "UNAVAILABLE"
    assert report.confidence_cap == 0.65
    assert report.requires_human_review is True

    model_answer = answer(confidence=0.91)
    apply_critic_constraints(model_answer, report)
    assert model_answer.confidence == 0.65
    assert model_answer.requires_human_review is True


def test_critic_prompt_contains_observable_inputs_not_reasoning_request() -> None:
    prompt = build_critic_prompt(
        request=request("NSFR neden yükseldi?"),
        answer=answer(),
        evidence_text="ID: ops-1\nLAYER: OPERATIONAL",
        decision_quality=quality(layers=["operational"]),
    )
    lowered = prompt.lower()
    assert "retrieved evidence" in lowered
    assert "candidate answer json" in lowered
    assert "deterministic decision quality json" in lowered
    assert "do not reveal hidden reasoning" in lowered
