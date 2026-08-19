from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.company_context_boundary import build_company_identity
from app.company_detection_coverage_intelligence import (
    CompanyDetectionCoverageReceipt,
    CompanyDetectionCoverageStatus,
    CompanyTelemetryCapabilityStatus,
    assess_company_detection_coverage,
    build_company_telemetry_capability_observation,
    verify_company_detection_coverage_receipt,
)
from app.cyber_defense_intelligence import ThreatIntelligenceSource, build_threat_record
from app.cyber_threat_enrichment_intelligence import (
    build_attack_defensive_coverage,
    fuse_global_threat_intelligence,
)

NOW = datetime(2026, 8, 19, 19, 20, tzinfo=UTC)


def _identity(suffix: str = "a"):
    return build_company_identity(
        tenant_id=f"tenant-{suffix}",
        company_id=f"company-{suffix}",
        company_slug=f"company-{suffix}",
        profile_revision="rev-1",
        environment="production",
    )


def _global_receipt(*, with_components: bool = True):
    attack_ids = ("T1059",) if with_components else ()
    threat = build_threat_record(
        record_id="threat:mitre:CVE-2026-9001",
        source=ThreatIntelligenceSource.MITRE_ATTACK,
        source_record_id="mitre:CVE-2026-9001",
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=1),
        source_evidence_ref="mitre:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        attack_technique_ids=attack_ids,
    )
    coverages = ()
    if with_components:
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
        threat_records=(threat,),
        defensive_coverages=coverages,
        as_of=NOW - timedelta(minutes=30),
        max_epss_age_days=2,
    )


def _observation(
    component_id: str,
    *,
    status: CompanyTelemetryCapabilityStatus,
    identity=None,
    age_minutes: int = 5,
):
    identity = identity or _identity()
    telemetry_ref = None
    rules: tuple[str, ...] = ()
    if status is not CompanyTelemetryCapabilityStatus.MISSING:
        telemetry_ref = f"telemetry:company-a:{component_id.lower()}"
        rules = (f"detection-rule:{component_id.lower()}:v1",)
    observed = NOW - timedelta(minutes=age_minutes)
    return build_company_telemetry_capability_observation(
        identity=identity,
        observation_id=f"telemetry-observation:{component_id}:{status.value}",
        data_component_id=component_id,
        status=status,
        telemetry_ref=telemetry_ref,
        detection_rule_refs=rules,
        evidence_refs=(f"company-evidence:{component_id}:{status.value}",),
        observed_at=observed,
        recorded_at=observed,
    )


