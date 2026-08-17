from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.grounded_chat import grounded_chat
from app.main import ChatRequest, Evidence


def operational_evidence() -> Evidence:
    return Evidence(
        id="ops-1",
        layer="operational",
        title="NSFR observation",
        excerpt="Refund and PFR deterioration increased the observed NSFR result.",
        source_name="ops-kpi",
        source_url=None,
        effective_from=date(2026, 8, 17),
        effective_to=None,
        authority_level="operational",
        score=0.92,
    )


def legal_evidence() -> Evidence:
    return Evidence(
        id="law-1",
        layer="legal",
        title="Verified legal obligation",
        excerpt="The verified legal instrument contains the applicable obligation.",
        source_name="official-law",
        source_url="https://www.resmigazete.gov.tr/example",
        effective_from=date(2026, 8, 1),
        effective_to=None,
        authority_level="binding",
        score=0.95,
    )


def answer_payload(*, layer: str, citation: str) -> dict:
    insufficient = {
        "status": "insufficient",
        "summary": "No finding requested from this authority layer.",
        "citations": [],
    }
    payload = {
        "answer": "The conclusion is limited to the supplied evidence.",
        "legal": dict(insufficient),
        "company": dict(insufficient),
        "standards": dict(insufficient),
        "operational": dict(insufficient),
        "recommendation": "Use the supplied evidence and do not exceed its scope.",
        "risk": "medium",
        "confidence": 0.80,
        "requires_human_review": False,
    }
    key = "standards" if layer == "standard" else layer
    payload[key] = {
        "status": "supported",
        "summary": "Supported by retrieved evidence.",
        "citations": [citation],
    }
    return payload


@pytest.mark.asyncio
async def test_operational_question_does_not_run_legal_temporal_resolution(
    monkeypatch,
) -> None:
    import app.grounded_chat as gc

    monkeypatch.setenv("EAY_ENVIRONMENT", "test")
    monkeypatch.setenv("EAY_GROUNDED_CRITIC_ENABLED", "0")
    calls = []

    def search(query, as_of, layers, limit):
        calls.append((query, tuple(layers), limit))
        assert layers == ["operational"]
        return [operational_evidence()]

    def temporal_must_not_run(as_of):
        raise AssertionError("operational question must not activate legal temporal resolver")

    async def chat_json(*, system, user, schema, model=None):
        assert "EVIDENCE_ACTIVE_LAYERS: operational" in user
        return answer_payload(layer="operational", citation="ops-1"), {
            "prompt_eval_count": 10,
            "eval_count": 5,
        }

    saved = {}
    monkeypatch.setattr(gc.store, "search", search)
    monkeypatch.setattr(gc.store, "save_interaction", lambda **kwargs: saved.update(kwargs))
    monkeypatch.setattr(gc.store, "create_low_confidence_candidate", lambda interaction_id: None)
    monkeypatch.setattr(gc.temporal_resolver, "resolve", temporal_must_not_run)
    monkeypatch.setattr(gc.ollama, "chat_json", chat_json)
    monkeypatch.setattr(gc, "_provenance_for_evidence", lambda *args, **kwargs: [])

    response = await grounded_chat(
        ChatRequest(
            message="NSFR neden yükseldi?",
            as_of=date(2026, 8, 17),
        )
    )

    assert calls
    assert response.evidence_plan is not None
    assert response.evidence_plan.active_layers == ["operational"]
    assert response.evidence_plan.legal_temporal_resolution_required is False
    assert response.temporal_resolution_fingerprint is None
    assert response.conflicts == []
    assert saved["evidence"][0].id == "ops-1"


@pytest.mark.asyncio
async def test_legal_question_cannot_bypass_temporal_resolution(monkeypatch) -> None:
    import app.grounded_chat as gc

    monkeypatch.setenv("EAY_ENVIRONMENT", "test")
    monkeypatch.setenv("EAY_GROUNDED_CRITIC_ENABLED", "0")
    temporal_calls = []

    def search(query, as_of, layers, limit):
        assert layers == ["legal"]
        return [legal_evidence()]

    def resolve(as_of):
        temporal_calls.append(as_of)
        return SimpleNamespace(
            resolved=True,
            as_of=as_of.isoformat(),
            resolution_fingerprint="temporal-verified-1",
            active_instrument_ids=("law-source-1",),
            blockers=(),
        )

    async def chat_json(*, system, user, schema, model=None):
        assert "EVIDENCE_ACTIVE_LAYERS: legal" in user
        assert "LEGAL_TEMPORAL_RESOLUTION: temporal-verified-1" in user
        return answer_payload(layer="legal", citation="law-1"), {
            "prompt_eval_count": 12,
            "eval_count": 6,
        }

    audit_calls = []
    monkeypatch.setattr(gc.store, "search", search)
    monkeypatch.setattr(gc.store, "save_interaction", lambda **kwargs: None)
    monkeypatch.setattr(gc.store, "create_low_confidence_candidate", lambda interaction_id: None)
    monkeypatch.setattr(gc.temporal_resolver, "resolve", resolve)
    monkeypatch.setattr(
        gc,
        "_filter_temporally_active_legal_evidence",
        lambda evidence, state: evidence,
    )
    monkeypatch.setattr(gc.ollama, "chat_json", chat_json)
    monkeypatch.setattr(gc, "_provenance_for_evidence", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        gc.legal_interaction_audit,
        "record",
        lambda **kwargs: audit_calls.append(kwargs)
        or SimpleNamespace(audit_fingerprint="audit-1"),
    )

    response = await grounded_chat(
        ChatRequest(
            message="Bu mevzuata göre yasal olarak zorunlu mu?",
            as_of=date(2026, 8, 17),
        )
    )

    assert temporal_calls == [date(2026, 8, 17)]
    assert response.evidence_plan is not None
    assert response.evidence_plan.active_layers == ["legal"]
    assert response.evidence_plan.legal_temporal_resolution_required is True
    assert response.temporal_resolution_fingerprint == "temporal-verified-1"
    assert response.legal_audit_fingerprint == "audit-1"
    assert len(audit_calls) == 1
