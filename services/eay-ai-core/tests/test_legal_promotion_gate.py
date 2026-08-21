import hashlib
from datetime import date

from app.legal_promotion_gate import LegalPromotionCandidate, evaluate_legal_promotion
from app.regulatory import SourceDefinition
from app.regulatory_authority import assess_regulatory_authority


def _assessment():
    source = SourceDefinition(
        id="rg-source",
        name="Resmi Gazete",
        url="https://www.resmigazete.gov.tr/",
        role="binding_publication_index",
    )
    return assess_regulatory_authority(
        source,
        document_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
        text="20 Mayıs 2026 Resmî Gazete Sayı : 33259 MADDE 1 Amaç MADDE 2 Dayanak",
    )


def _candidate(**overrides):
    text = "20 Mayıs 2026 Resmî Gazete Sayı : 33259 MADDE 1 Amaç MADDE 2 Dayanak"
    payload = dict(
        instrument_id="tgk-test",
        authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
        authoritative_text=text,
        expected_content_sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
        publication_date=date(2026, 5, 20),
        effective_from=date(2026, 5, 20),
        authority_assessment=_assessment(),
        relation_type="new",
        related_instrument_id=None,
        human_approval_ref="LEGAL-2026-001",
    )
    payload.update(overrides)
    return LegalPromotionCandidate(**payload)


def test_exact_candidate_with_human_approval_can_pass_gate_but_never_auto_promotes():
    decision = evaluate_legal_promotion(_candidate())
    assert decision.eligible is True
    assert decision.blockers == ()
    assert decision.auto_promote is False
    assert decision.requires_human_action is True
    assert len(decision.decision_fingerprint) == 64


def test_hash_mismatch_fails_closed():
    decision = evaluate_legal_promotion(_candidate(expected_content_sha256="0" * 64))
    assert decision.eligible is False
    assert "authoritative_text_hash_mismatch" in decision.blockers


def test_non_authoritative_host_fails_closed():
    decision = evaluate_legal_promotion(_candidate(authoritative_url="https://example.com/rule"))
    assert decision.eligible is False
    assert "authoritative_source_host_not_allowed" in decision.blockers


def test_human_approval_is_mandatory():
    decision = evaluate_legal_promotion(_candidate(human_approval_ref=None))
    assert decision.eligible is False
    assert "human_approval_required" in decision.blockers


def test_amendment_requires_relation_target():
    decision = evaluate_legal_promotion(_candidate(relation_type="amends", related_instrument_id=None))
    assert decision.eligible is False
    assert "related_instrument_required" in decision.blockers


def test_invalid_temporal_order_fails_closed():
    decision = evaluate_legal_promotion(
        _candidate(publication_date=date(2026, 5, 20), effective_from=date(2026, 5, 19))
    )
    assert decision.eligible is False
    assert "effective_date_before_publication" in decision.blockers
