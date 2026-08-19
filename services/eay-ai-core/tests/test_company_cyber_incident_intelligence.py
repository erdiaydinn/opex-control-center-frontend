from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    CompanyCyberDefensePlan,
    IncidentStatus,
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    assess_company_incident,
    build_company_cyber_defense_plan,
    build_company_security_signal,
)
from app.cyber_defense_intelligence import DefensiveAction

T1 = datetime(2026, 8, 19, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 19, 9, tzinfo=UTC)
T3 = datetime(2026, 8, 19, 10, tzinfo=UTC)


def _company(*, tenant: str = "tenant-a", company: str = "company-a"):
    return build_company_identity(
        tenant_id=tenant,
        company_id=company,
        company_slug=company,
        profile_revision="rev-1",
        environment="production",
    )


def _signal(
    identity,
    *,
    signal_id: str,
    strength: SecurityEvidenceStrength,
    family: SecuritySourceFamily,
    signal_type: SecuritySignalType = SecuritySignalType.ANOMALOUS_PROCESS,
    observed_at: datetime = T1,
    recorded_at: datetime = T1,
    techniques: tuple[str, ...] = (),
):
    return build_company_security_signal(
        identity=identity,
        signal_id=signal_id,
        signal_type=signal_type,
        evidence_strength=strength,
        source_family=family,
        evidence_refs=(f"evidence:{family.value}:{signal_id}",),
        asset_refs=("asset:workload-1",),
        attack_technique_ids=techniques,
        observed_at=observed_at,
        recorded_at=recorded_at,
    )


