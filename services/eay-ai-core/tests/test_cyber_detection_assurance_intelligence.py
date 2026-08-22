from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.company_context_boundary import build_company_identity
from app.company_detection_coverage_intelligence import (
    CompanyTelemetryCapabilityStatus,
    assess_company_detection_coverage,
    build_company_telemetry_capability_observation,
)
from app.cyber_defense_intelligence import ThreatIntelligenceSource, build_threat_record
from app.cyber_detection_assurance_intelligence import (
    CyberDetectionAssuranceFinding,
    build_cyber_detection_assurance_finding,
    verify_cyber_detection_assurance_finding,
)
from app.cyber_platform_assurance import (
    SecurityAssuranceEnvironment,
    SecurityAssuranceStatus,
    SecurityFindingSeverity,
    build_eay_platform_security_plan,
)
from app.cyber_threat_enrichment_intelligence import (
    build_attack_defensive_coverage,
    fuse_global_threat_intelligence,
)

NOW = datetime(2026, 8, 19, 19, 30, tzinfo=UTC)
REV = "c" * 64


def _identity(suffix: str = "a"):
    return build_company_identity(
        tenant_id=f"tenant-{suffix}",
        company_id=f"company-{suffix}",
        company_slug=f"company-{suffix}",
        profile_revision="rev-1",
        environment="production",
    )


def _global(*, with_components: bool = True):
    cisa = build_threat_record(
        record_id="threat:cisa:CVE-2026-9001",
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-9001",
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=1),
        source_evidence_ref="cisa-kev:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )
    records = [cisa]
    coverages = ()
    if with_components:
        mitre = build_threat_record(
            record_id="threat:mitre:CVE-2026-9001",
            source=ThreatIntelligenceSource.MITRE_ATTACK,
            source_record_id="mitre:CVE-2026-9001",
            published_at=NOW - timedelta(days=2),
            recorded_at=NOW - timedelta(days=1),
            source_evidence_ref="mitre:CVE-2026-9001",
            cve_ids=("CVE-2026-9001",),
            attack_technique_ids=("T1059",),
        )
        records.append(mitre)
        coverages = (
            build_attack_defensive_coverage(
                technique_id="T1059",
                attack_release_ref="mitre-attack:enterprise:v19.1",
                detection_strategy_ids=("DET0466",),
                data_component_ids=("DC0039", "DC0061"),
                telemetry_refs=("telemetry:process-events", "telemetry:file-events"),
                observed_at=NOW - timedelta(hours=2),
                recorded_at=NOW - timedelta(hours=1),
                source_evidence_ref="mitre:T1059:v19.1",
            ),
        )
    return fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=tuple(records),
        defensive_coverages=coverages,
        as_of=NOW - timedelta(minutes=30),
        max_epss_age_days=2,
    )


def _obs(component_id: str, status: CompanyTelemetryCapabilityStatus, *, identity=None):
    identity = identity or _identity()
    telemetry_ref = None
    if status is not CompanyTelemetryCapabilityStatus.MISSING:
        telemetry_ref = f"telemetry:company-a:{component_id.lower()}"
    return build_company_telemetry_capability_observation(
        identity=identity,
        observation_id=f"obs:{component_id}:{status.value}",
        data_component_id=component_id,
        status=status,
        telemetry_ref=telemetry_ref,
        evidence_refs=(f"company-evidence:{component_id}:{status.value}",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )


def _coverage(global_receipt, *observations, identity=None):
    identity = identity or _identity()
    return assess_company_detection_coverage(
        identity=identity,
        global_enrichment=global_receipt,
        observations=tuple(observations),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )


def _plan(environment=SecurityAssuranceEnvironment.REPOSITORY):
    return build_eay_platform_security_plan(
        plan_id=f"security-plan:{environment.value}",
        repository_ref="github:erdiaydinn/opex-control-center-frontend",
        revision_ref=REV,
        environment=environment,
    )


def test_covered_company_detection_state_becomes_evidence_bound_pass():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.AVAILABLE),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )

    assert finding.status is SecurityAssuranceStatus.PASS
    assert finding.severity is SecurityFindingSeverity.INFO
    assert finding.control_verified is True
    assert finding.security_attention_required is False
    assert finding.production_write_allowed is False
    assert finding.automatic_remediation_allowed is False
    assert finding.release_gate_authority_granted is False
    assert finding.execution_authority_granted is False


