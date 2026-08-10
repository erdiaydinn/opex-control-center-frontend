from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

import pytest

from app.legal_engine import LegalEngine
from app.legal_review import (
    CandidateProposal,
    LegalReviewStore,
    PromoteDraftRequest,
)


def _seed_change(db_path, change_id="chg-1"):
    with sqlite3.connect(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS regulatory_changes (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_name TEXT NOT NULL,
                source_url TEXT NOT NULL,
                source_role TEXT NOT NULL,
                old_hash TEXT NOT NULL,
                new_hash TEXT NOT NULL,
                diff_excerpt TEXT NOT NULL,
                relevance_hits_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                requires_binding_verification INTEGER NOT NULL DEFAULT 1,
                detected_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO regulatory_changes(
                id, source_id, source_name, source_url, source_role,
                old_hash, new_hash, diff_excerpt, relevance_hits_json,
                status, requires_binding_verification, detected_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1, ?)
            """,
            (
                change_id,
                "tr-resmi-gazete",
                "T.C. Resmî Gazete",
                "https://www.resmigazete.gov.tr/",
                "binding_publication_index",
                "old",
                "new",
                "- eski metin\n+ yeni gıda kodeksi metni",
                '["gıda", "kodeksi"]',
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def test_candidate_preserves_raw_provenance_and_is_idempotent(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed_change(db_path)
    store = LegalReviewStore(db_path)

    first = store.create_from_change(
        CandidateProposal(
            change_id="chg-1",
            proposed_title="Türk Gıda Kodeksi Test Tebliği",
            proposed_instrument_type="communique",
            extraction_method="deterministic",
        )
    )
    second = store.create_from_change(CandidateProposal(change_id="chg-1"))

    assert first.id == second.id
    assert first.status == "pending_review"
    assert first.raw_diff == "- eski metin\n+ yeni gıda kodeksi metni"
    assert len(first.raw_diff_sha256) == 64
    assert first.source_role == "binding_publication_index"


def test_candidate_cannot_skip_review_gate(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed_change(db_path)
    store = LegalReviewStore(db_path)
    candidate = store.create_from_change(CandidateProposal(change_id="chg-1"))

    with pytest.raises(ValueError, match="candidate_not_approved_for_verification"):
        store.mark_promoted(candidate.id, "instrument-1")


def test_approved_candidate_promotes_only_to_draft_instrument(tmp_path):
    db_path = tmp_path / "eay.db"
    _seed_change(db_path)
    store = LegalReviewStore(db_path)
    engine = LegalEngine(db_path)
    candidate = store.create_from_change(CandidateProposal(change_id="chg-1"))
    approved = store.decide(candidate.id, "approved_for_verification", "reviewed")
    assert approved.status == "approved_for_verification"

    payload = PromoteDraftRequest(
        instrument_id="tgk-test-2026",
        title="Türk Gıda Kodeksi Test Tebliği",
        instrument_type="communique",
        source_url="https://www.resmigazete.gov.tr/",
        publication_date="2026-08-10",
        effective_from="2026-08-10",
    )
    engine.upsert_instrument(
        __import__("app.legal_engine", fromlist=["LegalInstrumentUpsert"]).LegalInstrumentUpsert(
            id=payload.instrument_id,
            title=payload.title,
            instrument_type=payload.instrument_type,
            source_url=payload.source_url,
            publication_date=payload.publication_date,
            effective_from=payload.effective_from,
            verification_status="draft",
            notes=f"candidate={candidate.id}; sha256={candidate.raw_diff_sha256}",
        )
    )
    store.mark_promoted(candidate.id, payload.instrument_id)

    promoted = store.get(candidate.id)
    assert promoted is not None
    assert promoted.status == "promoted_draft"
    assert promoted.promoted_instrument_id == "tgk-test-2026"
    # Draft instruments must never appear in the verified-as-of result set.
    assert engine.instruments_as_of(payload.effective_from) == []