def test_all_required_current_telemetry_can_prove_covered_state():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
            _observation("DC0061", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.COVERED
    assert receipt.required_data_component_ids == ("DC0039", "DC0061")
    assert receipt.available_component_ids == ("DC0039", "DC0061")
    assert receipt.missing_component_ids == ()
    assert receipt.unverified_component_ids == ()
    assert receipt.verified_coverage_ratio == pytest.approx(1.0)
    assert receipt.firm_company_detection_claim_authorized is True
    assert receipt.remediation_authority_granted is False
    assert receipt.execution_authority_granted is False


def test_explicit_current_missing_evidence_can_prove_partial_detection_gap():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
            _observation("DC0061", status=CompanyTelemetryCapabilityStatus.MISSING),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.PARTIAL
    assert receipt.available_component_ids == ("DC0039",)
    assert receipt.missing_component_ids == ("DC0061",)
    assert receipt.unverified_component_ids == ()
    assert receipt.verified_coverage_ratio == pytest.approx(0.5)
    assert receipt.firm_company_detection_claim_authorized is True
    assert "missing_detection_components_present" in receipt.reason_codes


def test_absent_observation_is_unverified_not_silently_missing():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED
    assert receipt.missing_component_ids == ()
    assert receipt.unverified_component_ids == ("DC0061",)
    assert receipt.verified_coverage_ratio is None
    assert receipt.firm_company_detection_claim_authorized is False


def test_stale_company_telemetry_evidence_returns_to_unverified_state():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
            _observation(
                "DC0061",
                status=CompanyTelemetryCapabilityStatus.AVAILABLE,
                age_minutes=180,
            ),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.UNVERIFIED
    assert receipt.unverified_component_ids == ("DC0061",)
    assert receipt.firm_company_detection_claim_authorized is False


def test_degraded_component_is_a_firm_partial_state_when_all_evidence_is_current():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
            _observation("DC0061", status=CompanyTelemetryCapabilityStatus.DEGRADED),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.PARTIAL
    assert receipt.degraded_component_ids == ("DC0061",)
    assert receipt.missing_component_ids == ()
    assert receipt.firm_company_detection_claim_authorized is True


def test_cross_company_telemetry_cannot_satisfy_company_detection_coverage():
    with pytest.raises(
        ValueError,
        match="company_detection_cross_company_observation_forbidden",
    ):
        assess_company_detection_coverage(
            identity=_identity("a"),
            global_enrichment=_global_receipt(),
            observations=(
                _observation(
                    "DC0039",
                    status=CompanyTelemetryCapabilityStatus.AVAILABLE,
                    identity=_identity("b"),
                ),
            ),
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )


def test_unrelated_or_duplicate_component_observation_fails_closed():
    unrelated = build_company_telemetry_capability_observation(
        identity=_identity(),
        observation_id="telemetry-observation:DC9999:available",
        data_component_id="DC9999",
        status=CompanyTelemetryCapabilityStatus.AVAILABLE,
        telemetry_ref="telemetry:company-a:dc9999",
        evidence_refs=("company-evidence:DC9999:available",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    with pytest.raises(
        ValueError,
        match="company_detection_observation_not_required_by_global_context",
    ):
        assess_company_detection_coverage(
            identity=_identity(),
            global_enrichment=_global_receipt(),
            observations=(unrelated,),
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )

    duplicate = _observation(
        "DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE
    )
    with pytest.raises(ValueError, match="company_detection_duplicate_component_observation"):
        assess_company_detection_coverage(
            identity=_identity(),
            global_enrichment=_global_receipt(),
            observations=(duplicate, duplicate),
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )


def test_global_context_without_detection_components_does_not_invent_company_gap():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(with_components=False),
        observations=(),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.coverage_status is CompanyDetectionCoverageStatus.NO_GLOBAL_REQUIREMENTS
    assert receipt.required_data_component_ids == ()
    assert receipt.missing_component_ids == ()
    assert receipt.unverified_component_ids == ()
    assert receipt.verified_coverage_ratio is None
    assert receipt.firm_company_detection_claim_authorized is False


def test_missing_capability_requires_explicit_company_evidence_and_cannot_claim_telemetry():
    with pytest.raises(ValidationError, match="company_detection_missing_cannot_claim_live_telemetry"):
        build_company_telemetry_capability_observation(
            identity=_identity(),
            observation_id="telemetry-observation:DC0061:missing",
            data_component_id="DC0061",
            status=CompanyTelemetryCapabilityStatus.MISSING,
            telemetry_ref="telemetry:should-not-exist",
            evidence_refs=("company-evidence:DC0061:missing",),
            observed_at=NOW,
            recorded_at=NOW,
        )


def test_tampered_detection_coverage_receipt_fails_integrity_or_semantic_validation():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    tampered = receipt.model_copy(
        update={"coverage_status": CompanyDetectionCoverageStatus.COVERED}
    )

    with pytest.raises(ValidationError):
        verify_company_detection_coverage_receipt(receipt=tampered)


def test_detection_coverage_receipt_never_grants_remediation_or_execution_authority():
    receipt = assess_company_detection_coverage(
        identity=_identity(),
        global_enrichment=_global_receipt(),
        observations=(
            _observation("DC0039", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
            _observation("DC0061", status=CompanyTelemetryCapabilityStatus.AVAILABLE),
        ),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    payload = receipt.model_dump(mode="json")
    payload["execution_authority_granted"] = True

    with pytest.raises(ValidationError, match="company_detection_never_grants_execution_authority"):
        CompanyDetectionCoverageReceipt.model_validate(payload)
