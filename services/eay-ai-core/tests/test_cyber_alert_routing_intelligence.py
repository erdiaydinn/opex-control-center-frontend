from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.alert_intelligence import (
    AlertCandidate,
    PriorAlertState,
    evaluate_alert_policy,
)
from app.company_context_boundary import build_company_identity
from app.company_cyber_incident_intelligence import (
    SecurityEvidenceStrength,
    SecuritySignalType,
    SecuritySourceFamily,
    assess_company_incident,
    build_company_security_signal,
)
from app.cyber_alert_routing import (
    CyberAlertDeliveryLevel,
    CyberAlertRoutingDecision,
    route_cyber_alert,
)
from app.cyber_incident_disclosure import (
    CyberIncidentLanguage,
    CyberIncidentRecipient,
    build_cyber_incident_audience_policy,
    evaluate_cyber_incident_disclosure,
)

T1 = datetime(2026, 8, 19, 8, tzinfo=UTC)
T2 = datetime(2026, 8, 19, 9, tzinfo=UTC)


def _company(*, company: str = "company-a"):
    return build_company_identity(
        tenant_id="tenant-a",
        company_id=company,
        company_slug=company,
        profile_revision="rev-1",
        environment="production",
    )


def _signal(identity, *, signal_id: str, family: SecuritySourceFamily):
    return build_company_security_signal(
        identity=identity,
        signal_id=signal_id,
        signal_type=(
            SecuritySignalType.MALWARE_DETECTION
            if family is SecuritySourceFamily.ENDPOINT
            else SecuritySignalType.NETWORK_INDICATOR
        ),
        evidence_strength=(
            SecurityEvidenceStrength.VERIFIED_DETECTION
            if family is SecuritySourceFamily.ENDPOINT
            else SecurityEvidenceStrength.CORRELATED
        ),
        source_family=family,
        evidence_refs=(f"evidence:{family.value}:{signal_id}",),
        asset_refs=("asset:edge-1",),
        observed_at=T1,
        recorded_at=T1,
    )


def _incident(*, incident_id: str = "incident-a"):
    identity = _company()
    return assess_company_incident(
        identity=identity,
        incident_id=incident_id,
        signals=(
            _signal(identity, signal_id="endpoint-1", family=SecuritySourceFamily.ENDPOINT),
            _signal(identity, signal_id="network-1", family=SecuritySourceFamily.NETWORK),
        ),
        as_of=T2,
    )


def _policy():
    return build_cyber_incident_audience_policy(
        identity=_company(),
        policy_id="cyber-audience:company-a:v1",
        owner_principal_ref="principal:owner-a",
        designated_principal_refs=("principal:security-lead",),
    )


def _recipient(principal: str, *, company: str = "company-a"):
    return CyberIncidentRecipient(
        identity=_company(company=company),
        principal_ref=principal,
    )


def _notify_alert(incident, *, fingerprint: str | None = None):
    return evaluate_alert_policy(
        AlertCandidate(
            fingerprint=fingerprint or incident.fingerprint,
            observed_at=T2,
            priority_score=0.95,
            evidence_refs=("evidence:incident-alert",),
        ),
        None,
    )


def _suppressed_alert(incident):
    candidate = AlertCandidate(
        fingerprint=incident.fingerprint,
        observed_at=T2,
        priority_score=0.80,
        evidence_refs=("evidence:incident-alert",),
    )
    prior = PriorAlertState(
        fingerprint=incident.fingerprint,
        last_notified_at=T2 - timedelta(minutes=5),
        last_priority_score=0.80,
        evidence_refs=("evidence:incident-alert",),
    )
    result = evaluate_alert_policy(candidate, prior)
    assert result.should_notify is False
    return result


def test_owner_notify_routes_full_confirmed_incident() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.FULL_INCIDENT
    assert route.should_deliver is True
    assert route.incident_language is CyberIncidentLanguage.CONFIRMED_CYBER_INCIDENT
    assert route.disclose_incident_nature is True
    assert route.disclose_sensitive_evidence_refs is True
    assert route.notification_send_authority_granted is False
    assert route.execution_authority_granted is False


