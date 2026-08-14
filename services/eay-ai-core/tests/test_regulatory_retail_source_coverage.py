from __future__ import annotations

import json
from pathlib import Path

from app.regulatory import SourceDefinition, _host_allowed
from app.regulatory_authority import assess_regulatory_authority

CONFIG_PATH = Path(__file__).parents[1] / "config" / "regulatory_sources.json"

REQUIRED_RETAIL_SIGNALS = {
    "perakende",
    "tüketici",
    "6502",
    "fiyat etiketi",
    "mesafeli sözleşmeler",
    "ticari reklam",
    "elektronik ticaret",
    "6563",
    "kişisel veri",
    "6698",
    "iş sağlığı ve güvenliği",
    "6331",
}


def _resmi_gazete_source() -> SourceDefinition:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    source = next(item for item in payload["sources"] if item["id"] == "tr-resmi-gazete")
    return SourceDefinition.model_validate(source)


def test_resmi_gazete_watch_covers_food_and_core_retail_legal_signals() -> None:
    source = _resmi_gazete_source()
    assert source.role == "binding_publication_index"
    assert _host_allowed(str(source.url))
    assert REQUIRED_RETAIL_SIGNALS <= set(source.keywords)
    assert "gıda" in source.keywords
    assert "tüketici hukuku" in source.topics
    assert "elektronik ticaret" in source.topics
    assert "kişisel veri" in source.topics


def test_resmi_gazete_index_signal_never_becomes_binding_law() -> None:
    source = _resmi_gazete_source()
    assessment = assess_regulatory_authority(
        source,
        document_url=str(source.url),
        text="Resmî Gazete ana sayfa tüketici elektronik ticaret ve fiyat etiketi duyuruları",
    )
    assert assessment.authority_level == "discovery_signal"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True


def test_exact_resmi_gazete_shape_is_still_unverified_candidate() -> None:
    source = _resmi_gazete_source()
    assessment = assess_regulatory_authority(
        source,
        document_url="https://www.resmigazete.gov.tr/eskiler/2026/08/20260814-1.htm",
        text=(
            "14 Ağustos 2026 Resmî Gazete Sayı : 33100 "
            "MADDE 1 - Bu Yönetmeliğin amacı tüketici işlemlerinde uygulanacak esasları düzenlemektir."
        ),
    )
    assert assessment.authority_level == "binding_candidate_unverified"
    assert assessment.auto_promotable_to_binding is False
    assert assessment.exact_binding_verification_required is True
