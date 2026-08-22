from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.cyber_current_threat_context_intelligence import (
    CurrentThreatContextReceipt,
    build_current_threat_context,
    verify_current_threat_context,
)
from app.cyber_defense_intelligence import ThreatIntelligenceSource, build_threat_record
from app.cyber_threat_enrichment_intelligence import (
    build_attack_defensive_coverage,
    build_epss_observation,
    fuse_global_threat_intelligence,
)
from app.cyber_threat_source_freshness_intelligence import (
    attest_attack_source_freshness,
    build_authoritative_attack_release_observation,
)

NOW = datetime(2026, 8, 19, 19, 50, tzinfo=UTC)
SOURCE_ENDPOINT = (
    "https://raw.githubusercontent.com/mitre/cti/master/"
    "enterprise-attack/enterprise-attack.json"
)


def _global(*, attack: bool = True, stale_epss: bool = False):
    records = [
        build_threat_record(
            record_id="threat:nvd:CVE-2026-9001",
            source=ThreatIntelligenceSource.NVD,
            source_record_id="CVE-2026-9001",
            published_at=NOW - timedelta(days=2),
            recorded_at=NOW - timedelta(days=1),
            source_evidence_ref="nvd:CVE-2026-9001",
            cve_ids=("CVE-2026-9001",),
            severity_score=9.8,
        )
    ]
    coverages = ()
    if attack:
        records.append(
            build_threat_record(
                record_id="threat:mitre:CVE-2026-9001",
                source=ThreatIntelligenceSource.MITRE_ATTACK,
                source_record_id="mitre:CVE-2026-9001",
                published_at=NOW - timedelta(days=2),
                recorded_at=NOW - timedelta(days=1),
                source_evidence_ref="mitre:CVE-2026-9001",
                cve_ids=("CVE-2026-9001",),
                attack_technique_ids=("T1059",),
            )
        )
        coverages = (
            build_attack_defensive_coverage(
                technique_id="T1059",
                attack_release_ref="mitre-attack:enterprise:v19.2",
                detection_strategy_ids=("DET0466",),
                data_component_ids=("DC0039",),
                telemetry_refs=("telemetry:process-events",),
                observed_at=NOW - timedelta(hours=2),
                recorded_at=NOW - timedelta(hours=1),
                source_evidence_ref="mitre:T1059:v19.2",
            ),
        )
    score_date = (NOW - timedelta(days=10 if stale_epss else 0)).date()
    epss = build_epss_observation(
        cve_id="CVE-2026-9001",
        score=0.91,
        percentile=0.99,
        score_date=score_date,
        observed_at=NOW - timedelta(minutes=30),
        recorded_at=NOW - timedelta(minutes=20),
        source_evidence_ref=f"first-epss:CVE-2026-9001:{score_date.isoformat()}",
    )
    return fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=tuple(records),
        epss=epss,
        defensive_coverages=coverages,
        as_of=NOW,
        max_epss_age_days=2,
    )


def _freshness(ingested: str):
    authoritative = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.2",
        release_observed_at=NOW - timedelta(minutes=30),
        recorded_at=NOW - timedelta(minutes=20),
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )
    return attest_attack_source_freshness(
        source_endpoint_ref=SOURCE_ENDPOINT,
        source_content_fingerprint="a" * 64,
        ingested_release_ref=ingested,
        authoritative_release=authoritative,
        as_of=NOW,
    )


def test_current_attack_release_allows_current_global_reasoning():
    receipt = build_current_threat_context(
        global_enrichment=_global(),
        attack_freshness=_freshness("ATT&CK-v19.2"),
    )

    assert receipt.attack_context_present is True
    assert receipt.attack_release_current is True
    assert receipt.current_global_reasoning_allowed is True
    assert "attack_release_current" in receipt.reason_codes
    assert receipt.company_exposure_granted is False
    assert receipt.company_truth_granted is False
    assert receipt.incident_confirmation_granted is False
    assert receipt.exploit_generation_permitted is False
    assert receipt.execution_authority_granted is False


def test_behind_attack_release_blocks_current_attack_reasoning_without_deleting_evidence():
    enrichment = _global()
    receipt = build_current_threat_context(
        global_enrichment=enrichment,
        attack_freshness=_freshness("ATT&CK-v19.1"),
    )

    assert enrichment.attack_technique_ids == ("T1059",)
    assert receipt.attack_release_current is False
    assert receipt.current_global_reasoning_allowed is False
    assert "attack_release_not_current:behind" in receipt.reason_codes


def test_missing_attack_freshness_receipt_fails_closed():
    receipt = build_current_threat_context(global_enrichment=_global())

    assert receipt.attack_context_present is True
    assert receipt.attack_freshness_receipt_id is None
    assert receipt.attack_release_current is False
    assert receipt.current_global_reasoning_allowed is False
    assert receipt.reason_codes[0] == "attack_context_present_but_release_freshness_missing"


def test_global_context_without_attack_dependency_remains_usable_without_attack_receipt():
    receipt = build_current_threat_context(global_enrichment=_global(attack=False))

    assert receipt.attack_context_present is False
    assert receipt.attack_release_current is True
    assert receipt.current_global_reasoning_allowed is True
    assert receipt.attack_freshness_receipt_id is None


def test_attack_freshness_cannot_be_supplied_when_enrichment_has_no_attack_context():
    with pytest.raises(ValueError, match="current_threat_attack_freshness_without_attack_context"):
        build_current_threat_context(
            global_enrichment=_global(attack=False),
            attack_freshness=_freshness("ATT&CK-v19.2"),
        )


def test_stale_epss_is_explicit_but_does_not_by_itself_block_non_attack_global_context():
    receipt = build_current_threat_context(
        global_enrichment=_global(attack=False, stale_epss=True)
    )

    assert receipt.current_global_reasoning_allowed is True
    assert "epss_present_but_stale_not_used_for_current_priority" in receipt.reason_codes


def test_tamper_cannot_relabel_behind_attack_context_as_current():
    receipt = build_current_threat_context(
        global_enrichment=_global(),
        attack_freshness=_freshness("ATT&CK-v19.1"),
    )
    tampered = receipt.model_copy(
        update={
            "attack_release_current": True,
            "current_global_reasoning_allowed": True,
        }
    )

    with pytest.raises(ValidationError, match="current_threat_context_fingerprint_mismatch"):
        verify_current_threat_context(receipt=tampered)


def test_current_context_cannot_be_modified_to_grant_company_or_execution_truth():
    receipt = build_current_threat_context(
        global_enrichment=_global(),
        attack_freshness=_freshness("ATT&CK-v19.2"),
    )
    payload = receipt.model_dump(mode="json")
    payload["company_truth_granted"] = True

    with pytest.raises(ValidationError, match="current_threat_context_never_grants_company_truth"):
        CurrentThreatContextReceipt.model_validate(payload)