def test_confirmed_detection_gap_becomes_fail_with_global_urgency_severity():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.MISSING),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )

    assert finding.status is SecurityAssuranceStatus.FAIL
    assert finding.severity is SecurityFindingSeverity.CRITICAL
    assert finding.control_verified is False
    assert finding.security_attention_required is True
    assert finding.missing_component_ids == ("DC0061",)


def test_unknown_detection_evidence_stays_inconclusive_not_pass_or_confirmed_gap():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )

    assert finding.status is SecurityAssuranceStatus.INCONCLUSIVE
    assert finding.severity is SecurityFindingSeverity.HIGH
    assert finding.control_verified is False
    assert finding.security_attention_required is True
    assert finding.missing_component_ids == ()
    assert finding.unverified_component_ids == ("DC0061",)


def test_no_global_detection_requirement_is_inconclusive_info_not_false_pass():
    global_receipt = _global(with_components=False)
    coverage = _coverage(global_receipt)
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )

    assert finding.status is SecurityAssuranceStatus.INCONCLUSIVE
    assert finding.severity is SecurityFindingSeverity.INFO
    assert finding.control_verified is False
    assert finding.security_attention_required is False


def test_cross_company_detection_receipt_cannot_enter_company_assurance():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs(
            "DC0039",
            CompanyTelemetryCapabilityStatus.AVAILABLE,
            identity=_identity("b"),
        ),
        _obs(
            "DC0061",
            CompanyTelemetryCapabilityStatus.AVAILABLE,
            identity=_identity("b"),
        ),
        identity=_identity("b"),
    )

    with pytest.raises(
        ValueError,
        match="cyber_detection_assurance_company_identity_mismatch",
    ):
        build_cyber_detection_assurance_finding(
            identity=_identity("a"),
            assurance_plan=_plan(),
            global_enrichment=global_receipt,
            company_detection_coverage=coverage,
        )


def test_detection_assurance_requires_exact_global_enrichment_binding():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.AVAILABLE),
    )
    other_global = global_receipt.model_copy(
        update={"receipt_id": "global-threat-enrichment:other"}
    )

    with pytest.raises(ValidationError):
        build_cyber_detection_assurance_finding(
            identity=_identity(),
            assurance_plan=_plan(),
            global_enrichment=other_global,
            company_detection_coverage=coverage,
        )


def test_production_assurance_bridge_preserves_read_only_non_authoritative_boundary():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.MISSING),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )

    assert finding.assurance_environment is SecurityAssuranceEnvironment.PRODUCTION_READ_ONLY
    assert finding.production_write_allowed is False
    assert finding.automatic_remediation_allowed is False
    assert finding.release_gate_authority_granted is False
    assert finding.execution_authority_granted is False


def test_tampered_detection_assurance_finding_fails_integrity_validation():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.AVAILABLE),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )
    tampered = finding.model_copy(
        update={"severity": SecurityFindingSeverity.CRITICAL}
    )

    with pytest.raises(ValidationError, match="cyber_detection_assurance_fingerprint_mismatch"):
        verify_cyber_detection_assurance_finding(finding=tampered)


def test_assurance_finding_cannot_be_modified_to_grant_execution_authority():
    global_receipt = _global()
    coverage = _coverage(
        global_receipt,
        _obs("DC0039", CompanyTelemetryCapabilityStatus.AVAILABLE),
        _obs("DC0061", CompanyTelemetryCapabilityStatus.AVAILABLE),
    )
    finding = build_cyber_detection_assurance_finding(
        identity=_identity(),
        assurance_plan=_plan(),
        global_enrichment=global_receipt,
        company_detection_coverage=coverage,
    )
    payload = finding.model_dump(mode="json")
    payload["execution_authority_granted"] = True

    with pytest.raises(
        ValidationError,
        match="cyber_detection_assurance_never_grants_execution_authority",
    ):
        CyberDetectionAssuranceFinding.model_validate(payload)
