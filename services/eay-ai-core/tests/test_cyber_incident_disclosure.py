from __future__ import annotations

from datetime import UTC, datetime

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
from app.cyber_incident_disclosure import (
    CyberIncidentAudiencePolicy,
    CyberIncidentDisclosureLevel,
    CyberIncidentLanguage,
    CyberIncidentRecipient,
    build_cyber_incident_audience_policy,
    evaluate_cyber_incident_disclosure,
)

T1 = datetime(2026, 8, 19, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 19, 9, tzinfo=UTC)


def _company(*, tenant: str = "tenant-a", company: str = "company-a"):
    return build_company_identity(
        tenant_id=tenant,
        company_id=company,
        company_slug=company,
        profile_revision="rev-1",
        environment="production",
    )


def _signal(identity, *, signal_id: str, strength, family, signal_type):
    return build_company_security_signal(
        identity=identity,
        signal_id=signal_id,
        signal_type=signal_type,
        evidence_strength=strength,
        source_family=family,
        evidence_refs=(f"evidence:{family.value}:{signal_id}",),
        asset_refs=("asset:edge-1",),
        observed_at=T1,
        recorded_at=T1,
    )


def _incident(*, status: IncidentStatus = IncidentStatus.CONFIRMED):
    identity = _company()
    if status is IncidentStatus.CONFIRMED:
        signals = (
            _signal(
                identity,
                signal_id="endpoint-1",
                strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
                family=SecuritySourceFamily.ENDPOINT,
                signal_type=SecuritySignalType.MALWARE_DETECTION,
            ),
            _signal(
                identity,
                signal_id="network-1",
                strength=SecurityEvidenceStrength.CORRELATED,
                family=SecuritySourceFamily.NETWORK,
                signal_type=SecuritySignalType.NETWORK_INDICATOR,
            ),
        )
    elif status is IncidentStatus.SUSPICIOUS:
        signals = (
            _signal(
                identity,
                signal_id="endpoint-1",
                strength=SecurityEvidenceStrength.VERIFIED_DETECTION,
                family=SecuritySourceFamily.ENDPOINT,
                signal_type=SecuritySignalType.MALWARE_DETECTION,
            ),
        )
    else:
        signals = (
            _signal(
                identity,
                signal_id="endpoint-1",
                strength=SecurityEvidenceStrength.OBSERVATION,
                family=SecuritySourceFamily.ENDPOINT,
                signal_type=SecuritySignalType.ANOMALOUS_PROCESS,
            ),
        )
    incident = assess_company_incident(
        identity=identity,
        incident_id=f"incident-{status.value}",
        signals=signals,
        as_of=T2,
    )
    assert incident.status is status
    return incident


def _policy():
    return build_cyber_incident_audience_policy(
        identity=_company(),
        policy_id="cyber-audience:company-a:v1",
        owner_principal_ref="principal:erdi",
        designated_principal_refs=(
            "principal:security-lead",
            "principal:executive-oncall",
        ),
    )


def _recipient(principal: str, *, company: str = "company-a"):
    return CyberIncidentRecipient(
        identity=_company(company=company),
        principal_ref=principal,
    )


def test_owner_receives_full_confirmed_incident_details() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(),
        policy=_policy(),
        recipient=_recipient("principal:erdi"),
        operational_impact_required=True,
        operational_impact_message_ref="operational-impact:temporary-access-restriction",
    )
    assert decision.level is CyberIncidentDisclosureLevel.FULL_INCIDENT
    assert decision.incident_language is CyberIncidentLanguage.CONFIRMED_CYBER_INCIDENT
    assert decision.disclose_incident_nature is True
    assert decision.disclose_sensitive_evidence_refs is True
    assert decision.execution_authority_granted is False


def test_explicit_designated_principal_receives_full_details() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(),
        policy=_policy(),
        recipient=_recipient("principal:security-lead"),
        operational_impact_required=False,
    )
    assert decision.level is CyberIncidentDisclosureLevel.FULL_INCIDENT


def test_ordinary_user_receives_only_operational_impact_without_cyber_nature() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(),
        policy=_policy(),
        recipient=_recipient("principal:warehouse-manager-42"),
        operational_impact_required=True,
        operational_impact_message_ref="operational-impact:service-degradation",
    )
    assert decision.level is CyberIncidentDisclosureLevel.OPERATIONAL_IMPACT_ONLY
    assert decision.incident_language is None
    assert decision.disclose_incident_nature is False
    assert decision.disclose_sensitive_evidence_refs is False


