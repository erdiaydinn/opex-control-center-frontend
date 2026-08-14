from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.legal_registry_discovery import (
    ConsumerRegistryManifest,
    load_consumer_registry_manifest,
    resolve_priority_registry_links,
)
from app.legal_verification import VerificationCreate


CONFIG_PATH = Path(__file__).parents[1] / "config" / "tr_consumer_legal_registry.json"


def test_priority_consumer_registry_manifest_is_pinned_and_complete() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)

    assert str(manifest.registry_url).startswith("https://ticaret.gov.tr/")
    assert manifest.registry_role == "official_registry_discovery"
    assert {item.key for item in manifest.instruments} == {
        "tr-law-6502-consumer-protection",
        "tr-reg-price-label",
        "tr-reg-distance-contracts",
        "tr-reg-commercial-advertising-unfair-practices",
    }
    assert all(item.binding_source_required is True for item in manifest.instruments)


def test_registry_html_resolution_is_discovery_only_even_for_resmi_gazete_link() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = """
    <html><body>
      <a href="https://www.resmigazete.gov.tr/eskiler/2013/11/20131128-1.htm">
        6502 SAYILI TÜKETİCİNİN KORUNMASI HAKKINDA KANUN
      </a>
      <a href="/consumer/download/fiyat-etiketi.pdf">FİYAT ETİKETİ YÖNETMELİĞİ</a>
      <a href="/consumer/download/mesafeli.pdf">MESAFELİ SÖZLEŞMELER YÖNETMELİĞİ</a>
      <a href="/consumer/download/reklam.pdf">
        TİCARİ REKLAM VE HAKSIZ TİCARİ UYGULAMALAR YÖNETMELİĞİ
      </a>
    </body></html>
    """

    candidates = resolve_priority_registry_links(html, manifest)
    assert len(candidates) == 4
    law = next(item for item in candidates if item.instrument_key == "tr-law-6502-consumer-protection")
    assert law.discovered_url_is_binding_host is True
    assert law.discovery_only is True
    assert law.binding_verified is False
    assert law.promotion_eligible is False
    assert law.requires_exact_binding_source is True


def test_registry_title_matching_normalizes_nbsp_and_whitespace() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = '<a href="/x">FİYAT\u00a0ETİKETİ   YÖNETMELİĞİ</a>'

    candidates = resolve_priority_registry_links(html, manifest)
    assert [item.instrument_key for item in candidates] == ["tr-reg-price-label"]


def test_ambiguous_duplicate_title_fails_closed() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = """
    <a href="/a">FİYAT ETİKETİ YÖNETMELİĞİ</a>
    <a href="/b">FİYAT ETİKETİ YÖNETMELİĞİ</a>
    """

    with pytest.raises(ValueError, match="ambiguous_consumer_registry_title"):
        resolve_priority_registry_links(html, manifest)


def test_javascript_or_userinfo_discovery_urls_are_rejected() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    with pytest.raises(ValueError, match="requires_http_https"):
        resolve_priority_registry_links(
            '<a href="javascript:alert(1)">FİYAT ETİKETİ YÖNETMELİĞİ</a>',
            manifest,
        )

    with pytest.raises(ValueError, match="must_not_contain_userinfo"):
        resolve_priority_registry_links(
            '<a href="https://user:pass@ticaret.gov.tr/x">FİYAT ETİKETİ YÖNETMELİĞİ</a>',
            manifest,
        )


def test_registry_manifest_rejects_host_suffix_spoof_and_duplicate_titles() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["registry_url"] = "https://ticaret.gov.tr.attacker.example/registry"
    with pytest.raises(ValidationError, match="exact_ticaret_gov_tr_host"):
        ConsumerRegistryManifest.model_validate(payload)

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["instruments"].append(dict(payload["instruments"][0], key="different-key"))
    with pytest.raises(ValidationError, match="duplicate_consumer_registry_title"):
        ConsumerRegistryManifest.model_validate(payload)


def test_commerce_ministry_registry_cannot_be_used_as_binding_verification_source() -> None:
    with pytest.raises(ValidationError, match="Resmi Gazete or Mevzuat Bilgi Sistemi"):
        VerificationCreate(
            instrument_id="consumer-law-test",
            authoritative_url=(
                "https://ticaret.gov.tr/tuketici/mevzuat/6502-sayili-tuketicinin-korunmasi-mevzuati"
            ),
            authoritative_text="Official registry index text is discovery evidence, not binding text.",
            publication_date=date(2026, 4, 2),
            effective_from=date(2026, 4, 2),
        )
