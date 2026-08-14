import sqlite3

import pytest

from app.regulatory_lineage import RegulatoryLineageStore


def test_lineage_is_append_only_and_chained_per_source(tmp_path):
    store = RegulatoryLineageStore(tmp_path / "eay.db")
    first = store.append(
        record_type="snapshot",
        record_id="s1",
        source_id="tr-gkgm-home",
        content_hash="a" * 64,
        metadata={"origin": "watcher"},
        created_at="2026-08-10T10:00:00+00:00",
    )
    second = store.append(
        record_type="change",
        record_id="c1",
        source_id="tr-gkgm-home",
        content_hash="b" * 64,
        metadata={"authority_level": "discovery_signal"},
        created_at="2026-08-10T10:05:00+00:00",
    )
    assert second.parent_chain_hash == first.chain_hash
    result = store.verify_source_chain("tr-gkgm-home")
    assert result["verified"] is True
    assert result["record_count"] == 2
    assert result["head_chain_hash"] == second.chain_hash


def test_same_record_is_idempotent_but_mutation_is_rejected(tmp_path):
    store = RegulatoryLineageStore(tmp_path / "eay.db")
    original = store.append(
        record_type="snapshot",
        record_id="s1",
        source_id="tr-resmi-gazete",
        content_hash="a" * 64,
        metadata={"origin": "watcher"},
    )
    repeated = store.append(
        record_type="snapshot",
        record_id="s1",
        source_id="tr-resmi-gazete",
        content_hash="a" * 64,
        metadata={"origin": "watcher"},
    )
    assert repeated.chain_hash == original.chain_hash
    with pytest.raises(ValueError, match="immutable_regulatory_lineage_conflict"):
        store.append(
            record_type="snapshot",
            record_id="s1",
            source_id="tr-resmi-gazete",
            content_hash="b" * 64,
            metadata={"origin": "watcher"},
        )


def test_chain_verifier_detects_tampering(tmp_path):
    db = tmp_path / "eay.db"
    store = RegulatoryLineageStore(db)
    store.append(
        record_type="snapshot",
        record_id="s1",
        source_id="tr-gkgm-home",
        content_hash="a" * 64,
        metadata={"origin": "watcher"},
        created_at="2026-08-10T10:00:00+00:00",
    )
    store.append(
        record_type="snapshot",
        record_id="s2",
        source_id="tr-gkgm-home",
        content_hash="b" * 64,
        metadata={"origin": "watcher"},
        created_at="2026-08-10T10:01:00+00:00",
    )
    with sqlite3.connect(db) as conn:
        conn.execute(
            "UPDATE regulatory_evidence_lineage SET content_hash = ? WHERE record_id = 's1'",
            ("f" * 64,),
        )
    result = store.verify_source_chain("tr-gkgm-home")
    assert result["verified"] is False
    assert result["broken_record_id"] == "s1"


def test_append_with_connection_obeys_caller_rollback(tmp_path):
    db = tmp_path / "eay.db"
    store = RegulatoryLineageStore(db)
    conn = store._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        RegulatoryLineageStore.append_with_connection(
            conn,
            record_type="snapshot",
            record_id="rollback-snapshot",
            source_id="tr-gkgm-home",
            content_hash="c" * 64,
            metadata={"origin": "watcher-transaction"},
            created_at="2026-08-10T10:10:00+00:00",
        )
        conn.rollback()
    finally:
        conn.close()

    assert store.get("snapshot", "rollback-snapshot") is None
    assert store.verify_source_chain("tr-gkgm-home")["record_count"] == 0


def test_existing_watcher_rows_backfill_idempotently(tmp_path):
    db = tmp_path / "eay.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE regulatory_snapshots(
                id TEXT PRIMARY KEY, source_id TEXT, content_hash TEXT,
                content_text TEXT, fetched_at TEXT
            );
            CREATE TABLE regulatory_changes(
                id TEXT PRIMARY KEY, source_id TEXT, source_name TEXT,
                source_url TEXT, source_role TEXT, old_hash TEXT, new_hash TEXT,
                diff_excerpt TEXT, relevance_hits_json TEXT, status TEXT,
                requires_binding_verification INTEGER, detected_at TEXT
            );
            """
        )
        conn.execute(
            "INSERT INTO regulatory_snapshots VALUES (?, ?, ?, ?, ?)",
            ("s1", "tr-gkgm-home", "a" * 64, "text", "2026-08-10T10:00:00+00:00"),
        )
        conn.execute(
            "INSERT INTO regulatory_changes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "c1", "tr-gkgm-home", "GKGM", "https://www.tarimorman.gov.tr/GKGM/",
                "discovery", "a" * 64, "b" * 64, "diff", "[]", "pending", 1,
                "2026-08-10T10:05:00+00:00",
            ),
        )
    store = RegulatoryLineageStore(db)
    first = store.import_existing_watcher_rows()
    second = store.import_existing_watcher_rows()
    assert first == {"snapshots": 1, "changes": 1}
    assert second == {"snapshots": 0, "changes": 0}
    assert store.verify_source_chain("tr-gkgm-home")["verified"] is True
