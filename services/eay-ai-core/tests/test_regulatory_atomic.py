import sqlite3

import pytest

from app.regulatory import RegulatoryStore
from app.regulatory_atomic import AtomicRegulatoryPersistence
from app.regulatory_lineage import RegulatoryLineageStore


def _authority() -> dict[str, object]:
    return {
        "authority_level": "discovery_signal",
        "assessment_fingerprint": "f" * 64,
        "reasons": ["official announcement only"],
    }


def test_baseline_snapshot_and_lineage_commit_together(tmp_path):
    db = tmp_path / "eay.db"
    RegulatoryStore(db)
    atomic = AtomicRegulatoryPersistence(db)

    result = atomic.persist_observation(
        source_id="tr-gkgm-test",
        source_name="GKGM test",
        source_url="https://www.tarimorman.gov.tr/GKGM/",
        source_role="discovery",
        jurisdiction="TR",
        content_hash="a" * 64,
        content_text="baseline regulatory text",
        expected_previous_hash=None,
        observed_at="2026-08-10T19:00:00+00:00",
    )

    with sqlite3.connect(db) as conn:
        snapshot_count = conn.execute("SELECT COUNT(*) FROM regulatory_snapshots").fetchone()[0]
        lineage_count = conn.execute("SELECT COUNT(*) FROM regulatory_evidence_lineage").fetchone()[0]
    assert snapshot_count == 1
    assert lineage_count == 1
    assert len(result.snapshot_chain_hash) == 64
    assert result.change_id is None


def test_relevant_change_snapshot_authority_change_and_lineage_are_one_commit(tmp_path):
    db = tmp_path / "eay.db"
    RegulatoryStore(db)
    atomic = AtomicRegulatoryPersistence(db)
    atomic.persist_observation(
        source_id="tr-gkgm-test",
        source_name="GKGM test",
        source_url="https://www.tarimorman.gov.tr/GKGM/",
        source_role="discovery",
        jurisdiction="TR",
        content_hash="a" * 64,
        content_text="baseline regulatory text",
        expected_previous_hash=None,
        observed_at="2026-08-10T19:00:00+00:00",
    )

    result = atomic.persist_observation(
        source_id="tr-gkgm-test",
        source_name="GKGM test",
        source_url="https://www.tarimorman.gov.tr/GKGM/",
        source_role="discovery",
        jurisdiction="TR",
        content_hash="b" * 64,
        content_text="changed regulatory text",
        expected_previous_hash="a" * 64,
        diff_excerpt="+ etiket mevzuatı değişikliği",
        relevance_hits=["etiket"],
        authority_assessment=_authority(),
        observed_at="2026-08-10T19:05:00+00:00",
    )

    with sqlite3.connect(db) as conn:
        conn.row_factory = sqlite3.Row
        change = conn.execute("SELECT * FROM regulatory_changes WHERE id=?", (result.change_id,)).fetchone()
    assert change is not None
    assert change["authority_fingerprint"] == "f" * 64
    assert change["lineage_chain_hash"] == result.change_chain_hash
    chain = RegulatoryLineageStore(db).verify_source_chain("tr-gkgm-test")
    assert chain["verified"] is True
    assert chain["record_count"] == 3


def test_stale_head_fails_before_any_partial_write(tmp_path):
    db = tmp_path / "eay.db"
    RegulatoryStore(db)
    atomic = AtomicRegulatoryPersistence(db)
    atomic.persist_observation(
        source_id="tr-gkgm-test",
        source_name="GKGM test",
        source_url="https://www.tarimorman.gov.tr/GKGM/",
        source_role="discovery",
        jurisdiction="TR",
        content_hash="a" * 64,
        content_text="baseline regulatory text",
        expected_previous_hash=None,
    )

    with pytest.raises(ValueError, match="stale_regulatory_observation_head"):
        atomic.persist_observation(
            source_id="tr-gkgm-test",
            source_name="GKGM test",
            source_url="https://www.tarimorman.gov.tr/GKGM/",
            source_role="discovery",
            jurisdiction="TR",
            content_hash="c" * 64,
            content_text="stale observation",
            expected_previous_hash="b" * 64,
            diff_excerpt="+ stale",
            relevance_hits=["etiket"],
            authority_assessment=_authority(),
        )

    with sqlite3.connect(db) as conn:
        snapshots = conn.execute("SELECT COUNT(*) FROM regulatory_snapshots").fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM regulatory_changes").fetchone()[0]
        lineage = conn.execute("SELECT COUNT(*) FROM regulatory_evidence_lineage").fetchone()[0]
    assert snapshots == 1
    assert changes == 0
    assert lineage == 1


def test_lineage_failure_rolls_back_snapshot_and_change(monkeypatch, tmp_path):
    db = tmp_path / "eay.db"
    RegulatoryStore(db)
    atomic = AtomicRegulatoryPersistence(db)
    atomic.persist_observation(
        source_id="tr-gkgm-test",
        source_name="GKGM test",
        source_url="https://www.tarimorman.gov.tr/GKGM/",
        source_role="discovery",
        jurisdiction="TR",
        content_hash="a" * 64,
        content_text="baseline regulatory text",
        expected_previous_hash=None,
    )

    original = RegulatoryLineageStore.append_with_connection.__func__

    def fail_on_change(cls, conn, **kwargs):
        if kwargs["record_type"] == "change":
            raise RuntimeError("simulated_lineage_failure")
        return original(cls, conn, **kwargs)

    monkeypatch.setattr(
        RegulatoryLineageStore,
        "append_with_connection",
        classmethod(fail_on_change),
    )
    with pytest.raises(RuntimeError, match="simulated_lineage_failure"):
        atomic.persist_observation(
            source_id="tr-gkgm-test",
            source_name="GKGM test",
            source_url="https://www.tarimorman.gov.tr/GKGM/",
            source_role="discovery",
            jurisdiction="TR",
            content_hash="b" * 64,
            content_text="changed regulatory text",
            expected_previous_hash="a" * 64,
            diff_excerpt="+ etiket",
            relevance_hits=["etiket"],
            authority_assessment=_authority(),
        )

    with sqlite3.connect(db) as conn:
        snapshots = conn.execute("SELECT COUNT(*) FROM regulatory_snapshots").fetchone()[0]
        changes = conn.execute("SELECT COUNT(*) FROM regulatory_changes").fetchone()[0]
        lineage = conn.execute("SELECT COUNT(*) FROM regulatory_evidence_lineage").fetchone()[0]
    assert snapshots == 1
    assert changes == 0
    assert lineage == 1
