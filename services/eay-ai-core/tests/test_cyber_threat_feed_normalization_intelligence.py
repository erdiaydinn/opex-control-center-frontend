from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.cyber_defense_intelligence import ThreatIntelligenceSource
from app.cyber_threat_feed_normalization import (
    NormalizedThreatFeed,
    normalize_cisa_kev_payload,
    normalize_mitre_attack_stix_payload,
    normalize_nvd_cve_payload,
)

OBSERVED = datetime(2026, 8, 19, 12, tzinfo=UTC)


def test_cisa_kev_normalization_marks_only_authoritative_known_exploitation() -> None:
    payload = {
        "catalogVersion": "2026.08.19",
        "dateReleased": "2026-08-19T10:00:00.000Z",
        "count": 1,
        "vulnerabilities": [
            {
                "cveID": "CVE-2026-12345",
                "vendorProject": "Example Vendor",
                "product": "Edge Gateway",
                "vulnerabilityName": "Example vulnerability",
                "dateAdded": "2026-08-18",
                "shortDescription": "raw description must not be retained",
                "requiredAction": "apply vendor mitigation",
                "dueDate": "2026-09-01",
                "knownRansomwareCampaignUse": "Unknown",
                "notes": "source note",
                "cwes": ["CWE-78"],
            }
        ],
    }
    feed = normalize_cisa_kev_payload(
        payload=payload,
        feed_ref="source:cisa-kev",
        observed_at=OBSERVED,
    )
    assert feed.receipt.source is ThreatIntelligenceSource.CISA_KEV
    assert feed.receipt.raw_payload_retained is False
    assert feed.receipt.network_io_performed is False
    assert feed.receipt.company_truth_granted is False
    assert feed.receipt.execution_authority_granted is False
    assert len(feed.records) == 1
    record = feed.records[0]
    assert record.cve_ids == ("CVE-2026-12345",)
    assert record.cwe_ids == ("CWE-78",)
    assert record.known_exploited_in_wild is True
    assert "raw description must not be retained" not in str(feed.model_dump(mode="json"))
    assert "apply vendor mitigation" not in str(feed.model_dump(mode="json"))


def test_cisa_kev_declared_count_mismatch_fails_closed() -> None:
    with pytest.raises(ValueError, match="cyber_cisa_kev_count_mismatch"):
        normalize_cisa_kev_payload(
            payload={"count": 2, "vulnerabilities": []},
            feed_ref="source:cisa-kev",
            observed_at=OBSERVED,
        )


def test_nvd_normalization_does_not_self_promote_kev_metadata() -> None:
    payload = {
        "resultsPerPage": 1,
        "startIndex": 0,
        "totalResults": 1,
        "vulnerabilities": [
            {
                "cve": {
                    "id": "CVE-2026-23456",
                    "sourceIdentifier": "example@example.org",
                    "published": "2026-08-17T10:30:00.000",
                    "lastModified": "2026-08-18T11:00:00.000",
                    "vulnStatus": "Analyzed",
                    "cisaExploitAdd": "2026-08-18",
                    "cisaActionDue": "2026-09-01",
                    "cisaRequiredAction": "apply mitigation",
                    "weaknesses": [
                        {"description": [{"lang": "en", "value": "CWE-79"}]}
                    ],
                    "metrics": {
                        "cvssMetricV31": [
                            {"cvssData": {"baseScore": 9.1}}
                        ],
                        "cvssMetricV40": [
                            {"cvssData": {"baseScore": 9.4}}
                        ],
                    },
                }
            }
        ],
    }
    feed = normalize_nvd_cve_payload(
        payload=payload,
        feed_ref="source:nvd-cve-api-v2",
        observed_at=OBSERVED,
    )
    record = feed.records[0]
    assert record.source is ThreatIntelligenceSource.NVD
    assert record.cve_ids == ("CVE-2026-23456",)
    assert record.cwe_ids == ("CWE-79",)
    assert record.severity_score == 9.4
    assert record.known_exploited_in_wild is False
    assert record.company_truth_granted is False


def test_mitre_attack_stix_normalizes_active_attack_patterns_only() -> None:
    payload = {
        "type": "bundle",
        "id": "bundle--example",
        "objects": [
            {
                "type": "attack-pattern",
                "id": "attack-pattern--active",
                "created": "2025-01-01T00:00:00.000Z",
                "modified": "2026-08-18T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1059"}
                ],
            },
            {
                "type": "attack-pattern",
                "id": "attack-pattern--revoked",
                "revoked": True,
                "modified": "2026-08-18T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T9999"}
                ],
            },
            {"type": "identity", "id": "identity--mitre"},
        ],
    }
    feed = normalize_mitre_attack_stix_payload(
        payload=payload,
        feed_ref="source:mitre-attack-stix-2.1",
        observed_at=OBSERVED,
    )
    assert len(feed.records) == 1
    assert feed.receipt.ignored_object_count == 2
    assert feed.records[0].attack_technique_ids == ("T1059",)
    assert feed.records[0].known_exploited_in_wild is False
    assert feed.records[0].incident_confirmation_granted is False


def test_feed_normalizer_rejects_secret_bearing_source_reference() -> None:
    with pytest.raises(ValueError, match="cyber_feed_unsafe_reference_forbidden"):
        normalize_cisa_kev_payload(
            payload={"count": 0, "vulnerabilities": []},
            feed_ref="authorization:bearer-material",
            observed_at=OBSERVED,
        )


def test_feed_fingerprint_tamper_fails_closed() -> None:
    feed = normalize_nvd_cve_payload(
        payload={"vulnerabilities": []},
        feed_ref="source:nvd-cve-api-v2",
        observed_at=OBSERVED,
    )
    tampered = feed.model_copy(update={"records": ()})
    payload = tampered.model_dump(mode="json")
    payload["receipt"]["ignored_object_count"] = 1
    with pytest.raises(ValueError):
        NormalizedThreatFeed.model_validate(payload)
