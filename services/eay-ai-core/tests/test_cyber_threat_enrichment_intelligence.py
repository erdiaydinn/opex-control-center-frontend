from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.company_context_boundary import build_company_identity
from app.cyber_defense_intelligence import (
    AssetCriticality,
    ExposureStatus,
    PatchStatus,
    ThreatIntelligenceSource,
    build_company_exposure,
    build_threat_record,
)
from app.cyber_defense_priority_intelligence import (
    CompanyExposureClaim,
    CompanyThreatDisposition,
    build_defensive_priority_receipt,
)
from app.cyber_threat_enrichment_intelligence import (
    DefensiveTechniqueCoverage,
    EpssObservation,
    GlobalDefensiveUrgency,
    GlobalThreatEnrichmentReceipt,
    build_attack_defensive_coverage,
    build_epss_observation,
    fuse_global_threat_intelligence,
    verify_global_threat_enrichment_receipt,
)

NOW = datetime(2026, 8, 19, 18, 45, tzinfo=UTC)


def _record(
    *,
    source: ThreatIntelligenceSource,
    suffix: str,
    severity: float | None = 9.8,
    known_exploited: bool = False,
    attack_ids: tuple[str, ...] = (),
):
    return build_threat_record(
        record_id=f"threat:{suffix}:CVE-2026-9001",
        source=source,
        source_record_id=f"{suffix}:CVE-2026-9001",
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=1),
        source_evidence_ref=f"{suffix}:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        attack_technique_ids=attack_ids,
        severity_score=severity,
        known_exploited_in_wild=known_exploited,
    )


def _epss(*, score: float = 0.91, percentile: float = 0.99, days_old: int = 0):
    score_date = (NOW - timedelta(days=days_old)).date()
    return build_epss_observation(
        cve_id="CVE-2026-9001",
        score=score,
        percentile=percentile,
        score_date=score_date,
        observed_at=NOW - timedelta(minutes=20),
        recorded_at=NOW - timedelta(minutes=10),
        source_evidence_ref=f"first-epss:CVE-2026-9001:{score_date.isoformat()}",
    )


def _coverage():
    return build_attack_defensive_coverage(
        technique_id="T1059",
        attack_release_ref="mitre-attack:enterprise:v19.1",
        detection_strategy_ids=("DET0466",),
        data_component_ids=("DC0039", "DC0061"),
        telemetry_refs=("telemetry:process-events", "telemetry:file-events"),
        observed_at=NOW - timedelta(hours=2),
        recorded_at=NOW - timedelta(hours=1),
        source_evidence_ref="mitre-attack:T1059:v19.1",
    )


def _identity():
    return build_company_identity(
        tenant_id="tenant-a",
        company_id="company-a",
        company_slug="company-a",
        profile_revision="rev-1",
        environment="production",
    )


def test_fusion_combines_public_sources_epss_and_detection_coverage_without_company_truth():
    records = (
        _record(
            source=ThreatIntelligenceSource.CISA_KEV,
            suffix="cisa-kev",
            known_exploited=True,
        ),
        _record(source=ThreatIntelligenceSource.NVD, suffix="nvd"),
        _record(
            source=ThreatIntelligenceSource.MITRE_ATTACK,
            suffix="mitre-attack",
            severity=None,
            attack_ids=("T1059",),
        ),
    )

    receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=records,
        epss=_epss(),
        defensive_coverages=(_coverage(),),
        as_of=NOW,
        max_epss_age_days=2,
    )

    assert receipt.global_defensive_urgency is GlobalDefensiveUrgency.CRITICAL
    assert receipt.known_exploited_in_wild is True
    assert receipt.epss_current is True
    assert receipt.epss_score == pytest.approx(0.91)
    assert receipt.source_diversity_count == 3
    assert receipt.attack_technique_ids == ("T1059",)
    assert receipt.detection_strategy_ids == ("DET0466",)
    assert receipt.data_component_ids == ("DC0039", "DC0061")
    assert receipt.company_exposure_granted is False
    assert receipt.company_truth_granted is False
    assert receipt.incident_confirmation_granted is False
    assert receipt.exploit_generation_permitted is False
    assert receipt.execution_authority_granted is False


def test_high_epss_without_kev_is_priority_signal_not_known_exploitation():
    receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(_record(source=ThreatIntelligenceSource.NVD, suffix="nvd"),),
        epss=_epss(score=0.88, percentile=0.995),
        as_of=NOW,
        max_epss_age_days=2,
    )

    assert receipt.global_defensive_urgency is GlobalDefensiveUrgency.HIGH
    assert receipt.known_exploited_in_wild is False
    assert "epss_high_probability" in receipt.reason_codes
    assert receipt.exploitation_prediction_is_company_risk is False


def test_stale_epss_is_retained_for_provenance_but_does_not_elevate_global_urgency():
    receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(
            _record(
                source=ThreatIntelligenceSource.NVD,
                suffix="nvd",
                severity=4.0,
            ),
        ),
        epss=_epss(score=0.99, percentile=0.999, days_old=10),
        as_of=NOW,
        max_epss_age_days=2,
    )

    assert receipt.epss_score == pytest.approx(0.99)
    assert receipt.epss_current is False
    assert "epss_stale" in receipt.reason_codes
    assert receipt.global_defensive_urgency is GlobalDefensiveUrgency.LOW


@pytest.mark.parametrize(
    ("score", "percentile"),
    [(-0.01, 0.5), (1.01, 0.5), (0.5, -0.01), (0.5, 1.01)],
)
def test_epss_probability_and_percentile_must_stay_between_zero_and_one(
    score: float,
    percentile: float,
):
    with pytest.raises(ValidationError):
        build_epss_observation(
            cve_id="CVE-2026-9001",
            score=score,
            percentile=percentile,
            score_date=NOW.date(),
            observed_at=NOW,
            recorded_at=NOW,
            source_evidence_ref="first-epss:CVE-2026-9001",
        )


