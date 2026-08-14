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
    assert len(manifest.manifest_fingerprint) == 64
    assert {item.key for item in manifest.instruments} == {
        "tr-law-6502-consumer-protection",
        "tr-reg-price-label",
        "tr-reg-distance-contracts",
        "tr-reg-commercial-advertising-unfair-practices",
    }
    assert all(item.binding_source_required is True for item in manifest.instruments)
    assert all(
        str(item.registry_target_url).startswith("https://www.mevzuat.gov.tr/")
        for item in manifest.instruments
    )


def test_registry_html_resolution_matches_real_ministry_row_shape_but_stays_discovery_only() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = """
    <html><body>
      <div>6502 SAYILI TÜKETİCİNİN KORUNMASI HAKKINDA KANUN | 
        <a href="https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6502.pdf">İNDİR</a>
      </div>
      <div>FİYAT ETİKETİ YÖNETMELİĞİ | 
        <a href="https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19819&amp;MevzuatTertip=5&amp;MevzuatTur=7">İNDİR</a>
      </div>
      <div>MESAFELİ SÖZLEŞMELER YÖNETMELİĞİ | 
        <a href="https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=20237&amp;MevzuatTertip=5&amp;MevzuatTur=7">İNDİR</a>
      </div>
      <div>TİCARİ REKLAM VE HAKSIZ TİCARİ UYGULAMALAR YÖNETMELİĞİ | 
        <a href="https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=20435&amp;MevzuatTertip=5&amp;MevzuatTur=7">İNDİR</a>
      </div>
    </body></html>
    """

    candidates = resolve_priority_registry_links(html, manifest)
    assert len(candidates) == 4
    assert {item.registry_manifest_fingerprint for item in candidates} == {
        manifest.manifest_fingerprint
    }
    assert all(item.registry_target_match is True for item in candidates)
    assert all(item.discovered_url_is_binding_host is True for item in candidates)
    assert all(item.discovery_only is True for item in candidates)
    assert all(item.binding_verified is False for item in candidates)
    assert all(item.promotion_eligible is False for item in candidates)
    assert all(item.requires_exact_binding_source is True for item in candidates)


def test_registry_manifest_fingerprint_changes_when_priority_contract_changes() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    baseline = ConsumerRegistryManifest.model_validate(payload)
    payload["instruments"][0]["topics"].append("new-reviewed-topic")
    changed = ConsumerRegistryManifest.model_validate(payload)

    assert changed.manifest_fingerprint != baseline.manifest_fingerprint


def test_registry_title_matching_normalizes_nbsp_and_whitespace() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = """
    <div>FİYAT\u00a0ETİKETİ   YÖNETMELİĞİ | 
      <a href="https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19819&amp;MevzuatTertip=5&amp;MevzuatTur=7">İNDİR</a>
    </div>
    """

    candidates = resolve_priority_registry_links(html, manifest)
    assert [item.instrument_key for item in candidates] == ["tr-reg-price-label"]


def test_registry_target_drift_fails_closed_for_review() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    html = """
    <div>FİYAT ETİKETİ YÖNETMELİĞİ | 
      <a href="https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=99999&amp;MevzuatTertip=5&amp;MevzuatTur=7">İNDİR</a>
    </div>
    """

    with pytest.raises(ValueError, match="consumer_registry_target_drift:tr-reg-price-label"):
        resolve_priority_registry_links(html, manifest)


def test_ambiguous_duplicate_title_fails_closed() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    target = str(next(item for item in manifest.instruments if item.key == "tr-reg-price-label").registry_target_url)
    html = f"""
    <div>FİYAT ETİKETİ YÖNETMELİĞİ | <a href="{target}">İNDİR</a></div>
    <div>FİYAT ETİKETİ YÖNETMELİĞİ | <a href="{target}">İNDİR</a></div>
    """

    with pytest.raises(ValueError, match="ambiguous_consumer_registry_title"):
        resolve_priority_registry_links(html, manifest)


def test_unsafe_or_non_official_discovery_urls_are_rejected() -> None:
    manifest = load_consumer_registry_manifest(CONFIG_PATH)
    with pytest.raises(ValueError, match="requires_http_https"):
        resolve_priority_registry_links(
            '<div>FİYAT ETİKETİ YÖNETMELİĞİ | <a href="javascript:alert(1)">İNDİR</a></div>',
            manifest,
        )

    with pytest.raises(ValueError, match="must_not_contain_userinfo"):
        resolve_priority_registry_links(
            '<div>FİYAT ETİKETİ YÖNETMELİĞİ | <a href="https://user:pass@ticaret.gov.tr/x">İNDİR</a></div>',
            manifest,
        )

    with pytest.raises(ValueError, match="requires_official_target_host"):
        resolve_priority_registry_links(
            '<div>FİYAT ETİKETİ YÖNETMELİĞİ | <a href="https://attacker.example/fake.pdf">İNDİR</a></div>',
            manifest,
        )


def test_registry_manifest_rejects_host_suffix_spoof_duplicate_titles_and_target_host() -> None:
    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["registry_url"] = "https://ticaret.gov.tr.attacker.example/registry"
    with pytest.raises(ValidationError, match="exact_ticaret_gov_tr_host"):
        ConsumerRegistryManifest.model_validate(payload)

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["instruments"].append(dict(payload["instruments"][0], key="different-key"))
    with pytest.raises(ValidationError, match="duplicate_consumer_registry_title"):
        ConsumerRegistryManifest.model_validate(payload)

    payload = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    payload["instruments"][0]["registry_target_url"] = "https://attacker.example/fake.pdf"
    with pytest.raises(ValidationError, match="target_requires_official_host"):
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
