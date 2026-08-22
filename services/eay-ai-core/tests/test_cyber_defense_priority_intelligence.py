from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    IncidentStatus,
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    assess_company_incident,
    build_company_security_signal,
)
from app.cyber_defense_intelligence import (
    AssetCriticality,
    DefensivePriority,
    ExposureStatus,
    PatchStatus,
    ThreatIntelligenceSource,
    build_company_exposure,
    build_threat_record,
)
from app.cyber_defense_priority_intelligence import (
    CompanyExposureClaim,
    CompanyThreatDisposition,
    DefensivePriorityReceipt,
    build_defensive_priority_receipt,
    verify_defensive_priority_receipt,
)

NOW = datetime(2026, 8, 19, 18, 30, tzinfo=UTC)


def _identity(suffix: str = "a"):
    return build_company_identity(
        tenant_id=f"tenant-{suffix}",
        company_id=f"company-{suffix}",
        company_slug=f"company-{suffix}",
        profile_revision="rev-1",
        environment="production",
    )


def _threat(*, product_refs: tuple[str, ...] = ()):
    return build_threat_record(
        record_id="threat:CVE-2026-9001",
        source=ThreatIntelligenceSource.CISA_KEV,
        source_record_id="CVE-2026-9001",
        published_at=NOW - timedelta(hours=2),
        recorded_at=NOW - timedelta(hours=1),
        source_evidence_ref="cisa-kev:CVE-2026-9001",
        product_refs=product_refs,
        cve_ids=("CVE-2026-9001",),
        severity_score=9.8,
        known_exploited_in_wild=True,
    )


def _exposure(
    *,
    identity,
    threat,
    status: ExposureStatus,
    assessed_at: datetime = NOW - timedelta(minutes=15),
    evidence_refs: tuple[str, ...] = ("scanner:asset-a",),
):
    return build_company_exposure(
        identity=identity,
        threat=threat,
        exposure_id="exposure:asset-a:CVE-2026-9001",
        asset_ref="asset:prod-api-a",
        company_evidence_refs=evidence_refs,
        status=status,
        criticality=AssetCriticality.CRITICAL,
        assessed_at=assessed_at,
        recorded_at=assessed_at,
        patch_status=PatchStatus.UNPATCHED,
        internet_reachable=True,
        privileged_identity_surface=True,
    )


def _confirmed_incident(*, identity, threat, exposure):
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
        observed_at=NOW - timedelta(minutes=9),
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
        recorded_at=NOW - timedelta(minutes=6),
    )
    signals = (first, second)
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident:company-a:1",
        signals=signals,
        as_of=NOW - timedelta(minutes=5),
    )
    assert incident.status is IncidentStatus.CONFIRMED
    return incident, signals


def test_global_critical_unknown_company_exposure_holds_firm_priority():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.UNKNOWN,
        evidence_refs=(),
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.global_threat_priority is DefensivePriority.CRITICAL
    assert receipt.company_defensive_priority is None
    assert receipt.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert receipt.disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE
    assert receipt.firm_company_exposure_claim_authorized is False
    assert receipt.exploit_generation_permitted is False
    assert receipt.execution_authority_granted is False


def test_global_product_presence_without_company_exposure_never_authorizes_company_impact():
    identity = _identity()
    threat = _threat(product_refs=("package:example-lib",))
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.UNKNOWN,
        evidence_refs=(),
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.global_threat_priority is DefensivePriority.CRITICAL
    assert receipt.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert receipt.firm_company_exposure_claim_authorized is False
    assert receipt.company_defensive_priority is None


def test_potential_company_exposure_prioritizes_verification_without_firm_impact_claim():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.POTENTIALLY_EXPOSED,
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.disposition is CompanyThreatDisposition.PRIORITIZE_VERIFICATION
    assert receipt.exposure_claim is CompanyExposureClaim.POSSIBLY_AFFECTED
    assert receipt.firm_company_exposure_claim_authorized is False
    assert receipt.company_defensive_priority is None