def test_future_known_epss_cannot_leak_into_historical_receipt():
    epss = build_epss_observation(
        cve_id="CVE-2026-9001",
        score=0.90,
        percentile=0.99,
        score_date=NOW.date(),
        observed_at=NOW,
        recorded_at=NOW,
        source_evidence_ref="first-epss:CVE-2026-9001",
    )

    with pytest.raises(ValueError, match="cyber_enrichment_future_known_epss_forbidden"):
        fuse_global_threat_intelligence(
            cve_id="CVE-2026-9001",
            threat_records=(
                _record(
                    source=ThreatIntelligenceSource.NVD,
                    suffix="nvd",
                    severity=8.0,
                ),
            ),
            epss=epss,
            as_of=NOW - timedelta(hours=1),
            max_epss_age_days=2,
        )


def test_attack_detection_coverage_must_bind_to_a_technique_present_in_threat_evidence():
    with pytest.raises(
        ValueError,
        match="cyber_enrichment_attack_coverage_not_bound_to_threat",
    ):
        fuse_global_threat_intelligence(
            cve_id="CVE-2026-9001",
            threat_records=(
                _record(source=ThreatIntelligenceSource.NVD, suffix="nvd"),
            ),
            defensive_coverages=(_coverage(),),
            as_of=NOW,
            max_epss_age_days=2,
        )


@pytest.mark.parametrize(
    ("detection_ids", "component_ids"),
    [(("BAD1",), ()), ((), ("DS0015",))],
)
def test_attack_coverage_rejects_non_detection_strategy_or_data_component_ids(
    detection_ids: tuple[str, ...],
    component_ids: tuple[str, ...],
):
    with pytest.raises(ValidationError):
        build_attack_defensive_coverage(
            technique_id="T1059",
            attack_release_ref="mitre-attack:enterprise:v19.1",
            detection_strategy_ids=detection_ids,
            data_component_ids=component_ids,
            telemetry_refs=("telemetry:process-events",),
            observed_at=NOW,
            recorded_at=NOW,
            source_evidence_ref="mitre-attack:T1059:v19.1",
        )


def test_global_enrichment_cannot_bypass_company_exposure_receipt():
    threat = _record(
        source=ThreatIntelligenceSource.NVD,
        suffix="nvd",
        severity=9.8,
    )
    global_receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(threat,),
        epss=_epss(score=0.95, percentile=0.999),
        as_of=NOW,
        max_epss_age_days=2,
    )
    identity = _identity()
    exposure = build_company_exposure(
        identity=identity,
        threat=threat,
        exposure_id="exposure:asset-a:CVE-2026-9001",
        asset_ref="asset:prod-api-a",
        company_evidence_refs=(),
        status=ExposureStatus.UNKNOWN,
        criticality=AssetCriticality.CRITICAL,
        patch_status=PatchStatus.UNKNOWN,
        internet_reachable=False,
        privileged_identity_surface=False,
        compensating_control_present=False,
        assessed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    company_receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert global_receipt.global_defensive_urgency is GlobalDefensiveUrgency.HIGH
    assert company_receipt.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert company_receipt.disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE
    assert company_receipt.company_defensive_priority is None
    assert company_receipt.firm_company_exposure_claim_authorized is False


def test_global_receipt_is_tenant_neutral_and_offensive_fields_are_forbidden():
    receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(_record(source=ThreatIntelligenceSource.NVD, suffix="nvd"),),
        epss=_epss(),
        as_of=NOW,
        max_epss_age_days=2,
    )
    payload = receipt.model_dump(mode="json")

    assert "identity" not in payload
    assert "tenant_id" not in payload
    assert "company_id" not in payload

    payload["exploit_payload"] = "forbidden"
    with pytest.raises(ValidationError):
        GlobalThreatEnrichmentReceipt.model_validate(payload)


def test_tampered_global_receipt_fails_integrity_verification():
    receipt = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(_record(source=ThreatIntelligenceSource.NVD, suffix="nvd"),),
        epss=_epss(),
        as_of=NOW,
        max_epss_age_days=2,
    )
    tampered = receipt.model_copy(
        update={"global_defensive_urgency": GlobalDefensiveUrgency.CRITICAL}
    )

    with pytest.raises(ValidationError, match="cyber_enrichment_receipt_fingerprint_mismatch"):
        verify_global_threat_enrichment_receipt(receipt=tampered)


def test_duplicate_public_threat_records_are_rejected():
    record = _record(source=ThreatIntelligenceSource.NVD, suffix="nvd")
    with pytest.raises(ValueError, match="cyber_enrichment_record_ids_must_be_unique"):
        fuse_global_threat_intelligence(
            cve_id="CVE-2026-9001",
            threat_records=(record, record),
            as_of=NOW,
            max_epss_age_days=2,
        )


def test_epss_observation_never_claims_exploitation_confirmation():
    observation = _epss()
    payload = observation.model_dump(mode="json")
    payload["exploitation_confirmed"] = True

    with pytest.raises(ValidationError, match="cyber_epss_never_confirms_exploitation"):
        EpssObservation.model_validate(payload)


def test_attack_coverage_never_accepts_instruction_or_execution_authority():
    coverage = _coverage()
    payload = coverage.model_dump(mode="json")
    payload["attack_instruction_content_allowed"] = True

    with pytest.raises(ValidationError, match="cyber_attack_instruction_content_forbidden"):
        DefensiveTechniqueCoverage.model_validate(payload)
