from __future__ import annotations

import json
from pathlib import Path

from app.regulatory import SourceDefinition, _host_allowed
from app.regulatory_authority import assess_regulatory_authority

CONFIG_PATH = Path(__file__).parents[1] / "config" / "regulatory_sources.json"

REQUIRED_RETAIL_SIGNALS = {
    "perakende", "tüketici", "6502", "fiyat etiketi", "mesafeli sözleşmeler",
    "ticari reklam", "elektronik ticaret", "6563", "kişisel veri", "6698",
    "iş sağlığı ve güvenliği", "6331",
}


def _source(source_id: str) -> SourceDefinition:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source = next(item for item in payload["sources"] if item["id"] == source_id)
    return SourceDefinition.model_validate(source)


def test_resmi_gazete_watch_covers_food_and_core_retail_legal_signals() -> None:
    source = _source("tr-resmi-gazete")
    assert source.role == "binding_publication_index"
    assert _host_allowed(str(source.url))
    assert REQUIRED_RETAIL_SIGNALS <= set(source.keywords)
    assert "gıda" in source.keywords
    assert "tüketici hukuku" in source.topics
    assert "elektronik ticaret" in source.topics
    assert "kişisel veri" in source.topics


def test_resmi_gazete_index_signal_never_becomes_binding_law() -> None:
    source = _source("tr-resmi-gazete")
    assessment = assess_regulatory_authority(
        source,
        document_url=str(source.url),
        text="Resmî Gazete ana sayfa tüketici elektronik ticaret ve fiyat etiketi duyuruları",
    )
    assert assessment.authority_level == "discovery_signal"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True


def test_exact_resmi_gazete_shape_is_still_unverified_candidate() -> None:
    source = _source("tr-resmi-gazete")
    assessment = assess_regulatory_authority(
        source,
        document_url="https://www.resmigazete.gov.tr/eskiler/2026/08/20260814-1.htm",
        text=("14 Ağustos 2026 Resmî Gazete Sayı : 33100 "
              "MADDE 1 - Bu Yönetmeliğin amacı tüketici işlemlerinde uygulanacak esasları düzenlemektir."),
    )
    assert assessment.authority_level == "binding_candidate_unverified"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True


def test_commerce_ministry_consumer_registry_is_official_but_non_binding() -> None:
    source = _source("tr-ticaret-consumer-law-registry")
    assert source.role == "official_registry"
    assert _host_allowed(str(source.url))
    assert {"6502", "fiyat etiketi", "mesafeli sözleşmeler", "ticari reklam"} <= set(source.keywords)
    assessment = assess_regulatory_authority(
        source,
        document_url=str(source.url),
        text="6502 Sayılı Tüketicinin Korunması Mevzuatı Fiyat Etiketi Yönetmeliği Mesafeli Sözleşmeler Yönetmeliği",
    )
    assert assessment.authority_level == "discovery_signal"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True


def test_commerce_ministry_allowlist_does_not_open_arbitrary_hosts() -> None:
    assert _host_allowed("https://ticaret.gov.tr/tuketici/mevzuat/6502-sayili-tuketicinin-korunmasi-mevzuati")
    assert _host_allowed("https://tuketici.ticaret.gov.tr/yayinlar/mevzuat-kanun-yonetmelik-teblig/6502-sayili-tuketicinin-korunmasi-mevzuati")
    assert not _host_allowed("https://ticaret.gov.tr.example.com/evil")
    assert not _host_allowed("https://example.com/ticaret.gov.tr/evil")
