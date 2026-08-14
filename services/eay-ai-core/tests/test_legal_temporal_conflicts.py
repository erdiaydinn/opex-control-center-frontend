from datetime import date

import pytest

from app.legal_engine import LegalEngine, LegalInstrumentUpsert, LegalRequirementUpsert
from app.legal_relations import LegalRelationStore
from app.legal_temporal_conflicts import TemporalConflictEngine, TemporalResolutionBlocked


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


def _legal_requirement(engine: LegalEngine, req_id: str, source_id: str, max_temp: float):
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id=req_id,
            authority="legal",
            source_id=source_id,
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=max_temp,
            unit="C",
        )
    )


def _company_requirement(engine: LegalEngine, max_temp: float):
    engine.upsert_requirement(
        LegalRequirementUpsert(
            id="company-temp",
            authority="company",
            source_id="company-standard",
            scope="chilled-storage",
            dimension="max_temperature_c",
            operator="<=",
            numeric_value=max_temp,
            unit="C",
        )
    )


def test_conflict_engine_uses_historical_version_before_and_after_supersession(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "temp-rule-v1", date(2026, 1, 1))
    _instrument(engine, "temp-rule-v2", date(2026, 7, 1))
    _legal_requirement(engine, "legal-v1", "temp-rule-v1", 8)
    _legal_requirement(engine, "legal-v2", "temp-rule-v2", 4)
    _company_requirement(engine, 6)

    relations = LegalRelationStore(db)
    relation = relations.propose(
        source_instrument_id="temp-rule-v2",
        relation_type="supersedes",
        target_instrument_id="temp-rule-v1",
        evidence_ref="verification:v2:promotion:hash",
    )
    relations.decide(relation.id, decision="approved", reviewer_ref="LEGAL-REVIEW-1")

    conflicts = TemporalConflictEngine(db)
    june, june_fp = conflicts.compare_company_to_law(date(2026, 6, 30))
    assert len(june_fp) == 64
    assert len(june) == 1
    assert june[0].legal_requirement_id == "legal-v1"
    assert june[0].status == "company_stricter"

    july, july_fp = conflicts.compare_company_to_law(date(2026, 7, 1))
    assert len(july_fp) == 64
    assert len(july) == 1
    assert july[0].legal_requirement_id == "legal-v2"
    assert july[0].status == "company_weaker_conflict"


def test_conflict_engine_blocks_when_temporal_graph_is_ambiguous(tmp_path):
    db = tmp_path / "eay.db"
    engine = LegalEngine(db)
    _instrument(engine, "base-rule", date(2026, 1, 1))
    _instrument(engine, "replacement-a", date(2026, 5, 1))
    _instrument(engine, "replacement-b", date(2026, 5, 2))
    _company_requirement(engine, 6)

    relations = LegalRelationStore(db)
    for source in ("replacement-a", "replacement-b"):
        relation = relations.propose(
            source_instrument_id=source,
            relation_type="supersedes",
            target_instrument_id="base-rule",
            evidence_ref=f"evidence:{source}",
        )
        relations.decide(relation.id, decision="approved", reviewer_ref=f"REVIEW:{source}")

    with pytest.raises(TemporalResolutionBlocked) as exc:
        TemporalConflictEngine(db).compare_company_to_law(date(2026, 6, 1))
    assert any(item.startswith("ambiguous_multiple_superseders:base-rule:") for item in exc.value.blockers)
    assert len(exc.value.resolution_fingerprint) == 64