def test_single_vulnerability_or_kev_related_observation_never_confirms_incident() -> None:
    identity = _company()
    signal = build_company_security_signal(
        identity=identity,
        signal_id="vuln-1",
        signal_type=SecuritySignalType.VULNERABILITY_EXPOSURE,
        evidence_strength=SecurityEvidenceStrength.OBSERVATION,
        source_family=SecuritySourceFamily.VULNERABILITY,
        evidence_refs=("evidence:scanner:vuln-1",),
        asset_refs=("asset:edge-1",),
        exposure_refs=("exposure:kev:cve-2026-1",),
        threat_record_refs=("cisa-kev:cve-2026-1",),
        observed_at=T1,
        recorded_at=T1,
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-1",
        signals=(signal,),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.UNCONFIRMED
    assert incident.threat_actor_attribution_proven is False
    assert incident.causal_claim_proven is False
    assert incident.execution_authority_granted is False


def test_one_verified_detection_without_independent_quorum_is_suspicious() -> None:
    identity = _company()
    signal = _signal(
        identity,
        signal_id="endpoint-1",
        strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        family=SecuritySourceFamily.ENDPOINT,
        techniques=("T1059",),
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-2",
        signals=(signal,),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.SUSPICIOUS
    assert "verified_detection_without_independent_quorum" in incident.reason_codes
    assert incident.attack_technique_ids == ("T1059",)
    assert incident.threat_actor_attribution_proven is False


def test_verified_detection_plus_independent_signal_can_confirm_incident() -> None:
    identity = _company()
    endpoint = _signal(
        identity,
        signal_id="endpoint-1",
        strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        family=SecuritySourceFamily.ENDPOINT,
        techniques=("T1059",),
    )
    network = _signal(
        identity,
        signal_id="network-1",
        strength=SecurityEvidenceStrength.CORRELATED,
        family=SecuritySourceFamily.NETWORK,
        signal_type=SecuritySignalType.NETWORK_INDICATOR,
        techniques=("T1071.001",),
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-3",
        signals=(endpoint, network),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.CONFIRMED
    assert "verified_company_detection" in incident.reason_codes
    assert "independent_company_signal_quorum" in incident.reason_codes
    assert set(incident.attack_technique_ids) == {"T1059", "T1071.001"}
    assert incident.threat_actor_attribution_proven is False
    assert incident.causal_claim_proven is False


def test_explicit_human_confirmation_can_confirm_without_actor_attribution() -> None:
    identity = _company()
    human = _signal(
        identity,
        signal_id="human-1",
        strength=SecurityEvidenceStrength.HUMAN_CONFIRMATION,
        family=SecuritySourceFamily.HUMAN,
        signal_type=SecuritySignalType.MALWARE_DETECTION,
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-4",
        signals=(human,),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.CONFIRMED
    assert incident.reason_codes == ("human_incident_confirmation",)
    assert incident.actor_attribution_ref is None
    assert incident.threat_actor_attribution_proven is False


def test_cross_company_signal_is_rejected() -> None:
    company_a = _company(tenant="tenant-a", company="company-a")
    company_b = _company(tenant="tenant-b", company="company-b")
    signal = _signal(
        company_a,
        signal_id="signal-a",
        strength=SecurityEvidenceStrength.CORRELATED,
        family=SecuritySourceFamily.IDENTITY,
    )
    with pytest.raises(ValueError, match="cyber_incident_cross_company_signal_forbidden"):
        assess_company_incident(
            identity=company_b,
            incident_id="incident-cross-company",
            signals=(signal,),
            as_of=T2,
        )


def test_future_recorded_signal_cannot_leak_into_historical_incident() -> None:
    identity = _company()
    known = _signal(
        identity,
        signal_id="known",
        strength=SecurityEvidenceStrength.OBSERVATION,
        family=SecuritySourceFamily.ENDPOINT,
    )
    future_known = _signal(
        identity,
        signal_id="future",
        strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        family=SecuritySourceFamily.NETWORK,
        observed_at=T1,
        recorded_at=T3,
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-historical",
        signals=(known, future_known),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.UNCONFIRMED
    assert incident.signal_ids == ("known",)


def test_defense_plan_maps_company_signals_to_candidates_without_authority() -> None:
    identity = _company()
    endpoint = _signal(
        identity,
        signal_id="endpoint",
        strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        family=SecuritySourceFamily.ENDPOINT,
        signal_type=SecuritySignalType.MALWARE_DETECTION,
        techniques=("T1059",),
    )
    identity_signal = _signal(
        identity,
        signal_id="identity",
        strength=SecurityEvidenceStrength.CORRELATED,
        family=SecuritySourceFamily.IDENTITY,
        signal_type=SecuritySignalType.IDENTITY_RISK,
    )
    vulnerability = _signal(
        identity,
        signal_id="vulnerability",
        strength=SecurityEvidenceStrength.OBSERVATION,
        family=SecuritySourceFamily.VULNERABILITY,
        signal_type=SecuritySignalType.VULNERABILITY_EXPOSURE,
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-plan",
        signals=(endpoint, identity_signal, vulnerability),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.CONFIRMED

    plan = build_company_cyber_defense_plan(
        identity=identity,
        incident=incident,
        signals=(endpoint, identity_signal, vulnerability),
        generated_at=T2,
    )
    actions = {candidate.action for candidate in plan.candidates}
    assert DefensiveAction.INCREASE_TELEMETRY in actions
    assert DefensiveAction.DEPLOY_DETECTION_RULE in actions
    assert DefensiveAction.PATCH_OR_UPDATE in actions
    assert DefensiveAction.REVOKE_SESSION_CANDIDATE in actions
    assert DefensiveAction.ROTATE_CREDENTIAL_CANDIDATE in actions
    assert DefensiveAction.ISOLATE_ASSET_CANDIDATE in actions
    assert DefensiveAction.BACKUP_RESTORE_READINESS in actions
    assert plan.automatic_execution_permitted is False
    assert plan.execution_authority_granted is False
    for candidate in plan.candidates:
        assert candidate.candidate_only is True
        assert candidate.requires_effect_verification is True
        assert candidate.execution_authority_granted is False
        if candidate.action not in {
            DefensiveAction.INCREASE_TELEMETRY,
            DefensiveAction.BACKUP_RESTORE_READINESS,
        }:
            assert candidate.requires_human_approval is True


def test_attack_mapping_does_not_prove_actor_or_cause() -> None:
    identity = _company()
    endpoint = _signal(
        identity,
        signal_id="mapped-1",
        strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
        family=SecuritySourceFamily.ENDPOINT,
        techniques=("T1059",),
    )
    network = _signal(
        identity,
        signal_id="mapped-2",
        strength=SecurityEvidenceStrength.CORRELATED,
        family=SecuritySourceFamily.NETWORK,
        techniques=("T1071",),
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-mapped",
        signals=(endpoint, network),
        as_of=T2,
    )
    assert incident.status is IncidentStatus.CONFIRMED
    assert incident.attack_technique_ids
    assert incident.actor_attribution_ref is None
    assert incident.threat_actor_attribution_proven is False
    assert incident.causal_claim_proven is False


def test_secret_or_offensive_references_are_rejected() -> None:
    identity = _company()
    with pytest.raises(ValueError, match="cyber_signal_unsafe_reference_forbidden"):
        build_company_security_signal(
            identity=identity,
            signal_id="unsafe",
            signal_type=SecuritySignalType.NETWORK_INDICATOR,
            evidence_strength=SecurityEvidenceStrength.OBSERVATION,
            source_family=SecuritySourceFamily.NETWORK,
            evidence_refs=("credential_dump:raw",),
            observed_at=T1,
            recorded_at=T1,
        )


def test_defense_plan_fingerprint_tamper_fails_closed() -> None:
    identity = _company()
    signal = _signal(
        identity,
        signal_id="signal-1",
        strength=SecurityEvidenceStrength.OBSERVATION,
        family=SecuritySourceFamily.ENDPOINT,
    )
    incident = assess_company_incident(
        identity=identity,
        incident_id="incident-tamper",
        signals=(signal,),
        as_of=T2,
    )
    plan = build_company_cyber_defense_plan(
        identity=identity,
        incident=incident,
        signals=(signal,),
        generated_at=T2,
    )
    tampered = plan.model_copy(update={"generated_at": T3})
    with pytest.raises(ValueError, match="cyber_defense_plan_fingerprint_mismatch"):
        CompanyCyberDefensePlan.model_validate(tampered.model_dump(mode="json"))
