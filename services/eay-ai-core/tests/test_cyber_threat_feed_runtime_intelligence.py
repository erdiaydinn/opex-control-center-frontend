from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.cyber_defense_intelligence import ThreatIntelligenceSource
from app.cyber_threat_feed_runtime import (
    CISA_KEV_JSON_ENDPOINT,
    MITRE_ATTACK_STIX_ENDPOINT,
    NVD_CVE_API_ENDPOINT,
    ThreatFeedBinding,
    ThreatFeedKind,
    ThreatFeedObservation,
    build_nvd_incremental_params,
    build_parallel_threat_feed_refresh_plan,
    default_threat_feed_bindings,
    ingest_threat_feed_payload,
)

NOW = datetime(2026, 8, 19, 18, tzinfo=UTC)


def _bindings():
    return default_threat_feed_bindings()


def _binding(kind: ThreatFeedKind):
    return next(item for item in _bindings() if item.kind is kind)


def _cisa_payload():
    return {
        "title": "CISA Known Exploited Vulnerabilities Catalog",
        "catalogVersion": "2026.08.19",
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-12345",
                "vendorProject": "Example Vendor",
                "product": "Example Gateway",
                "dateAdded": "2026-08-18",
                "cwes": ["CWE-79"],
                "knownRansomwareCampaignUse": "Unknown",
            }
        ],
    }


def _nvd_payload():
    return {
        "version": "2.0",
        "timestamp": "2026-08-19T17:55:00.000Z",
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-23456",
                    "published": "2026-08-17T10:00:00.000Z",
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.8}}
                        ]
                    },
                    "weaknesses": [
                        {"description": [{"lang": "en", "value": "CWE-78"}]}
                    ],
                }
            }
        ],
    }


def _mitre_payload():
    return {
        "type": "bundle",
        "spec_version": "2.1",
        "objects": [
            {
                "type": "attack-pattern",
                "id": "attack-pattern--11111111-1111-1111-1111-111111111111",
                "created": "2020-01-01T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1059"}
                ],
                "x_mitre_platforms": ["Windows", "Linux"],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--22222222-2222-2222-2222-222222222222",
                "created": "2020-01-01T00:00:00.000Z",
                "revoked": True,
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T9999"}
                ],
            },
        ],
    }


def test_default_feeds_are_exact_reviewed_read_only_sources() -> None:
    bindings = _bindings()
    assert {item.kind for item in bindings} == {
        ThreatFeedKind.CISA_KEV_JSON,
        ThreatFeedKind.NVD_CVE_API,
        ThreatFeedKind.MITRE_ATTACK_STIX,
    }
    endpoints = {item.endpoint_ref for item in bindings}
    assert endpoints == {
        CISA_KEV_JSON_ENDPOINT,
        NVD_CVE_API_ENDPOINT,
        MITRE_ATTACK_STIX_ENDPOINT,
    }
    for binding in bindings:
        assert binding.method == "GET"
        assert binding.read_only is True
        assert binding.raw_payload_retention_allowed is False
        assert binding.credential_material_retention_allowed is False
        assert binding.company_truth_authority_granted is False
        assert binding.incident_confirmation_granted is False
        assert binding.execution_authority_granted is False


def test_feed_endpoint_cannot_be_model_swapped() -> None:
    binding = _binding(ThreatFeedKind.CISA_KEV_JSON)
    tampered = binding.model_copy(update={"endpoint_ref": "https://example.invalid/feed.json"})
    with pytest.raises(ValidationError, match="cyber_feed_endpoint_not_reviewed"):
        ThreatFeedBinding.model_validate(tampered.model_dump(mode="json"))


def test_refresh_plan_fans_out_all_never_observed_feeds_in_parallel() -> None:
    plan = build_parallel_threat_feed_refresh_plan(
        bindings=_bindings(), last_success_by_feed={}, as_of=NOW
    )
    assert plan.may_run_in_parallel is True
    assert len(plan.due_feed_ids) == 3
    assert all(item.due for item in plan.candidates)
    assert plan.execution_authority_granted is False


def test_refresh_plan_respects_independent_feed_freshness() -> None:
    bindings = _bindings()
    last = {item.feed_id: NOW - timedelta(minutes=20) for item in bindings}
    plan = build_parallel_threat_feed_refresh_plan(
        bindings=bindings, last_success_by_feed=last, as_of=NOW
    )
    assert plan.due_feed_ids == ()

    cisa = _binding(ThreatFeedKind.CISA_KEV_JSON)
    last[cisa.feed_id] = NOW - timedelta(hours=2)
    plan = build_parallel_threat_feed_refresh_plan(
        bindings=bindings, last_success_by_feed=last, as_of=NOW
    )
    assert plan.due_feed_ids == (cisa.feed_id,)


