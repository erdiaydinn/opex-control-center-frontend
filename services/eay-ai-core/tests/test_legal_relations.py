from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_relations import LegalRelationStore


def _instrument(engine: LegalEngine, *, instrument_id: str, status: str):
    verified = status == "verified"
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id=instrument_id,
            title=f"Instrument {instrument_id}",
            instrument_type="regulation",
            publication_date=date(2026, 1, 1) if verified else None,
            effective_from=date(2026, 1, 1) if verified else None,
            source_url=(
                "https://www.resmigazete.gov.tr/eskiler/2026/01/example.htm"
                if verified
                else "https://www.tarimorman.gov.tr/GKGM/example"
            ),
            verification_status=status,
        )
    )


def test_relation_proposal_is_pending_and_idempotent(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, instrument_id="old-rule", status="verified")
    _instrument(engine, instrument_id="new-rule", status="draft")
    store = LegalRelationStore(db)

    first = store.propose(
        source_instrument_id="new-rule",
        relation_type="amends",
        target_instrument_id="old-rule",
        evidence_ref="RG-2026-001-MADDE-7",
    )
    second = store.propose(
        source_instrument_id="new-rule",
        relation_type="amends",
        target_instrument_id="old-rule",
        evidence_ref="RG-2026-001-MADDE-7",
    )
    assert first.status == "pending"
    assert first.id == second.id
    assert len(first.relation_fingerprint) == 64


def test_relation_rejects_self_reference_and_draft_target(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, instrument_id="draft-a", status="draft")
    _instrument(engine, instrument_id="draft-b", status="draft")
    store = LegalRelationStore(db)

    with pytest.raises(ValueError, match="self_reference"):
        store.propose(
            source_instrument_id="draft-a",
            relation_type="repeals",
            target_instrument_id="draft-a",
            evidence_ref="RG-1",
        )
    with pytest.raises(ValueError, match="target_must_not_be_draft"):
        store.propose(
            source_instrument_id="draft-a",
            relation_type="repeals",
            target_instrument_id="draft-b",
            evidence_ref="RG-1",
        )


def test_relation_cannot_be_approved_before_source_verification(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, instrument_id="old-rule", status="verified")
    _instrument(engine, instrument_id="new-rule", status="draft")
    store = LegalRelationStore(db)
    record = store.propose(
        source_instrument_id="new-rule",
        relation_type="supersedes",
        target_instrument_id="old-rule",
        evidence_ref="RG-2026-009",
    )
    with pytest.raises(ValueError, match="verified_source_instrument_required"):
        store.decide(record.id, decision="approved", reviewer_ref="LEGAL-TEAM-1")


def test_verified_source_relation_requires_human_reviewer_and_does_not_mutate_target(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, instrument_id="old-rule", status="verified")
    _instrument(engine, instrument_id="new-rule", status="verified")
    store = LegalRelationStore(db)
    record = store.propose(
        source_instrument_id="new-rule",
        relation_type="repeals",
        target_instrument_id="old-rule",
        evidence_ref="RG-2026-010-MADDE-12",
    )
    with pytest.raises(ValueError, match="reviewer_required"):
        store.decide(record.id, decision="approved", reviewer_ref="")

    approved = store.decide(record.id, decision="approved", reviewer_ref="LEGAL-TEAM-2")
    assert approved.status == "approved"
    assert approved.reviewer_ref == "LEGAL-TEAM-2"
    assert store.approved_targets("new-rule")[0].target_instrument_id == "old-rule"

    # Relationship approval is evidence, not an automatic repeal/status mutation.
    with store._connect() as conn:
        target = conn.execute(
            "SELECT verification_status FROM legal_instruments WHERE id='old-rule'"
        ).fetchone()
    assert target["verification_status"] == "verified"
