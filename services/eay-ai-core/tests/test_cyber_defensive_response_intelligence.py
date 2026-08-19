from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    assess_company_incident,
    build_company_security_signal,
)
from app.company_detection_coverage_intelligence import (
    CompanyTelemetryCapabilityStatus,
    assess_company_detection_coverage,
    build_company_telemetry_capability_observation,
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
from app.cyber_defense_priority_intelligence import build_defensive_priority_receipt
from app.cyber_defensive_response_intelligence import (
    DefensiveResponseAction,
    DefensiveResponseMode,
    DefensiveResponseMutationClass,
    DefensiveResponsePlan,
    build_defensive_response_plan,
    verify_defensive_response_plan,
)
from app.cyber_threat_enrichment_intelligence import (
    build_attack_defensive_coverage,
    fuse_global_threat_intelligence,
)
from app.cyber_threat_source_freshness_intelligence import (
    attest_attack_source_freshness,
    build_authoritative_attack_release_observation,
)

NOW = datetime(2026, 8, 19, 20, 20, tzinfo=UTC)


def _identity(suffix: str = "a"):
    return build_company_identity(
        tenant_id=f"tenant-{suffix}",
        company_id=f"company-{suffix}",
        company_slug=f"company-{suffix}",
        profile_revision="rev-1",
        environment="production",
    )


def _threat():
    return build_threat_record(
        record_id="threat:CVE-2026-9001",
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-9001",
        published_at=NOW - timedelta(hours=4),
        recorded_at=NOW - timedelta(hours=3),
        source_evidence_ref="cisa-kev:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )


def _exposure(identity, threat, status: ExposureStatus, *, evidence=True):
    return build_company_exposure(
        identity=identity,
        threat=threat,
        exposure_id="exposure:asset-a:CVE-2026-9001",
        asset_ref="asset:prod-api-a",
        company_evidence_refs=("scanner:asset-a",) if evidence else (),
        status=status,
        criticality=AssetCriticality.CRITICAL,
        patch_status=(
            PatchStatus.UNPATCHED
            if status is ExposureStatus.CONFIRMED_EXPOSED
            else PatchStatus.UNKNOWN
        ),
        internet_reachable=status is ExposureStatus.CONFIRMED_EXPOSED,
        privileged_identity_surface=status is ExposureStatus.CONFIRMED_EXPOSED,
        compensating_control_present=False,
        assessed_at=NOW - timedelta(minutes=10),
        recorded_at=NOW - timedelta(minutes=10),
    )


def _priority(status: ExposureStatus, *, incident=False, identity=None):
    identity = identity or _identity()
    threat = _threat()
    exposure = _exposure(
        identity,
        threat,
        status,
        evidence=status is not ExposureStatus.UNKNOWN,
    )
    if not incident:
        return build_defensive_priority_receipt(
            identity=identity,
            threat=threat,
            exposure=exposure,
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )

    first = build_company_security_signal(
        identity=identity,
        signal_id="signal:endpoint-1",
        signal_type=SecuritySignalType.MALWARE_DETECTION,
        evidence_strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        source_family=SecuritySourceFamily.ENDPOINT,
        evidence_refs=("edr:detection-1",),
        asset_refs=(exposure.asset_ref,),
        exposure_refs=(exposure.exposure_id,),
        threat_record_refs=(threat.record_id,),
        observed_at=NOW - timedelta(minutes=8),
        recorded_at=NOW - timedelta(minutes=8),
    )
    second = build_company_security_signal(
        identity=identity,
        signal_id="signal:network-1",
        signal_type=SecuritySignalType.NETWORK_INDICATOR,
        evidence_strength=SecurityEvidenceStrength.CORRELATED,
        source_family=SecuritySourceFamily.NETWORK,
        evidence_refs=("network:detection-1",),
        asset_refs=(exposure.asset_ref,),
        exposure_refs=(exposure.exposure_id,),
        threat_record_refs=(threat.record_id,),
        observed_at=NOW - timedelta(minutes=7),
        recorded_at=NOW - timedelta(minutes=7),
    )
    signals = (first, second)
    company_incident = assess_company_incident(
        identity=identity,
        incident_id="incident:company-a:1",
        signals=signals,
        as_of=NOW - timedelta(minutes=5),
    )
    return build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        incident=company_incident,
        incident_signals=signals,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )


def _global_context(*, current: bool = True):
    attack = build_threat_record(
        record_id="threat:mitre:CVE-2026-9001",
        source=ThreatIntelligenceSource.MITRE_ATTACK,
        source_record_id="mitre:CVE-2026-9001",
        published_at=NOW - timedelta(days=2),
        recorded_at=NOW - timedelta(days=1),
        source_evidence_ref="mitre:CVE-2026-9001",
        cve_ids=("CVE-2026-9001",),
        attack_technique_ids=("T1059",),
    )
    coverage = build_attack_defensive_coverage(
        technique_id="T1059",
        attack_release_ref="mitre-attack:enterprise:v19.2",
        detection_strategy_ids=("DET0466",),
        data_component_ids=("DC0039", "DC0061"),
        telemetry_refs=("telemetry:process-events", "telemetry:file-events"),
        observed_at=NOW - timedelta(hours=2),
        recorded_at=NOW - timedelta(hours=1),
        source_evidence_ref="mitre:T1059:v19.2",
    )
    enrichment = fuse_global_threat_intelligence(
        cve_id="CVE-2026-9001",
        threat_records=(attack,),
        defensive_coverages=(coverage,),
        as_of=NOW - timedelta(minutes=30),
        max_epss_age_days=2,
    )
    authoritative = build_authoritative_attack_release_observation(
        release_ref="ATT&CK-v19.2",
        release_observed_at=NOW - timedelta(hours=1),
        recorded_at=NOW - timedelta(hours=1),
        evidence_ref="mitre-attack:update-2026-08-06:v19.2",
    )
    freshness = attest_attack_source_freshness(
        source_endpoint_ref="https://raw.githubusercontent.com/mitre/cti/release/enterprise-attack.json",
        source_content_fingerprint="a" * 64,
        ingested_release_ref="ATT&CK-v19.2" if current else "ATT&CK-v19.1",
        authoritative_release=authoritative,
        as_of=NOW,
    )
    context = build_current_threat_context(
        global_enrichment=enrichment,
        attack_freshness=freshness,
    )
    return enrichment, context


def _detection(identity, enrichment, *, second_status=None):
    first = build_company_telemetry_capability_observation(
        identity=identity,
        observation_id="obs:DC0039:available",
        data_component_id="DC0039",
        status=CompanyTelemetryCapabilityStatus.AVAILABLE,
        telemetry_ref="telemetry:company-a:process-events",
        evidence_refs=("company-evidence:DC0039:available",),
        observed_at=NOW - timedelta(minutes=5),
        recorded_at=NOW - timedelta(minutes=5),
    )
    observations = [first]
    if second_status is not None:
        observations.append(
            build_company_telemetry_capability_observation(
                identity=identity,
                observation_id=f"obs:DC0061:{second_status.value}",
                data_component_id="DC0061",
                status=second_status,
                telemetry_ref=(
                    "telemetry:company-a:file-events"
                    if second_status is not CompanyTelemetryCapabilityStatus.MISSING
                    else None
                ),
                evidence_refs=(f"company-evidence:DC0061:{second_status.value}",),
                observed_at=NOW - timedelta(minutes=5),
                recorded_at=NOW - timedelta(minutes=5),
            )
        )
    return assess_company_detection_coverage(
        identity=identity,
        global_enrichment=enrichment,
        observations=tuple(observations),
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )


def _actions(plan):
    return {candidate.action for candidate in plan.candidates}


def test_unknown_company_exposure_can_only_generate_read_only_verification():
    plan = build_defensive_response_plan(
        identity=_identity(),
        priority=_priority(ExposureStatus.UNKNOWN),
    )

    assert plan.mode is DefensiveResponseMode.VERIFY
    assert _actions(plan) == {DefensiveResponseAction.VERIFY_COMPANY_EXPOSURE}
    assert all(
        item.mutation_class is DefensiveResponseMutationClass.READ_ONLY_VERIFICATION
        for item in plan.candidates
    )
    assert plan.automatic_execution_permitted is False
    assert plan.execution_authority_granted is False


def test_potential_exposure_still_cannot_generate_patch_or_containment():
    plan = build_defensive_response_plan(
        identity=_identity(),
        priority=_priority(ExposureStatus.POTENTIALLY_EXPOSED),
    )

    assert plan.mode is DefensiveResponseMode.VERIFY
    assert DefensiveResponseAction.PREPARE_PATCH_OR_UPDATE not in _actions(plan)
    assert DefensiveResponseAction.PREPARE_ASSET_ISOLATION not in _actions(plan)


def test_confirmed_exposure_can_generate_human_reviewed_mitigation_candidates():
    plan = build_defensive_response_plan(
        identity=_identity(),
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED),
    )

    assert plan.mode is DefensiveResponseMode.MITIGATE
    assert {
        DefensiveResponseAction.PREPARE_PATCH_OR_UPDATE,
        DefensiveResponseAction.PREPARE_CONFIG_HARDENING,
        DefensiveResponseAction.VERIFY_BACKUP_RESTORE_READINESS,
    }.issubset(_actions(plan))
    mutating = [item for item in plan.candidates if item.action in {
        DefensiveResponseAction.PREPARE_PATCH_OR_UPDATE,
        DefensiveResponseAction.PREPARE_CONFIG_HARDENING,
    }]
    assert all(item.human_review_required for item in mutating)
    assert all(item.canonical_execution_path_required for item in mutating)
    assert all(item.automatic_execution_permitted is False for item in mutating)