def test_explicit_delegate_notify_routes_full_incident() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:security-lead"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.FULL_INCIDENT


def test_ordinary_user_notify_is_reduced_to_operational_impact_only() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:warehouse-manager-42"),
        operational_impact_required=True,
        operational_impact_message_ref="operational-impact:service-degradation",
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.OPERATIONAL_IMPACT_ONLY
    assert route.should_deliver is True
    assert route.incident_language is None
    assert route.disclose_incident_nature is False
    assert route.disclose_sensitive_evidence_refs is False


def test_ordinary_user_notify_is_suppressed_when_no_operational_impact_is_required() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:warehouse-manager-42"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.SUPPRESSED
    assert route.should_deliver is False
    assert route.incident_language is None
    assert route.message_ref is None


def test_cross_company_recipient_is_suppressed_even_when_generic_alert_says_notify() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:company-b-security", company="company-b"),
        operational_impact_required=True,
        operational_impact_message_ref="operational-impact:service-degradation",
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.SUPPRESSED
    assert route.should_deliver is False


def test_generic_alert_suppression_wins_even_for_owner_full_disclosure() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_suppressed_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    assert route.delivery_level is CyberAlertDeliveryLevel.SUPPRESSED
    assert route.should_deliver is False


def test_alert_must_be_bound_to_exact_incident_fingerprint() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    with pytest.raises(ValueError, match="cyber_alert_policy_not_bound_to_exact_incident"):
        route_cyber_alert(
            incident=incident,
            alert=_notify_alert(incident, fingerprint="different-alert-fingerprint"),
            disclosure=disclosure,
            full_incident_message_ref="cyber-incident-summary:incident-a:v1",
        )


def test_disclosure_for_another_incident_cannot_be_reused() -> None:
    incident = _incident(incident_id="incident-a")
    other = _incident(incident_id="incident-b")
    other_disclosure = evaluate_cyber_incident_disclosure(
        incident=other,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    with pytest.raises(ValueError, match="cyber_alert_disclosure_incident_id_mismatch"):
        route_cyber_alert(
            incident=incident,
            alert=_notify_alert(incident),
            disclosure=other_disclosure,
            full_incident_message_ref="cyber-incident-summary:incident-a:v1",
        )


def test_full_delivery_requires_governed_summary_reference() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    with pytest.raises(ValidationError, match="cyber_alert_full_message_requires_governed_summary_ref"):
        route_cyber_alert(
            incident=incident,
            alert=_notify_alert(incident),
            disclosure=disclosure,
            full_incident_message_ref="raw-evidence:incident-a",
        )


def test_routing_decision_tamper_fails_closed() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    tampered = route.model_copy(update={"recipient_principal_ref": "principal:other"})
    with pytest.raises(ValidationError, match="cyber_alert_routing_fingerprint_mismatch"):
        CyberAlertRoutingDecision.model_validate(tampered.model_dump(mode="json"))


def test_routing_never_grants_notification_send_authority() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    tampered = route.model_copy(update={"notification_send_authority_granted": True})
    with pytest.raises(ValidationError, match="cyber_alert_routing_never_grants_notification_send_authority"):
        CyberAlertRoutingDecision.model_validate(tampered.model_dump(mode="json"))


def test_routing_never_grants_execution_authority() -> None:
    incident = _incident()
    disclosure = evaluate_cyber_incident_disclosure(
        incident=incident,
        policy=_policy(),
        recipient=_recipient("principal:owner-a"),
        operational_impact_required=False,
    )
    route = route_cyber_alert(
        incident=incident,
        alert=_notify_alert(incident),
        disclosure=disclosure,
        full_incident_message_ref="cyber-incident-summary:incident-a:v1",
    )
    tampered = route.model_copy(update={"execution_authority_granted": True})
    with pytest.raises(ValidationError, match="cyber_alert_routing_never_grants_execution_authority"):
        CyberAlertRoutingDecision.model_validate(tampered.model_dump(mode="json"))
