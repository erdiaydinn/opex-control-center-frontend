from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_relations import LegalRelationStore
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


def seed_verified_target(engine: LegalEngine):
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id="old-rule",
            title="Existing Verified Regulation",
            instrument_type="regulation",
            publication_date=date(2025, 1, 1),
            effective_from=date(2025, 1, 1),
            source_url="https://www.resmigazete.gov.tr/eskiler/2025/01/20250101-1.htm",
            verification_status="verified",
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


def test_verified_promotion_stages_relation_as_pending_in_same_workflow(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    seed_verified_target(engine)
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
            authoritative_text=EXACT_TEXT,
            publication_date=date(2026, 5, 20),
            effective_from=date(2026, 5, 20),
            relation_type="amends",
            related_instrument_id="old-rule",
        )
    )

    verified = store.verify_and_apply(
        record.id, "checked", human_approval_ref="LEGAL-APPROVAL-REL-1"
    )

    assert verified.decision == "verified"
    assert verified.relation_record_id
    assert len(verified.relation_fingerprint or "") == 64
    assert verified.promotion_decision_fingerprint
    with store._connect() as conn:
        relation = conn.execute(
            "SELECT * FROM legal_instrument_relations WHERE id = ?",
            (verified.relation_record_id,),
        ).fetchone()
    assert relation is not None
    assert relation["source_instrument_id"] == "tgk-test"
    assert relation["target_instrument_id"] == "old-rule"
    assert relation["relation_type"] == "amends"
    assert relation["status"] == "pending"
    assert relation["reviewer_ref"] is None
    assert record.id in relation["evidence_ref"]
    assert verified.promotion_decision_fingerprint in relation["evidence_ref"]


def test_relation_conflict_rolls_back_legal_promotion_atomically(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    seed_draft(engine)
    seed_verified_target(engine)
    relations = LegalRelationStore(db)
    relations.propose(
        source_instrument_id="tgk-test",
        relation_type="amends",
        target_instrument_id="old-rule",
        evidence_ref="preexisting-different-evidence",
    )
    store = LegalVerificationStore(db)
    record = store.create(
        VerificationCreate(
            instrument_id="tgk-test",
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2026/05/20260520-1.htm",
            authoritative_text=EXACT_TEXT,
            publication_date=date(2026, 5, 20),
            effective_from=date(2026, 5, 20),
            relation_type="amends",
            related_instrument_id="old-rule",
        )
    )

    with pytest.raises(ValueError, match="immutable_legal_relation_conflict"):
        store.verify_and_apply(
            record.id, "checked", human_approval_ref="LEGAL-APPROVAL-REL-2"
        )

    with store._connect() as conn:
        instrument = conn.execute(
            "SELECT verification_status FROM legal_instruments WHERE id='tgk-test'"
        ).fetchone()
        verification = conn.execute(
            "SELECT decision, promotion_decision_fingerprint, relation_record_id FROM legal_verifications WHERE id = ?",
            (record.id,),
        ).fetchone()
    assert instrument is not None and instrument["verification_status"] == "draft"
    assert verification is not None and verification["decision"] == "pending"
    assert verification["promotion_decision_fingerprint"] is None
    assert verification["relation_record_id"] is None
