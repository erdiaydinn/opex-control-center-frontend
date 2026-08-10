from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_verification import LegalVerificationStore, VerificationCreate


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
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/01/test.htm",
            authoritative_text="Resmi mevzuat metni test icerigi " * 4,
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 2),
            official_gazette_number="12345",
        )
    )
    assert record.decision == "pending"
    assert len(record.content_sha256) == 64


def test_verification_cannot_be_decided_twice(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/01/test.htm",
            authoritative_text="Resmi mevzuat metni test icerigi " * 4,
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 1),
        )
    )
    store.decide(record.id, "verified", "checked")
    with pytest.raises(ValueError, match="verification_not_pending"):
        store.decide(record.id, "rejected", "second decision")