def test_confirmed_deployed_exposure_can_elevate_company_priority():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.exposure_claim is CompanyExposureClaim.AFFECTED
    assert receipt.firm_company_exposure_claim_authorized is True
    assert receipt.company_defensive_priority in {
        DefensivePriority.HIGH,
        DefensivePriority.CRITICAL,
    }
    assert receipt.disposition is CompanyThreatDisposition.PRIORITIZE_MITIGATION


def test_verified_same_company_linked_incident_can_make_priority_urgent():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
    )
    incident, signals = _confirmed_incident(
        identity=identity,
        threat=threat,
        exposure=exposure,
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        incident=incident,
        incident_signals=signals,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.disposition is CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE
    assert receipt.company_defensive_priority is DefensivePriority.CRITICAL
    assert receipt.firm_company_incident_claim_authorized is True
    assert receipt.causal_claim_authorized is False
    assert receipt.actor_attribution_authorized is False
    assert len(receipt.linked_incident_signal_fingerprints) == 2


def test_cross_company_exposure_is_rejected():
    identity = _identity("a")
    other = _identity("b")
    threat = _threat()
    exposure = _exposure(
        identity=other,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
    )

    with pytest.raises(ValueError, match="cyber_exposure_company_identity_mismatch"):
        build_defensive_priority_receipt(
            identity=identity,
            threat=threat,
            exposure=exposure,
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )


def test_cross_company_incident_is_rejected():
    identity = _identity("a")
    other = _identity("b")
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
    )
    other_exposure = _exposure(
        identity=other,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
    )
    incident, signals = _confirmed_incident(
        identity=other,
        threat=threat,
        exposure=other_exposure,
    )

    with pytest.raises(ValueError, match="cyber_priority_cross_company_incident_forbidden"):
        build_defensive_priority_receipt(
            identity=identity,
            threat=threat,
            exposure=exposure,
            incident=incident,
            incident_signals=signals,
            as_of=NOW,
            max_company_evidence_age_seconds=3600,
        )


def test_stale_company_exposure_evidence_holds_firm_impact_claim():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.CONFIRMED_EXPOSED,
        assessed_at=NOW - timedelta(days=2),
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.company_evidence_current is False
    assert receipt.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert receipt.firm_company_exposure_claim_authorized is False
    assert receipt.disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE


def test_not_exposed_without_company_evidence_is_not_treated_as_safe():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.NOT_EXPOSED,
        evidence_refs=(),
    )

    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )

    assert receipt.exposure_claim is CompanyExposureClaim.UNRESOLVED
    assert receipt.firm_company_exposure_claim_authorized is False
    assert receipt.disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE


def test_tampered_priority_receipt_fails_integrity_verification():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.UNKNOWN,
        evidence_refs=(),
    )
    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    tampered = receipt.model_copy(
        update={"disposition": CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE}
    )

    with pytest.raises(ValueError):
        verify_defensive_priority_receipt(receipt=tampered)


def test_offensive_fields_are_rejected_by_priority_contract():
    identity = _identity()
    threat = _threat()
    exposure = _exposure(
        identity=identity,
        threat=threat,
        status=ExposureStatus.UNKNOWN,
        evidence_refs=(),
    )
    receipt = build_defensive_priority_receipt(
        identity=identity,
        threat=threat,
        exposure=exposure,
        as_of=NOW,
        max_company_evidence_age_seconds=3600,
    )
    payload = receipt.model_dump(mode="json")
    payload["exploit_payload"] = "forbidden"

    with pytest.raises(ValidationError):
        DefensivePriorityReceipt.model_validate(payload)


def test_global_threat_record_remains_tenant_neutral():
    threat = _threat()
    payload = threat.model_dump(mode="json")

    assert "identity" not in payload
    assert "tenant_id" not in payload
    assert "company_id" not in payload
    assert threat.company_truth_granted is False
    assert threat.incident_confirmation_granted is False
    assert threat.execution_authority_granted is False