def test_confirmed_linked_incident_can_generate_containment_candidates_but_not_execute():
    plan = build_defensive_response_plan(
        identity=_identity(),
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, incident=True),
    )

    assert plan.mode is DefensiveResponseMode.CONTAIN
    assert {
        DefensiveResponseAction.PREPARE_ASSET_ISOLATION,
        DefensiveResponseAction.PREPARE_SESSION_REVOCATION,
        DefensiveResponseAction.PREPARE_CREDENTIAL_ROTATION,
    }.issubset(_actions(plan))
    assert all(item.human_review_required for item in plan.candidates if item.mutation_class is DefensiveResponseMutationClass.MUTATING_DEFENSE_CANDIDATE)
    assert plan.execution_authority_granted is False


def test_confirmed_detection_gap_with_current_attack_context_can_prepare_detection_rule():
    identity = _identity()
    enrichment, context = _global_context(current=True)
    detection = _detection(
        identity,
        enrichment,
        second_status=CompanyTelemetryCapabilityStatus.MISSING,
    )
    plan = build_defensive_response_plan(
        identity=identity,
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, identity=identity),
        current_threat_context=context,
        detection_coverage=detection,
    )

    assert DefensiveResponseAction.PREPARE_DETECTION_RULE in _actions(plan)
    detection_candidate = next(
        item
        for item in plan.candidates
        if item.action is DefensiveResponseAction.PREPARE_DETECTION_RULE
    )
    assert detection_candidate.human_review_required is True
    assert detection_candidate.execution_authority_granted is False


