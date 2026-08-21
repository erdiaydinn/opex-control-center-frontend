from datetime import date

import pytest
from fastapi import HTTPException

import app.grounded_chat as gc
from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_knowledge import LegalKnowledgeIndexer
from app.legal_relations import LegalRelationStore
from app.legal_temporal import LegalTemporalResolver
from app.main import Evidence, Store


def _verified(engine: LegalEngine, instrument_id: str, effective_from: date) -> None:
    engine.upsert_instrument(
        LegalInstrumentUpsert(
            id=instrument_id,
            title=instrument_id,
            instrument_type="regulation",
            publication_date=effective_from,
            effective_from=effective_from,
            source_url="https://www.resmigazete.gov.tr/eskiler/2026/01/20260101-1.htm",
            verification_status="verified",
        )
    )


def _evidence(doc_id: str, effective_from: date) -> Evidence:
    return Evidence(
        id=doc_id,
        layer="legal",
        title=doc_id,
        excerpt="verified legal text",
        source_name="Resmî Gazete",
        source_url="https://www.resmigazete.gov.tr/eskiler/2026/01/20260101-1.htm",
        effective_from=effective_from,
        effective_to=None,
        authority_level="binding",
        score=0.9,
    )


def _insert_legal_doc(db, *, doc_id: str, instrument_id: str, effective_from: date) -> None:
    LegalKnowledgeIndexer(db)
    with Store(db)._connect() as conn:
        now = "2026-08-10T20:00:00+00:00"
        conn.execute(
            """
            INSERT INTO legal_knowledge_chunks(
                id, instrument_id, verification_id, ordinal, heading,
                content_sha256, chunk_sha256, source_url, publication_date,
                effective_from, effective_to, text, created_at
            ) VALUES (?, ?, ?, 1, NULL, ?, ?, ?, ?, ?, NULL, ?, ?)
            """,
            (
                doc_id,
                instrument_id,
                f"verification-{instrument_id}",
                "a" * 64,
                "b" * 64,
                "https://www.resmigazete.gov.tr/eskiler/2026/01/20260101-1.htm",
                effective_from.isoformat(),
                effective_from.isoformat(),
                "verified legal text",
                now,
            ),
        )
        conn.execute(
            """
            INSERT INTO knowledge_documents(
                id, layer, title, content, source_name, source_url, jurisdiction,
                authority_level, effective_from, effective_to, version, updated_at
            ) VALUES (?, 'legal', ?, ?, 'Resmî Gazete', ?, 'TR', 'binding', ?, NULL, ?, ?)
            """,
            (
                doc_id,
                doc_id,
                "verified legal text",
                "https://www.resmigazete.gov.tr/eskiler/2026/01/20260101-1.htm",
                effective_from.isoformat(),
                "a" * 64,
                now,
            ),
        )


def test_grounded_retrieval_excludes_superseded_legal_chunk(tmp_path):
    db = tmp_path / "eay.db"
    Store(db)
    engine = LegalEngine(db)
    _verified(engine, "old-rule", date(2026, 1, 1))
    _verified(engine, "new-rule", date(2026, 6, 1))

    relations = LegalRelationStore(db)
    relation = relations.propose(
        source_instrument_id="new-rule",
        relation_type="supersedes",
        target_instrument_id="old-rule",
        evidence_ref="verification:new-rule:promotion:abc",
    )
    relations.decide(relation.id, decision="approved", reviewer_ref="LEGAL-RAG-1")

    _insert_legal_doc(db, doc_id="legal-old", instrument_id="old-rule", effective_from=date(2026, 1, 1))
    _insert_legal_doc(db, doc_id="legal-new", instrument_id="new-rule", effective_from=date(2026, 6, 1))

    gc.DB_PATH = db
    gc.temporal_resolver = LegalTemporalResolver(db)
    state = gc._resolve_temporal_state(date(2026, 6, 1))
    filtered = gc._filter_temporally_active_legal_evidence(
        [
            _evidence("legal-old", date(2026, 1, 1)),
            _evidence("legal-new", date(2026, 6, 1)),
        ],
        state,
    )
    assert [item.id for item in filtered] == ["legal-new"]

    provenance = gc._provenance_for_evidence(
        ["legal-new"],
        temporal_resolution_fingerprint=state.resolution_fingerprint,
    )
    assert provenance[0].source_id == "new-rule"
    assert provenance[0].temporal_resolution_fingerprint == state.resolution_fingerprint


def test_grounded_legal_resolution_blocks_ambiguous_cycle(tmp_path):
    db = tmp_path / "eay.db"
    Store(db)
    engine = LegalEngine(db)
    _verified(engine, "rule-a", date(2026, 1, 1))
    _verified(engine, "rule-b", date(2026, 2, 1))
    relations = LegalRelationStore(db)
    for source, target, reviewer in (
        ("rule-a", "rule-b", "LEGAL-CYCLE-A"),
        ("rule-b", "rule-a", "LEGAL-CYCLE-B"),
    ):
        relation = relations.propose(
            source_instrument_id=source,
            relation_type="amends",
            target_instrument_id=target,
            evidence_ref=f"verification:{source}:promotion:cycle",
        )
        relations.decide(relation.id, decision="approved", reviewer_ref=reviewer)

    gc.DB_PATH = db
    gc.temporal_resolver = LegalTemporalResolver(db)
    with pytest.raises(HTTPException) as exc:
        gc._resolve_temporal_state(date(2026, 3, 1))
    assert exc.value.status_code == 409
    assert exc.value.detail["error"] == "legal_temporal_resolution_blocked"
    assert "approved_legal_relation_cycle" in exc.value.detail["blockers"]
