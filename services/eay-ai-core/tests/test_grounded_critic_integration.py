from __future__ import annotations

from datetime import date

import pytest

from app.grounded_chat import _apply_bounded_revision, _run_grounded_critic
from app.grounded_reasoning import assess_and_calibrate_grounded_answer
from app.main import ChatAnswer, ChatRequest, Evidence, LayerFinding


def evidence() -> list[Evidence]:
    return [
        Evidence(
            id="ops-1",
            layer="operational",
            title="NSFR daily observation",
            excerpt="NSFR increased after refund and PFR deterioration.",
            source_name="ops-kpi",
            source_url=None,
            effective_from=date(2026, 8, 17),
            effective_to=None,
            authority_level="operational",
            score=0.9,
        )
    ]


def request() -> ChatRequest:
    return ChatRequest(
        message="NSFR neden yükseldi? Kök neden ve öneri nedir?",
        as_of=date(2026, 8, 17),
        layers=["operational"],
    )


def payload(*, recommendation: str, confidence: float = 0.9) -> dict:
    insufficient = {
        "status": "insufficient",
        "summary": "Not requested from this evidence layer.",
        "citations": [],
    }
    return {
        "answer": "NSFR deterioration is visible in the supplied operational evidence.",
        "legal": insufficient,
        "company": insufficient,
        "standards": insufficient,
        "operational": {
            "status": "supported",
            "summary": "Refund and PFR deterioration are present.",
            "citations": ["ops-1"],
        },
        "recommendation": recommendation,
        "risk": "medium",
        "confidence": confidence,
        "requires_human_review": False,
    }


def answer() -> ChatAnswer:
    rows = evidence()
    return ChatAnswer(
        **payload(recommendation="Act immediately everywhere."),
        evidence=rows,
        model="test-model",
        prompt_tokens=10,
        output_tokens=10,
        interaction_id="interaction-1",
    )


@pytest.mark.asyncio
async def test_adaptive_critic_returns_observable_revise_verdict(monkeypatch) -> None:
    import app.grounded_chat as grounded_chat

    candidate = answer()
    quality = assess_and_calibrate_grounded_answer(request(), candidate, evidence())

    async def fake_chat_json(*, system, user, schema, model=None):
        assert "Verifier" in system
        assert "CANDIDATE ANSWER JSON" in user
        return (
            {
                "verdict": "REVISE",
                "issue_codes": ["ambiguous_recommendation"],
                "confidence_cap": 0.78,
                "requires_human_review": False,
                "revision_instructions": [
                    "Limit the recommendation to actions supported by ops-1."
                ],
            },
            {"prompt_eval_count": 20, "eval_count": 5},
        )

    monkeypatch.setattr(grounded_chat.ollama, "chat_json", fake_chat_json)
    critic, raw = await _run_grounded_critic(
        request=request(),
        answer=candidate,
        evidence=evidence(),
        decision_quality=quality,
    )

    assert critic.performed is True
    assert critic.verdict == "REVISE"
    assert critic.issue_codes == ["ambiguous_recommendation"]
    assert critic.confidence_cap == 0.78
    assert raw["prompt_eval_count"] == 20


@pytest.mark.asyncio
async def test_revision_is_bounded_and_revalidated_by_deterministic_guard(monkeypatch) -> None:
    import app.grounded_chat as grounded_chat

    rows = evidence()
    candidate = answer()
    critic = grounded_chat.GroundedCriticReport(
        performed=True,
        verdict="REVISE",
        issue_codes=["ambiguous_recommendation"],
        confidence_cap=0.78,
        revision_instructions=["Make the recommendation evidence-bound."],
    )
    calls = 0

    async def fake_chat_json(*, system, user, schema, model=None):
        nonlocal calls
        calls += 1
        assert "revising an existing evidence-bound answer" in system
        assert "VERIFIER RESULT JSON" in user
        return (
            payload(
                recommendation=(
                    "Validate the observed refund/PFR deterioration and investigate "
                    "the affected operational scope before intervention."
                ),
                confidence=0.76,
            ),
            {"prompt_eval_count": 25, "eval_count": 8},
        )

    monkeypatch.setattr(grounded_chat.ollama, "chat_json", fake_chat_json)
    revised, revised_quality, raw = await _apply_bounded_revision(
        request=request(),
        answer=candidate,
        evidence=rows,
        critic=critic,
        valid_ids={"ops-1"},
        has_legal=False,
        interaction_id="interaction-1",
    )

    assert calls == 1
    assert critic.revision_applied is True
    assert critic.revision_guard_passed is True
    assert revised_quality is not None
    assert revised_quality.evidence_sufficient is True
    assert revised.operational.citations == ["ops-1"]
    assert revised.recommendation.startswith("Validate the observed")
    assert raw["eval_count"] == 8


@pytest.mark.asyncio
async def test_failed_revision_never_loops_and_forces_review(monkeypatch) -> None:
    import app.grounded_chat as grounded_chat

    candidate = answer()
    critic = grounded_chat.GroundedCriticReport(
        performed=True,
        verdict="REVISE",
        issue_codes=["citation_gap"],
        confidence_cap=0.7,
        revision_instructions=["Repair citation coverage."],
    )
    calls = 0

    async def broken_chat_json(*, system, user, schema, model=None):
        nonlocal calls
        calls += 1
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(grounded_chat.ollama, "chat_json", broken_chat_json)
    returned, revised_quality, raw = await _apply_bounded_revision(
        request=request(),
        answer=candidate,
        evidence=evidence(),
        critic=critic,
        valid_ids={"ops-1"},
        has_legal=False,
        interaction_id="interaction-1",
    )

    assert calls == 1
    assert returned is candidate
    assert revised_quality is None
    assert raw == {}
    assert critic.revision_applied is False
    assert critic.revision_guard_passed is False
    assert critic.requires_human_review is True
    assert critic.confidence_cap == 0.4