def test_behind_attack_release_blocks_detection_rule_and_requests_refresh_instead():
    identity = _identity()
    enrichment, context = _global_context(current=False)
    detection = _detection(
        identity,
        enrichment,
        second_status=CompanyTelemetryCapabilityStatus.MISSING,
    )
    plan = build_defensive_response_plan(
        identity=identity,
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, identity=identity),
        current_threat_context=context,
        detection_coverage=detection,
    )

    assert DefensiveResponseAction.PREPARE_DETECTION_RULE not in _actions(plan)
    assert DefensiveResponseAction.REFRESH_THREAT_CONTEXT in _actions(plan)


def test_unverified_detection_coverage_requests_telemetry_verification_not_fake_rule_deployment():
    identity = _identity()
    enrichment, context = _global_context(current=True)
    detection = _detection(identity, enrichment, second_status=None)
    plan = build_defensive_response_plan(
        identity=identity,
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, identity=identity),
        current_threat_context=context,
        detection_coverage=detection,
    )

    assert DefensiveResponseAction.VERIFY_TELEMETRY_COVERAGE in _actions(plan)
    assert DefensiveResponseAction.PREPARE_DETECTION_RULE not in _actions(plan)


def test_detection_coverage_requires_exact_current_global_context_binding():
    identity = _identity()
    enrichment, _ = _global_context(current=True)
    detection = _detection(identity, enrichment, second_status=None)

    with pytest.raises(ValueError, match="cyber_response_detection_requires_current_threat_context"):
        build_defensive_response_plan(
            identity=identity,
            priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, identity=identity),
            detection_coverage=detection,
        )


def test_cross_company_priority_or_detection_cannot_enter_response_plan():
    with pytest.raises(ValueError, match="cyber_response_priority_company_mismatch"):
        build_defensive_response_plan(
            identity=_identity("a"),
            priority=_priority(ExposureStatus.CONFIRMED_EXPOSED, identity=_identity("b")),
        )


def test_tamper_cannot_enable_automatic_execution_or_remove_review_boundary():
    plan = build_defensive_response_plan(
        identity=_identity(),
        priority=_priority(ExposureStatus.CONFIRMED_EXPOSED),
    )
    payload = plan.model_dump(mode="json")
    payload["automatic_execution_permitted"] = True

    with pytest.raises(ValidationError, match="cyber_response_plan_automatic_execution_forbidden"):
        DefensiveResponsePlan.model_validate(payload)

    tampered = plan.model_copy(update={"execution_authority_granted": True})
    with pytest.raises(ValidationError):
        verify_defensive_response_plan(plan=tampered)
