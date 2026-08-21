from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_knowledge import LegalKnowledgeIndexer
from app.legal_verification import LegalVerificationStore, VerificationCreate
from app.main import Store


def _draft(engine: LegalEngine) -> None:
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="tgk-test",
            title="Türk Gıda Kodeksi Test Yönetmeliği",
            instrument_type="regulation",
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 1),
            source_url="https://www.resmigazete.gov.tr/test",
            verification_status="draft",
            amends=["old-test"],
            repeals=["older-test"],
            topics=["etiketleme", "gıda"],
            notes="original metadata",
        )
    )


def _exact_text(body: str) -> str:
    return "1 Ocak 2026 Resmî Gazete Sayı : 99999\n" + body


def test_only_verified_instrument_can_enter_legal_knowledge(tmp_path: Path):
    db = tmp_path / "eay.db"
    Store(db)
    engine = LegalEngine(db)
    _draft(engine)
    indexer = LegalKnowledgeIndexer(db)

    with pytest.raises(ValueError, match="instrument_not_verified"):
        indexer.sync_verified("tgk-test")


def test_verified_text_is_hashed_chunked_and_searchable(tmp_path: Path):
    db = tmp_path / "eay.db"
    knowledge = Store(db)
    engine = LegalEngine(db)
    _draft(engine)
    verification = LegalVerificationStore(db)

    authoritative_text = _exact_text("""BİRİNCİ BÖLÜM
Amaç ve kapsam

MADDE 1
Bu Yönetmeliğin amacı gıda etiketleme kurallarını belirlemektir.

MADDE 2
İşletmeciler zorunlu bilgileri tüketiciye sunar.
""")
    record = verification.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/test",
            authoritative_text=authoritative_text,
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 2, 1),
            official_gazette_number="99999",
        )
    )
    verification.verify_and_apply(
        record.id,
        "verified in test",
        human_approval_ref="LEGAL-TEST-002",
    )

    indexer = LegalKnowledgeIndexer(db)
    chunks = indexer.sync_verified("tgk-test")
    expected_hash = hashlib.sha256(authoritative_text.encode("utf-8")).hexdigest()

    assert chunks
    assert all(chunk.content_sha256 == expected_hash for chunk in chunks)
    assert all(chunk.verification_id == record.id for chunk in chunks)
    assert all(chunk.source_url.startswith("https://www.resmigazete.gov.tr/") for chunk in chunks)

    results = knowledge.search(
        "gıda etiketleme",
        as_of=date(2026, 3, 1),
        layers=["legal"],
        limit=5,
    )
    assert results
    assert results[0].authority_level == "binding"
    assert results[0].id.startswith("legal:tgk-test:")
    assert expected_hash in results[0].excerpt

    before_effective = knowledge.search(
        "gıda etiketleme",
        as_of=date(2026, 1, 15),
        layers=["legal"],
        limit=5,
    )
    assert before_effective == []


def test_verification_preserves_relationship_metadata(tmp_path: Path):
    db = tmp_path / "eay.db"
    Store(db)
    engine = LegalEngine(db)
    _draft(engine)
    verification = LegalVerificationStore(db)

    record = verification.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/test",
            authoritative_text=_exact_text("MADDE 1\nBu yeterince uzun ve resmi test metnidir."),
            publication_date=date(2026, 1, 1),
            effective_from=date(2026, 1, 2),
            official_gazette_number="99999",
        )
    )
    verification.verify_and_apply(
        record.id,
        "relationship metadata test",
        human_approval_ref="LEGAL-TEST-003",
    )

    with verification._connect() as conn:
        row = conn.execute("SELECT * FROM legal_instruments WHERE id='tgk-test'").fetchone()

    assert row is not None
    assert 'old-test' in row["amends_json"]
    assert 'older-test' in row["repeals_json"]
    assert 'etiketleme' in row["topics_json"]
    assert row["verification_status"] == "verified"
