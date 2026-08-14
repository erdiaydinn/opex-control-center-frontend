from datetime import date

from app.legal_engine import LegalEngine, LegalInstrumentUpsert
from app.legal_relations import LegalRelationStore
from app.legal_temporal import LegalTemporalResolver


def _instrument(engine: LegalEngine, instrument_id: str, effective_from: date):
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


def test_supersedes_switches_active_version_on_source_effective_date(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "version-1", date(2026, 1, 1))
    _instrument(engine, "version-2", date(2026, 6, 1))
    relations = LegalRelationStore(db)
    relation = relations.propose(
        source_instrument_id="version-2",
        relation_type="supersedes",
        target_instrument_id="version-1",
        evidence_ref="verification:2:promotion:abc",
    )
    relations.decide(relation.id, decision="approved", reviewer_ref="LEGAL-REVIEW-1")

    resolver = LegalTemporalResolver(db)
    may = resolver.resolve(date(2026, 5, 31))
    assert may.resolved is True
    assert may.active_instrument_ids == ("version-1",)

    june = resolver.resolve(date(2026, 6, 1))
    assert june.resolved is True
    assert june.active_instrument_ids == ("version-2",)
    assert june.inactive_instrument_ids == ("version-1",)
    assert june.applied_relation_ids == (relation.id,)
    assert len(june.resolution_fingerprint) == 64


def test_amends_keeps_both_verified_instruments_temporally_active(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "base", date(2026, 1, 1))
    _instrument(engine, "amendment", date(2026, 4, 1))
    relations = LegalRelationStore(db)
    relation = relations.propose(
        source_instrument_id="amendment",
        relation_type="amends",
        target_instrument_id="base",
        evidence_ref="verification:amendment:promotion:def",
    )
    relations.decide(relation.id, decision="approved", reviewer_ref="LEGAL-REVIEW-2")

    state = LegalTemporalResolver(db).resolve(date(2026, 4, 1))
    assert state.resolved is True
    assert state.active_instrument_ids == ("amendment", "base")
    assert state.inactive_instrument_ids == ()


def test_approved_relation_cycle_fails_closed(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "node-a", date(2026, 1, 1))
    _instrument(engine, "node-b", date(2026, 2, 1))
    relations = LegalRelationStore(db)
    first = relations.propose(
        source_instrument_id="node-a",
        relation_type="amends",
        target_instrument_id="node-b",
        evidence_ref="evidence-a",
    )
    second = relations.propose(
        source_instrument_id="node-b",
        relation_type="amends",
        target_instrument_id="node-a",
        evidence_ref="evidence-b",
    )
    relations.decide(first.id, decision="approved", reviewer_ref="LEGAL-REVIEW-3")
    relations.decide(second.id, decision="approved", reviewer_ref="LEGAL-REVIEW-4")

    state = LegalTemporalResolver(db).resolve(date(2026, 3, 1))
    assert state.resolved is False
    assert state.active_instrument_ids == ()
    assert "approved_legal_relation_cycle" in state.blockers


def test_multiple_superseders_of_same_target_fail_closed(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "old", date(2026, 1, 1))
    _instrument(engine, "new-a", date(2026, 5, 1))
    _instrument(engine, "new-b", date(2026, 5, 2))
    relations = LegalRelationStore(db)
    for source, evidence, reviewer in (
        ("new-a", "ev-a", "LEGAL-A"),
        ("new-b", "ev-b", "LEGAL-B"),
    ):
        relation = relations.propose(
            source_instrument_id=source,
            relation_type="supersedes",
            target_instrument_id="old",
            evidence_ref=evidence,
        )
        relations.decide(relation.id, decision="approved", reviewer_ref=reviewer)

    state = LegalTemporalResolver(db).resolve(date(2026, 6, 1))
    assert state.resolved is False
    assert state.active_instrument_ids == ()
    assert any(item.startswith("ambiguous_multiple_superseders:old:") for item in state.blockers)


def test_missing_temporal_metadata_fails_closed_even_for_historical_status(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "good", date(2026, 1, 1))
    with engine._connect() as conn:
        conn.execute(
            """
            INSERT INTO legal_instruments(
                id, title, instrument_type, jurisdiction, publication_date,
                effective_from, effective_to, transition_deadline,
                official_gazette_number, source_url, verification_status,
                amends_json, repeals_json, topics_json, notes, updated_at
            ) VALUES (?, ?, ?, 'TR', NULL, NULL, NULL, NULL, NULL, ?, 'repealed', '[]', '[]', '[]', NULL, ?)
            """,
            (
                "legacy-bad",
                "legacy-bad",
                "regulation",
                "https://www.resmigazete.gov.tr/",
                "2026-01-01T00:00:00+00:00",
            ),
        )

    state = LegalTemporalResolver(db).resolve(date(2026, 2, 1))
    assert state.resolved is False
    assert "missing_effective_from:legacy-bad" in state.blockers
