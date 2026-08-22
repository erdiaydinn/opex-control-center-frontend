from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.company_context_boundary import build_company_identity
from app.cyber_defense_intelligence import (
    AssetCriticality,
    DefensiveAction,
    DefensivePriority,
    ExposureStatus,
    PatchStatus,
    ThreatFreshness,
    ThreatIntelligenceSource,
    ThreatKnowledgeLedgerSnapshot,
    append_threat_record,
    assess_threat_freshness,
    build_company_exposure,
    build_defensive_response_candidate,
    build_threat_record,
    new_threat_ledger,
    prioritize_company_exposure,
    threat_ledger_as_of,
    verify_exposure_binding,
)

T1 = datetime(2026, 8, 17, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 18, 8, tzinfo=UTC)
T3 = datetime(2026, 8, 19, 8, tzinfo=UTC)


def _company(*, tenant: str = "tenant-a", company: str = "company-a"):
    return build_company_identity(
        tenant_id=tenant,
        company_id=company,
        company_slug=company,
        profile_revision="rev-1",
        environment="production",
    )


def _kev(*, record_id: str = "threat-1", recorded_at: datetime = T2):
    return build_threat_record(
        record_id=record_id,
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-0001",
        published_at=T1,
        recorded_at=recorded_at,
        source_evidence_ref="cisa:kev:2026-0001",
        product_refs=("product:edge-gateway",),
        cve_ids=("CVE-2026-0001",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )


def _confirmed_exposure(identity, threat):
    return build_company_exposure(
        identity=identity,
        threat=threat,
        exposure_id="exposure-1",
        asset_ref="asset:edge-gateway-1",
        company_evidence_refs=("evidence:scanner:asset-edge-gateway-1",),
        status=ExposureStatus.CONFIRMED_EXPOSED,
        criticality=AssetCriticality.CRITICAL,
        patch_status=PatchStatus.UNPATCHED,
        internet_reachable=True,
        privileged_identity_surface=True,
        assessed_at=T2,
        recorded_at=T2,
    )


def test_global_kev_never_proves_company_exposure_or_incident() -> None:
    threat = _kev()
    assert threat.known_exploited_in_wild is True
    assert threat.company_truth_granted is False
    assert threat.incident_confirmation_granted is False
    assert threat.execution_authority_granted is False

    with pytest.raises(ValueError, match="cyber_exposure_company_evidence_required"):
        build_company_exposure(
            identity=_company(),
            threat=threat,
            exposure_id="exposure-no-proof",
            asset_ref="asset:edge-gateway-1",
            company_evidence_refs=(),
            status=ExposureStatus.CONFIRMED_EXPOSED,
            criticality=AssetCriticality.CRITICAL,
            assessed_at=T2,
            recorded_at=T2,
        )


def test_known_exploited_flag_is_not_inferred_from_non_kev_source() -> None:
    with pytest.raises(ValueError, match="cyber_known_exploited_requires_kev_source"):
        build_threat_record(
            record_id="threat-nvd",
            source=ThreatIntelligenceSource.NVD,
            source_record_id="CVE-2026-0002",
            published_at=T1,
            recorded_at=T2,
            source_evidence_ref="nvd:cve:2026-0002",
            cve_ids=("CVE-2026-0002",),
            known_exploited_in_wild=True,
        )


def test_global_threat_can_be_shared_but_company_exposure_cannot_cross_boundary() -> None:
    threat = _kev()
    company_a = _company(tenant="tenant-a", company="company-a")
    company_b = _company(tenant="tenant-b", company="company-b")
    exposure_a = _confirmed_exposure(company_a, threat)

    verify_exposure_binding(identity=company_a, threat=threat, exposure=exposure_a)
    with pytest.raises(ValueError, match="cyber_exposure_company_identity_mismatch"):
        verify_exposure_binding(identity=company_b, threat=threat, exposure=exposure_a)


def test_threat_ledger_is_append_only_idempotent_and_conflict_safe() -> None:
    threat = _kev()
    ledger = new_threat_ledger(as_of=T3)
    once = append_threat_record(ledger=ledger, record=threat, as_of=T3)
    twice = append_threat_record(ledger=once, record=threat, as_of=T3)
    assert len(twice.records) == 1
    assert twice.records[0].fingerprint == threat.fingerprint

    changed = build_threat_record(
        record_id=threat.record_id,
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-0001",
        published_at=T1,
        recorded_at=T2,
        source_evidence_ref="cisa:kev:2026-0001",
        product_refs=("product:edge-gateway",),
        cve_ids=("CVE-2026-0001",),
        severity_score=8.8,
        known_exploited_in_wild=True,
    )
    with pytest.raises(ValueError, match="cyber_threat_record_identity_payload_conflict"):
        append_threat_record(ledger=once, record=changed, as_of=T3)


def test_historical_view_filters_future_recorded_intelligence() -> None:
    threat = _kev(recorded_at=T3)
    ledger = append_threat_record(
        ledger=new_threat_ledger(as_of=T3),
        record=threat,
        as_of=T3,
    )
    historical = threat_ledger_as_of(ledger=ledger, as_of=T2)
    assert historical.records == ()
    assert assess_threat_freshness(record=threat, as_of=T2) is ThreatFreshness.FUTURE_DATED


def test_risk_priority_uses_company_exposure_but_remains_advisory() -> None:
    identity = _company()
    threat = _kev()
    exposure = _confirmed_exposure(identity, threat)
    assessment = prioritize_company_exposure(
        identity=identity,
        threat=threat,
        exposure=exposure,
    )
    assert assessment.priority is DefensivePriority.CRITICAL
    assert assessment.score == 100
    assert "known_exploited_in_wild" in assessment.reason_codes
    assert "internet_reachable" in assessment.reason_codes
    assert assessment.advisory_only is True
    assert assessment.execution_authority_granted is False


def test_company_evidence_not_exposed_forces_zero_score() -> None:
    identity = _company()
    threat = _kev()
    exposure = build_company_exposure(
        identity=identity,
        threat=threat,
        exposure_id="exposure-not-exposed",
        asset_ref="asset:edge-gateway-1",
        company_evidence_refs=("evidence:inventory:no-match",),
        status=ExposureStatus.NOT_EXPOSED,
        criticality=AssetCriticality.CRITICAL,
        patch_status=PatchStatus.NOT_APPLICABLE,
        assessed_at=T2,
        recorded_at=T2,
    )
    assessment = prioritize_company_exposure(
        identity=identity,
        threat=threat,
        exposure=exposure,
    )
    assert assessment.score == 0
    assert assessment.priority is DefensivePriority.LOW
    assert "company_evidence_not_exposed" in assessment.reason_codes


def test_mutating_defensive_candidate_requires_approval_and_effect_verification() -> None:
    identity = _company()
    threat = _kev()
    exposure = _confirmed_exposure(identity, threat)

    with pytest.raises(ValueError, match="cyber_mutating_response_requires_human_approval"):
        build_defensive_response_candidate(
            identity=identity,
            threat=threat,
            exposure=exposure,
            candidate_id="response-1",
            action=DefensiveAction.PATCH_OR_UPDATE,
            target_ref="asset:edge-gateway-1",
            evidence_refs=("evidence:scanner:asset-edge-gateway-1",),
            requires_human_approval=False,
        )

    candidate = build_defensive_response_candidate(
        identity=identity,
        threat=threat,
        exposure=exposure,
        candidate_id="response-2",
        action=DefensiveAction.PATCH_OR_UPDATE,
        target_ref="asset:edge-gateway-1",
        evidence_refs=("evidence:scanner:asset-edge-gateway-1",),
        requires_human_approval=True,
    )
    assert candidate.requires_effect_verification is True
    assert candidate.execution_authority_granted is False


def test_secret_or_offensive_payload_references_are_rejected() -> None:
    with pytest.raises(ValueError, match="cyber_threat_unsafe_reference_forbidden"):
        build_threat_record(
            record_id="threat-unsafe",
            source=ThreatIntelligenceSource.NVD,
            source_record_id="CVE-2026-0003",
            published_at=T1,
            recorded_at=T2,
            source_evidence_ref="evidence:exploit_payload:raw",
            cve_ids=("CVE-2026-0003",),
        )

    identity = _company()
    threat = _kev()
    exposure = _confirmed_exposure(identity, threat)
    with pytest.raises(ValueError, match="cyber_response_unsafe_reference_forbidden"):
        build_defensive_response_candidate(
            identity=identity,
            threat=threat,
            exposure=exposure,
            candidate_id="response-unsafe",
            action=DefensiveAction.INCREASE_TELEMETRY,
            target_ref="asset:edge-gateway-1",
            evidence_refs=("authorization:bearer-material",),
            requires_human_approval=False,
        )


def test_tampered_ledger_fingerprint_fails_closed() -> None:
    ledger = append_threat_record(
        ledger=new_threat_ledger(as_of=T3),
        record=_kev(),
        as_of=T3,
    )
    tampered = ledger.model_copy(update={"as_of": datetime(2026, 8, 20, 8, tzinfo=UTC)})
    with pytest.raises(ValueError, match="cyber_threat_ledger_fingerprint_mismatch"):
        ThreatKnowledgeLedgerSnapshot.model_validate(tampered.model_dump(mode="json"))
