from pathlib import Path

import pytest

from app.regulatory import RegulatoryWatcher, SourceDefinition, _host_allowed


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
    assert "etiket" in [item.casefold() for item in changed.relevance_hits]

    rows = watcher.store.list_changes("pending", 10)
    assert len(rows) == 1
    assert rows[0].requires_binding_verification is True


def test_unrelated_site_chrome_change_does_not_alert(tmp_path: Path):
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
    assert watcher.store.list_changes("pending", 10) == []


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
