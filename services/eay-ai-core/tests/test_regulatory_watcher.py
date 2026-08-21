import sqlite3
from pathlib import Path

import pytest

from app.regulatory import RegulatoryWatcher, SourceDefinition, _host_allowed
from app.regulatory_lineage import RegulatoryLineageStore


def _source() -> SourceDefinition:
    return SourceDefinition(
        id="test-gkgm",
        name="Test GKGM",
        url="https://www.tarimorman.gov.tr/GKGM/",
        role="discovery",
        keywords=["kodeks", "etiket"],
    )


def test_regulatory_baseline_unchanged_and_relevant_change(tmp_path: Path):
    sources_path = tmp_path / "sources.json"
    sources_path.write_text('{"sources": []}', encoding="utf-8")
    watcher = RegulatoryWatcher(tmp_path / "eay.db", sources_path)
    source = _source()

    first = watcher.process_text(
        source,
        "<html><body>" + ("Türk Gıda Kodeksi mevcut durum. " * 8) + "</body></html>",
    )
    assert first.state == "baseline"
    assert first.snapshot_id
    assert len(first.snapshot_chain_hash or "") == 64

    second = watcher.process_text(
        source,
        "<html><body>" + ("Türk Gıda Kodeksi mevcut durum. " * 8) + "</body></html>",
    )
    assert second.state == "unchanged"

    changed = watcher.process_text(
        source,
        "<html><body>"
        + ("Türk Gıda Kodeksi mevcut durum. " * 8)
        + " Etiket mevzuatında yeni düzenleme yayımlandı."
        + "</body></html>",
    )
    assert changed.state == "changed_relevant"
    assert changed.change_id
    assert changed.snapshot_id
    assert changed.authority_level == "discovery_signal"
    assert len(changed.authority_fingerprint or "") == 64
    assert len(changed.change_chain_hash or "") == 64
    assert "etiket" in [item.casefold() for item in changed.relevance_hits]

    rows = watcher.store.list_changes("pending", 10)
    assert len(rows) == 1
    assert rows[0].requires_binding_verification is True
    assert rows[0].authority_assessment["authority_level"] == "discovery_signal"
    assert rows[0].authority_fingerprint == changed.authority_fingerprint
    assert rows[0].lineage_chain_hash == changed.change_chain_hash

    chain = watcher.lineage.verify_source_chain(source.id)
    assert chain["verified"] is True
    assert chain["record_count"] == 3
    assert chain["head_chain_hash"] == changed.change_chain_hash


def test_unrelated_site_chrome_change_does_not_alert_but_is_lineaged(tmp_path: Path):
    sources_path = tmp_path / "sources.json"
    sources_path.write_text('{"sources": []}', encoding="utf-8")
    watcher = RegulatoryWatcher(tmp_path / "eay.db", sources_path)
    source = _source()

    watcher.process_text(source, "<html><body>" + ("Ana sayfa içerik A. " * 10) + "</body></html>")
    changed = watcher.process_text(
        source,
        "<html><body>" + ("Ana sayfa içerik A. " * 10) + " Footer tasarımı değişti.</body></html>",
    )
    assert changed.state == "changed_irrelevant"
    assert changed.snapshot_id
    assert len(changed.snapshot_chain_hash or "") == 64
    assert watcher.store.list_changes("pending", 10) == []
    chain = watcher.lineage.verify_source_chain(source.id)
    assert chain["verified"] is True
    assert chain["record_count"] == 2


def test_process_text_rolls_back_snapshot_change_and_lineage_together(tmp_path: Path, monkeypatch):
    db = tmp_path / "eay.db"
    sources_path = tmp_path / "sources.json"
    sources_path.write_text('{"sources": []}', encoding="utf-8")
    watcher = RegulatoryWatcher(db, sources_path)
    source = _source()

    watcher.process_text(
        source,
        "<html><body>" + ("Türk Gıda Kodeksi mevcut durum. " * 8) + "</body></html>",
    )

    original = RegulatoryLineageStore.append_with_connection.__func__

    def fail_on_change(cls, conn, **kwargs):
        if kwargs.get("record_type") == "change":
            raise RuntimeError("simulated_change_lineage_failure")
        return original(cls, conn, **kwargs)

    monkeypatch.setattr(
        RegulatoryLineageStore,
        "append_with_connection",
        classmethod(fail_on_change),
    )

    with pytest.raises(RuntimeError, match="simulated_change_lineage_failure"):
        watcher.process_text(
            source,
            "<html><body>"
            + ("Türk Gıda Kodeksi mevcut durum. " * 8)
            + " Etiket mevzuatında yeni düzenleme yayımlandı."
            + "</body></html>",
        )

    with sqlite3.connect(db) as conn:
        snapshot_count = conn.execute("SELECT COUNT(*) FROM regulatory_snapshots").fetchone()[0]
        change_count = conn.execute("SELECT COUNT(*) FROM regulatory_changes").fetchone()[0]
        lineage_count = conn.execute("SELECT COUNT(*) FROM regulatory_evidence_lineage").fetchone()[0]
    assert snapshot_count == 1
    assert change_count == 0
    assert lineage_count == 1
    assert watcher.lineage.verify_source_chain(source.id)["verified"] is True


def test_existing_database_gets_additive_authority_columns(tmp_path: Path):
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
    sources_path = tmp_path / "sources.json"
    sources_path.write_text('{"sources": []}', encoding="utf-8")
    RegulatoryWatcher(db, sources_path)
    with sqlite3.connect(db) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(regulatory_changes)")}
    assert {"authority_assessment_json", "authority_fingerprint", "lineage_chain_hash"} <= columns


def test_source_host_allowlist_blocks_arbitrary_urls():
    assert _host_allowed("https://www.tarimorman.gov.tr/GKGM/")
    assert _host_allowed("https://guvenilirgida.tarimorman.gov.tr/")
    assert _host_allowed("https://www.resmigazete.gov.tr/")
    assert _host_allowed("https://kms.kaysis.gov.tr/Home/Kurum/24308110")
    assert not _host_allowed("https://example.com/evil")
    assert not _host_allowed("http://tarimorman.gov.tr.example.com/evil")


def test_source_registry_rejects_unapproved_host(tmp_path: Path):
    sources_path = tmp_path / "sources.json"
    sources_path.write_text(
        '{"sources":[{"id":"bad","name":"Bad Source","url":"https://example.com/",'
        '"role":"discovery"}]}',
        encoding="utf-8",
    )
    watcher = RegulatoryWatcher(tmp_path / "eay.db", sources_path)
    with pytest.raises(ValueError):
        watcher.sources()
