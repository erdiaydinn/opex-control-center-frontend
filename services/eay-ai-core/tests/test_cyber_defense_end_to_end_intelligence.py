from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.company_context_boundary import build_company_identity
from app.company_detection_coverage_intelligence import (
    CompanyDetectionCoverageStatus,
    CompanyTelemetryCapabilityStatus,
    assess_company_detection_coverage,
    build_company_telemetry_capability_observation,
)
from app.cyber_attack_release_feed_runtime import (
    build_attack_release_feed_binding,
    ingest_attack_release_payload,
)
from app.cyber_current_threat_context_intelligence import build_current_threat_context
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
from app.cyber_detection_assurance_intelligence import (
    build_cyber_detection_assurance_finding,
)
from app.cyber_platform_assurance import (
    SecurityAssuranceStatus,
    SecurityFindingSeverity,
    build_eay_platform_security_plan,
)
from app.cyber_threat_enrichment_intelligence import (
    GlobalDefensiveUrgency,
    build_attack_defensive_coverage,
    build_epss_observation,
    fuse_global_threat_intelligence,
)
from app.cyber_threat_source_freshness_intelligence import (
    ThreatSourceFreshnessStatus,
    attest_attack_source_freshness,
    build_authoritative_attack_release_observation,
)

NOW = datetime(2026, 8, 19, 20, 10, tzinfo=UTC)


def _identity():
    return build_company_identity(
        tenant_id="tenant-a",
        company_id="company-a",
        company_slug="company-a",
        profile_revision="rev-1",
        environment="production",
    )


def _attack_payload():
    return {
        "type": "bundle",
        "id": "bundle--11111111-1111-1111-1111-111111111111",
        "objects": [
            {
                "type": "attack-pattern",
                "id": "attack-pattern--11111111-1111-1111-1111-111111111111",
                "created": "2020-01-01T00:00:00.000Z",
                "external_references": [
                    {"source_name": "mitre-attack", "external_id": "T1059"}
                ],
                "x_mitre_platforms": ["Windows", "Linux"],
                "x_mitre_version": "2.7",
            }
        ],
    }


def _global_chain():
    release = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.2",
        release_observed_at=NOW - timedelta(minutes=40),
        recorded_at=NOW - timedelta(minutes=35),
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )
    attack_binding = build_attack_release_feed_binding(authoritative_release=release)
    attack_ingestion = ingest_attack_release_payload(
        binding=attack_binding,
        authoritative_release=release,
        payload=_attack_payload(),
        observed_at=NOW - timedelta(minutes=30),
    )
    attack_record = attack_ingestion.records[0]

    cisa_record = build_threat_record(
        record_id="threat:cisa:CVE-2026-9001",
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-9001",
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(hours=4),
        source_evidence_ref="cisa-kev:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )
    # Bind the canonical ATT&CK technique record to the CVE for this defensive
    # benchmark fixture; the public threat ledger can contain this relation only
    # when upstream evidence establishes it.
    attack_record_for_cve = build_threat_record(
        record_id="threat:mitre:CVE-2026-9001:T1059",
        source=ThreatIntelligenceSource.MITRE_ATTACK,
        source_record_id=attack_record.source_record_id,
        published_at=attack_record.published_at,
        recorded_at=attack_record.recorded_at,
        source_evidence_ref=attack_record.source_evidence_ref,
        product_refs=attack_record.product_refs,
        cve_ids=("CVE-2026-9001",),
        attack_technique_ids=attack_record.attack_technique_ids,
    )
    epss = build_epss_observation(
        cve_id="CVE-2026-9001",
        score=0.91,
        percentile=0.99,
        score_date=NOW.date(),
        observed_at=NOW - timedelta(minutes=25),
        recorded_at=NOW - timedelta(minutes=20),
        source_evidence_ref="first-epss:CVE-2026-9001:2026-08-19",
    )
    detection = build_attack_defensive_coverage(
        technique_id="T1059",
        attack_release_ref="mitre-attack:enterprise:v19.2",
        detection_strategy_ids=("DET0466",),
        data_component_ids=("DC0039", "DC0061"),
        telemetry_refs=("telemetry:process-events", "telemetry:file-events"),
        observed_at=NOW - timedelta(minutes=30),
        recorded_at=NOW - timedelta(minutes=30),
        source_evidence_ref="mitre-attack:T1059:v19.2",
    )
    enrichment = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(cisa_record, attack_record_for_cve),
        epss=epss,
        defensive_coverages=(detection,),
        as_of=NOW,
        max_epss_age_days=2,
    )
    freshness = attest_attack_source_freshness(
        source_endpoint_ref=attack_ingestion.observation.endpoint_ref,
        source_content_fingerprint=attack_ingestion.observation.content_sha256,
        ingested_release_ref=attack_ingestion.observation.release_ref,
        authoritative_release=release,
        as_of=NOW,
    )
    current_context = build_current_threat_context(
        global_enrichment=enrichment,
        attack_freshness=freshness,
    )
    return cisa_record, enrichment, freshness, current_context