def test_nvd_incremental_window_is_bounded_and_paginated() -> None:
    params = build_nvd_incremental_params(
        start_at=NOW - timedelta(days=1),
        end_at=NOW,
        start_index=2000,
        results_per_page=2000,
    )
    assert params["startIndex"] == 2000
    assert params["resultsPerPage"] == 2000
    assert str(params["lastModStartDate"]).endswith("Z")
    with pytest.raises(ValueError, match="cyber_feed_nvd_window_exceeds_120_days"):
        build_nvd_incremental_params(
            start_at=NOW - timedelta(days=121), end_at=NOW
        )


def test_cisa_kev_normalizes_known_exploited_record_without_company_claim() -> None:
    result = ingest_threat_feed_payload(
        binding=_binding(ThreatFeedKind.CISA_KEV_JSON),
        payload=_cisa_payload(),
        observed_at=NOW,
    )
    assert len(result.records) == 1
    record = result.records[0]
    assert record.source is ThreatIntelligenceSource.CISA_KEV
    assert record.cve_ids == ("CVE-2026-12345",)
    assert record.cwe_ids == ("CWE-79",)
    assert record.known_exploited_in_wild is True
    assert record.company_truth_granted is False
    assert record.incident_confirmation_granted is False
    assert result.observation.normalized_record_count == 1
    assert result.observation.raw_payload_retained is False
    assert result.observation.credential_material_retained is False


def test_nvd_normalizes_severity_and_cwe_but_never_invents_kev_truth() -> None:
    result = ingest_threat_feed_payload(
        binding=_binding(ThreatFeedKind.NVD_CVE_API),
        payload=_nvd_payload(),
        observed_at=NOW,
    )
    record = result.records[0]
    assert record.source is ThreatIntelligenceSource.NVD
    assert record.cve_ids == ("CVE-2026-23456",)
    assert record.cwe_ids == ("CWE-78",)
    assert record.severity_score == 9.8
    assert record.known_exploited_in_wild is False
    assert record.company_truth_granted is False


def test_mitre_stix_normalizes_active_techniques_and_skips_revoked() -> None:
    result = ingest_threat_feed_payload(
        binding=_binding(ThreatFeedKind.MITRE_ATTACK_STIX),
        payload=_mitre_payload(),
        observed_at=NOW,
    )
    assert len(result.records) == 1
    record = result.records[0]
    assert record.source is ThreatIntelligenceSource.MITRE_ATTACK
    assert record.attack_technique_ids == ("T1059",)
    assert set(record.product_refs) == {"platform:windows", "platform:linux"}


def test_future_dated_upstream_record_fails_closed() -> None:
    payload = _cisa_payload()
    payload["vulnerabilities"][0]["dateAdded"] = "2026-08-20"
    with pytest.raises(ValidationError, match="cyber_threat_recorded_at_predates_publication"):
        ingest_threat_feed_payload(
            binding=_binding(ThreatFeedKind.CISA_KEV_JSON),
            payload=payload,
            observed_at=NOW,
        )


def test_non_success_http_observation_is_not_ingested() -> None:
    with pytest.raises(ValueError, match="cyber_feed_http_status_not_success"):
        ingest_threat_feed_payload(
            binding=_binding(ThreatFeedKind.NVD_CVE_API),
            payload=_nvd_payload(),
            observed_at=NOW,
            http_status=500,
        )


def test_duplicate_normalized_records_fail_closed() -> None:
    payload = _cisa_payload()
    payload["vulnerabilities"].append(dict(payload["vulnerabilities"][0]))
    with pytest.raises(ValueError, match="cyber_feed_duplicate_normalized_record_id"):
        ingest_threat_feed_payload(
            binding=_binding(ThreatFeedKind.CISA_KEV_JSON),
            payload=payload,
            observed_at=NOW,
        )


def test_observation_fingerprint_tamper_fails_closed() -> None:
    result = ingest_threat_feed_payload(
        binding=_binding(ThreatFeedKind.CISA_KEV_JSON),
        payload=_cisa_payload(),
        observed_at=NOW,
    )
    tampered = result.observation.model_copy(update={"normalized_record_count": 99})
    with pytest.raises(ValidationError, match="cyber_feed_observation_fingerprint_mismatch"):
        ThreatFeedObservation.model_validate(tampered.model_dump(mode="json"))
