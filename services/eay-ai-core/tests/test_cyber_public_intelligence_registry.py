from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from app.cyber_public_intelligence_registry import (
    PublicIntelAuthMode,
    PublicIntelSource,
    assess_public_intel_source,
    load_public_intel_registry,
)

REGISTRY_PATH = Path(__file__).parents[1] / "config" / "cyber_public_intelligence_sources.json"


def registry():
    return load_public_intel_registry(REGISTRY_PATH)


def by_id(source_id: str) -> PublicIntelSource:
    return next(source for source in registry().sources if source.source_id == source_id)


def test_public_intel_registry_has_strong_independent_sources():
    value = registry()
    assert len(value.sources) >= 9
    assert len({source.source_id for source in value.sources}) == len(value.sources)
    assert len(value.fingerprint) == 64
    assert {
        "osv_dev",
        "cisa_vulnrichment",
        "cert_cc_vulnerability_notes",
        "enisa_euvd",
        "github_advisory_database",
        "cisa_cybersecurity_advisories",
        "abusech_threatfox",
        "abusech_urlhaus",
        "abusech_malwarebazaar_metadata",
    } <= {source.source_id for source in value.sources}


def test_all_public_sources_are_read_only_and_non_authoritative_for_eay():
    for source in registry().sources:
        assert source.server_side_only is True
        assert source.allowlisted_network_only is True
        assert source.read_only_queries_only is True
        assert source.sample_download_permitted is False
        assert source.indicator_submission_permitted is False
        assert source.company_exposure_authority is False
        assert source.incident_confirmation_authority is False
        assert source.production_mutation_permitted is False
        assert source.credential_capture_permitted is False
        assert source.exploit_generation_permitted is False
        assert source.execution_authority_granted is False
        assert len(source.fingerprint) == 64


def test_credential_free_feed_still_requires_verified_egress_allowlist():
    osv = by_id("osv_dev")
    held = assess_public_intel_source(osv)
    assert held.admitted_read_only is False
    assert held.blockers == ("egress_allowlist_verification_required",)

    admitted = assess_public_intel_source(osv, egress_allowlist_verified=True)
    assert admitted.admitted_read_only is True
    assert admitted.blockers == ()
    assert admitted.company_exposure_authority is False
    assert admitted.incident_confirmation_authority is False
    assert admitted.execution_authority_granted is False


def test_abusech_sources_require_terms_review_secret_and_egress():
    for source_id in (
        "abusech_threatfox",
        "abusech_urlhaus",
        "abusech_malwarebazaar_metadata",
    ):
        source = by_id(source_id)
        assert source.auth_mode is PublicIntelAuthMode.PROTECTED_SERVER_SECRET
        held = assess_public_intel_source(source)
        assert held.admitted_read_only is False
        assert held.blockers == (
            "terms_or_commercial_use_review_required",
            "protected_server_secret_required",
            "egress_allowlist_verification_required",
        )

        admitted = assess_public_intel_source(
            source,
            terms_review_passed=True,
            protected_secret_configured=True,
            egress_allowlist_verified=True,
        )
        assert admitted.admitted_read_only is True
        assert admitted.blockers == ()
        assert admitted.execution_authority_granted is False


def test_public_feed_cannot_be_relaxed_into_download_submission_or_execution():
    source = by_id("abusech_malwarebazaar_metadata")
    for field in (
        "sample_download_permitted",
        "indicator_submission_permitted",
        "company_exposure_authority",
        "incident_confirmation_authority",
        "production_mutation_permitted",
        "credential_capture_permitted",
        "exploit_generation_permitted",
        "execution_authority_granted",
    ):
        payload = source.model_dump(mode="json")
        payload[field] = True
        with pytest.raises(ValidationError):
            PublicIntelSource.model_validate(payload)


def test_public_feed_cannot_disable_read_only_or_network_boundary():
    source = by_id("osv_dev")
    for field in ("server_side_only", "allowlisted_network_only", "read_only_queries_only"):
        payload = source.model_dump(mode="json")
        payload[field] = False
        with pytest.raises(ValidationError):
            PublicIntelSource.model_validate(payload)
