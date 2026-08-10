from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_verification import LegalVerificationStore, VerificationCreate


EXACT_TEXT = "20 Mayıs 2026 Resmî Gazete Sayı : 33259 MADDE 1 Amaç ve kapsam MADDE 2 Dayanak"


def seed_draft(engine: LegalEngine):
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="tgk-test",
            title="Test Regulation",
            instrument_type="regulation",
            source_url="https://www.resmigazete.gov.tr/",
            verification_status="draft",
        )
    )


def test_verification_rejects_non_authoritative_source(tmp_path):
    with pytest.raises(ValueError):
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://example.com/law",
            authoritative_text="x" * 40,
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 1),
        )


def test_verification_hash_and_pending_state(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
            authoritative_text=EXACT_TEXT,
            publication_date=date(2026, 5, 20),
            effective_from=date(2026, 5, 20),
            official_gazette_number="33259",
        )
    )
    assert record.decision == "pending"
    assert len(record.content_sha256) == 64
    assert record.authority_level == "binding_candidate_unverified"
    assert len(record.authority_assessment_fingerprint) == 64


def test_verification_cannot_be_decided_twice(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
            authoritative_text=EXACT_TEXT,
            publication_date=date(2026, 5, 20),
            effective_from=date(2026, 5, 20),
        )
    )
    verified = store.decide(record.id, "verified", "LEGAL-APPROVAL-1")
    assert verified.promotion_decision_fingerprint
    with pytest.raises(ValueError, match="verification_not_pending"):
        store.decide(record.id, "rejected", "second decision")


def test_verification_rejects_non_exact_resmi_gazete_text(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
            authoritative_text="Resmî Gazete duyuru metni ama MADDE yapısı yoktur ve yalnızca haber niteliğindedir.",
            publication_date=date(2026, 5, 20),
            effective_from=date(2026, 5, 20),
        )
    )
    assert record.authority_level == "discovery_signal"
    with pytest.raises(ValueError, match="exact_binding_instrument_candidate_required"):
        store.verify_and_apply(record.id, "checked", human_approval_ref="LEGAL-APPROVAL-2")


def test_relation_intent_requires_existing_non_draft_target(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    with pytest.raises(KeyError, match="related_instrument_not_found"):
        LegalVerificationStore(db).create(
            VerificationCreate(
                instrument_id="tgk-test",
                authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
                authoritative_text=EXACT_TEXT,
                publication_date=date(2026, 5, 20),
                effective_from=date(2026, 5, 20),
                relation_type="amends",
                related_instrument_id="missing-target",
            )
        )