def test_end_to_end_current_global_threat_does_not_overclaim_unknown_company_exposure_but_can_surface_real_detection_gap():
    threat, enrichment, freshness, current_context = _global_chain()

    assert enrichment.global_defensive_urgency is GlobalDefensiveUrgency.CRITICAL
    assert freshness.status is ThreatSourceFreshnessStatus.CURRENT
    assert current_context.current_global_reasoning_allowed is True

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
    priority = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    assert priority.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert priority.disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE
    assert priority.company_defensive_priority is None
    assert priority.firm_company_exposure_claim_authorized is False

    process_observation = build_company_telemetry_capability_observation(
        identity=identity,
        observation_id="telemetry-observation:DC0039:available",
        data_component_id="DC0039",
        status=CompanyTelemetryCapabilityStatus.AVAILABLE,
        telemetry_ref="telemetry:company-a:process-events",
        detection_rule_refs=("detection-rule:process-command:v1",),
        evidence_refs=("company-evidence:DC0039:available",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    file_missing = build_company_telemetry_capability_observation(
        identity=identity,
        observation_id="telemetry-observation:DC0061:missing",
        data_component_id="DC0061",
        status=CompanyTelemetryCapabilityStatus.MISSING,
        evidence_refs=("company-evidence:DC0061:missing",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    detection_coverage = assess_company_detection_coverage(
        identity=identity,
        global_enrichment=enrichment,
        observations=(process_observation, file_missing),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    assert detection_coverage.coverage_status is CompanyDetectionCoverageStatus.PARTIAL
    assert detection_coverage.missing_component_ids == ("DC0061",)
    assert detection_coverage.firm_company_detection_claim_authorized is True

    assurance_plan = build_eay_platform_security_plan(
        plan_id="security-plan:cyber-e2e",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref="f" * 64,
    )
    finding = build_cyber_detection_assurance_finding(
        identity=identity,
        assurance_plan=assurance_plan,
        global_enrichment=enrichment,
        company_detection_coverage=detection_coverage,
    )
    assert finding.status is SecurityAssuranceStatus.FAIL
    assert finding.severity is SecurityFindingSeverity.CRITICAL
    assert finding.security_attention_required is True
    assert finding.production_write_allowed is False
    assert finding.automatic_remediation_allowed is False
    assert finding.release_gate_authority_granted is False
    assert finding.execution_authority_granted is False


def test_end_to_end_missing_company_telemetry_evidence_is_inconclusive_not_a_fake_gap():
    _, enrichment, freshness, current_context = _global_chain()
    assert freshness.status is ThreatSourceFreshnessStatus.CURRENT
    assert current_context.current_global_reasoning_allowed is True

    identity = _identity()
    process_observation = build_company_telemetry_capability_observation(
        identity=identity,
        observation_id="telemetry-observation:DC0039:available",
        data_component_id="DC0039",
        status=CompanyTelemetryCapabilityStatus.AVAILABLE,
        telemetry_ref="telemetry:company-a:process-events",
        evidence_refs=("company-evidence:DC0039:available",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    detection_coverage = assess_company_detection_coverage(
        identity=identity,
        global_enrichment=enrichment,
        observations=(process_observation,),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    assert detection_coverage.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED
    assert detection_coverage.missing_component_ids == ()
    assert detection_coverage.unverified_component_ids == ("DC0061",)

    finding = build_cyber_detection_assurance_finding(
        identity=identity,
        assurance_plan=build_eay_platform_security_plan(
            plan_id="security-plan:cyber-e2e-unverified",
            repository_ref="github:erdiaydinn/opex-control-center-frontend",
            revision_ref="f" * 64,
        ),
        global_enrichment=enrichment,
        company_detection_coverage=detection_coverage,
    )
    assert finding.status is SecurityAssuranceStatus.INCONCLUSIVE
    assert finding.control_verified is False
    assert finding.missing_component_ids == ()
    assert finding.unverified_component_ids == ("DC0061",)
    assert finding.security_attention_required is True