def test_ordinary_user_receives_nothing_without_operational_impact() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(),
        policy=_policy(),
        recipient=_recipient("principal:warehouse-manager-42"),
        operational_impact_required=False,
    )
    assert decision.level is CyberIncidentDisclosureLevel.NONE
    assert decision.incident_language is None


def test_cross_company_recipient_learns_nothing_about_incident() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(),
        policy=_policy(),
        recipient=_recipient("principal:company-b-security", company="company-b"),
        operational_impact_required=True,
        operational_impact_message_ref="operational-impact:service-degradation",
    )
    assert decision.level is CyberIncidentDisclosureLevel.NONE
    assert decision.disclose_incident_nature is False
    assert decision.operational_impact_message_ref is None


def test_unconfirmed_event_is_never_labeled_as_confirmed_attack() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(status=IncidentStatus.UNCONFIRMED),
        policy=_policy(),
        recipient=_recipient("principal:erdi"),
        operational_impact_required=False,
    )
    assert decision.incident_language is CyberIncidentLanguage.POSSIBLE_SECURITY_EVENT
    assert decision.incident_language is not CyberIncidentLanguage.CONFIRMED_CYBER_INCIDENT


def test_suspicious_event_preserves_uncertainty_language() -> None:
    decision = evaluate_cyber_incident_disclosure(
        incident=_incident(status=IncidentStatus.SUSPICIOUS),
        policy=_policy(),
        recipient=_recipient("principal:erdi"),
        operational_impact_required=False,
    )
    assert decision.incident_language is CyberIncidentLanguage.SUSPICIOUS_CYBER_INCIDENT


def test_broad_role_or_company_wide_disclosure_cannot_be_enabled() -> None:
    policy = _policy()
    with pytest.raises(ValidationError, match="cyber_incident_role_based_full_disclosure_forbidden"):
        CyberIncidentAudiencePolicy.model_validate(
            {**policy.model_dump(mode="json"), "role_based_full_disclosure_allowed": True}
        )
    with pytest.raises(ValidationError, match="cyber_incident_company_wide_full_disclosure_forbidden"):
        CyberIncidentAudiencePolicy.model_validate(
            {**policy.model_dump(mode="json"), "company_wide_full_disclosure_allowed": True}
        )


def test_owner_cannot_be_duplicated_into_designated_list() -> None:
    with pytest.raises(ValidationError, match="cyber_incident_owner_must_not_be_duplicated"):
        build_cyber_incident_audience_policy(
            identity=_company(),
            policy_id="cyber-audience:company-a:v1",
            owner_principal_ref="principal:erdi",
            designated_principal_refs=("principal:erdi",),
        )


def test_policy_tamper_fails_closed() -> None:
    policy = _policy()
    tampered = policy.model_copy(update={"owner_principal_ref": "principal:other-owner"})
    with pytest.raises(ValidationError, match="cyber_incident_audience_policy_fingerprint_mismatch"):
        CyberIncidentAudiencePolicy.model_validate(tampered.model_dump(mode="json"))


def test_policy_for_different_company_cannot_disclose_incident() -> None:
    policy = build_cyber_incident_audience_policy(
        identity=_company(company="company-b"),
        policy_id="cyber-audience:company-b:v1",
        owner_principal_ref="principal:company-b-owner",
    )
    with pytest.raises(ValueError, match="cyber_incident_disclosure_policy_company_mismatch"):
        evaluate_cyber_incident_disclosure(
            incident=_incident(),
            policy=policy,
            recipient=_recipient("principal:company-b-owner", company="company-b"),
            operational_impact_required=False,
        )


def test_non_privileged_operational_message_must_be_impact_only() -> None:
    with pytest.raises(ValueError, match="cyber_incident_operational_message_must_be_impact_only"):
        evaluate_cyber_incident_disclosure(
            incident=_incident(),
            policy=_policy(),
            recipient=_recipient("principal:warehouse-manager-42"),
            operational_impact_required=True,
            operational_impact_message_ref="cyber-incident:confirmed-malware-details",
        )
