from __future__ import annotations

from datetime import date

import pytest

from app.legal_registry_discovery import RegistryDiscoveryCandidate, load_consumer_registry_manifest
from app.legal_registry_verification_intake import build_registry_bound_verification_intake


def _candidate():
    manifest = load_consumer_registry_manifest()
    instrument = manifest.instruments[0]
    candidate = RegistryDiscoveryCandidate(
        instrument_key=instrument.key,
        title=instrument.title,
        registry_url=str(manifest.registry_url),
        registry_manifest_fingerprint=manifest.manifest_fingerprint,
        expected_registry_target_url=str(instrument.registry_target_url),
        discovered_url=str(instrument.registry_target_url),
        discovered_host="www.mevzuat.gov.tr",
    )
    return candidate, manifest


def _build(**overrides):
    candidate, manifest = _candidate()
    kwargs = {
        "authoritative_url": "https://www.resmigazete.gov.tr/eskiler/2013/11/20131128-1.htm",
        "authoritative_text": "6502 exact publication text",
        "publication_date": date(2013, 11, 28),
        "effective_from": date(2014, 5, 28),
        "official_gazette_number": "28835",
    }
    kwargs.update(overrides)
    return build_registry_bound_verification_intake(candidate, manifest, **kwargs)


def test_registry_intake_is_non_promoting_and_content_bound():
    intake = _build()
    assert intake.human_review_required is True
    assert intake.promotion_eligible is False
    assert intake.auto_promote is False
    assert len(intake.exact_binding_content_sha256) == 64
    assert len(intake.intake_fingerprint) == 64


def test_registry_intake_requires_exact_resmi_gazete_source():
    with pytest.raises(ValueError, match="exact_resmi_gazete_source_required"):
        _build(authoritative_url="https://www.mevzuat.gov.tr/mevzuatmetin/1.5.6502.pdf")


def test_registry_intake_rejects_effective_date_before_publication():
    with pytest.raises(ValueError, match="effective_date_before_publication"):
        _build(effective_from=date(2013, 11, 27))


def test_registry_intake_rejects_manifest_substitution():
    candidate, manifest = _candidate()
    tampered = candidate.model_copy(update={"registry_manifest_fingerprint": "0" * 64})
    with pytest.raises(ValueError, match="manifest_fingerprint_mismatch"):
        build_registry_bound_verification_intake(
            tampered,
            manifest,
            authoritative_url="https://www.resmigazete.gov.tr/eskiler/2013/11/20131128-1.htm",
            authoritative_text="exact publication text",
            publication_date=date(2013, 11, 28),
            effective_from=date(2014, 5, 28),
        )


def test_registry_intake_fingerprint_changes_with_publication_text():
    original = _build(authoritative_text="publication text v1")
    changed = _build(authoritative_text="publication text v2")
    assert original.exact_binding_content_sha256 != changed.exact_binding_content_sha256
    assert original.intake_fingerprint != changed.intake_fingerprint
