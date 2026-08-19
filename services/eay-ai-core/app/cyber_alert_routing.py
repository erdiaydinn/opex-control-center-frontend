"""Recipient-specific cyber alert routing for EAY Jarvis.

The generic alert engine decides whether an event merits notification. It does not
decide who may learn that a cyber incident exists. This bridge intersects the
canonical alert-fatigue decision with the canonical company incident disclosure
decision so notification cadence can never widen cyber visibility.

V1 is intentionally non-authoritative:
- it does not send a notification;
- it does not grant incident-response or business execution authority;
- a generic NOTIFY decision never overrides need-to-know disclosure;
- non-privileged recipients never receive incident nature or sensitive evidence;
- an alert must be fingerprint-bound to the exact incident it represents.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.alert_intelligence import AlertPolicyResult
from app.company_cyber_incident_intelligence import CompanyIncidentAssessment
from app.cyber_incident_disclosure import (
    CyberIncidentDisclosureDecision,
    CyberIncidentDisclosureLevel,
    CyberIncidentLanguage,
)

CYBER_ALERT_ROUTING_CONTRACT = "eay-cyber-alert-routing-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CyberAlertDeliveryLevel(str, Enum):
    FULL_INCIDENT = "full_incident"
    OPERATIONAL_IMPACT_ONLY = "operational_impact_only"
    SUPPRESSED = "suppressed"


class CyberAlertRoutingDecision(BaseModel):
    contract: str = CYBER_ALERT_ROUTING_CONTRACT
    incident_id: str = Field(min_length=1)
    incident_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    alert_fingerprint: str = Field(min_length=1)
    recipient_principal_ref: str = Field(min_length=1)
    delivery_level: CyberAlertDeliveryLevel
    should_deliver: bool
    incident_language: CyberIncidentLanguage | None = None
    message_ref: str | None = None
    disclose_incident_nature: bool = False
    disclose_sensitive_evidence_refs: bool = False
    notification_send_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def routing_is_private_and_non_authoritative(self) -> CyberAlertRoutingDecision:
        if self.notification_send_authority_granted:
            raise ValueError("cyber_alert_routing_never_grants_notification_send_authority")
        if self.execution_authority_granted:
            raise ValueError("cyber_alert_routing_never_grants_execution_authority")
        if self.delivery_level is CyberAlertDeliveryLevel.SUPPRESSED:
            if self.should_deliver:
                raise ValueError("cyber_alert_suppressed_delivery_cannot_notify")
            if any(
                (
                    self.incident_language is not None,
                    self.message_ref is not None,
                    self.disclose_incident_nature,
                    self.disclose_sensitive_evidence_refs,
                )
            ):
                raise ValueError("cyber_alert_suppressed_delivery_cannot_expose_details")
        elif self.delivery_level is CyberAlertDeliveryLevel.OPERATIONAL_IMPACT_ONLY:
            if not self.should_deliver or self.message_ref is None:
                raise ValueError("cyber_alert_operational_delivery_requires_message")
            if not self.message_ref.startswith("operational-impact:"):
                raise ValueError("cyber_alert_operational_message_must_be_impact_only")
            if self.incident_language is not None:
                raise ValueError("cyber_alert_operational_delivery_cannot_expose_incident_language")
            if self.disclose_incident_nature or self.disclose_sensitive_evidence_refs:
                raise ValueError("cyber_alert_operational_delivery_cannot_expose_incident_details")
        else:
            if not self.should_deliver or self.message_ref is None:
                raise ValueError("cyber_alert_full_delivery_requires_message")
            if not self.message_ref.startswith("cyber-incident-summary:"):
                raise ValueError("cyber_alert_full_message_requires_governed_summary_ref")
            if self.incident_language is None:
                raise ValueError("cyber_alert_full_delivery_requires_incident_language")
            if not self.disclose_incident_nature or not self.disclose_sensitive_evidence_refs:
                raise ValueError("cyber_alert_full_delivery_requires_full_visibility")
        for ref in (
            self.incident_id,
            self.alert_fingerprint,
            self.recipient_principal_ref,
            self.message_ref,
        ):
            if ref is not None:
                _safe_ref(ref, "cyber_alert_unsafe_reference_forbidden")
        _verify(self, "cyber_alert_routing_fingerprint_mismatch")
        return self


def route_cyber_alert(
    *,
    incident: CompanyIncidentAssessment,
    alert: AlertPolicyResult,
    disclosure: CyberIncidentDisclosureDecision,
    full_incident_message_ref: str | None = None,
) -> CyberAlertRoutingDecision:
    """Intersect alert cadence and disclosure; never let cadence widen audience."""

    incident = CompanyIncidentAssessment.model_validate(incident.model_dump(mode="json"))
    disclosure = CyberIncidentDisclosureDecision.model_validate(
        disclosure.model_dump(mode="json")
    )
    alert = AlertPolicyResult.model_validate(alert.model_dump(mode="json"))

    if disclosure.incident_id != incident.incident_id:
        raise ValueError("cyber_alert_disclosure_incident_id_mismatch")
    if disclosure.incident_fingerprint != incident.fingerprint:
        raise ValueError("cyber_alert_disclosure_incident_fingerprint_mismatch")
    if alert.fingerprint != incident.fingerprint:
        raise ValueError("cyber_alert_policy_not_bound_to_exact_incident")

    if not alert.should_notify or disclosure.level is CyberIncidentDisclosureLevel.NONE:
        return _suppressed(
            incident=incident,
            alert=alert,
            recipient_principal_ref=disclosure.recipient_principal_ref,
        )

    if disclosure.level is CyberIncidentDisclosureLevel.OPERATIONAL_IMPACT_ONLY:
        if disclosure.operational_impact_message_ref is None:
            raise ValueError("cyber_alert_operational_disclosure_missing_message")
        return _build_decision(
            incident=incident,
            alert=alert,
            recipient_principal_ref=disclosure.recipient_principal_ref,
            delivery_level=CyberAlertDeliveryLevel.OPERATIONAL_IMPACT_ONLY,
            should_deliver=True,
            incident_language=None,
            message_ref=disclosure.operational_impact_message_ref,
            disclose_incident_nature=False,
            disclose_sensitive_evidence_refs=False,
        )

    if full_incident_message_ref is None:
        raise ValueError("cyber_alert_full_disclosure_requires_governed_summary_ref")
    if disclosure.incident_language is None:
        raise ValueError("cyber_alert_full_disclosure_missing_incident_language")
    return _build_decision(
        incident=incident,
        alert=alert,
        recipient_principal_ref=disclosure.recipient_principal_ref,
        delivery_level=CyberAlertDeliveryLevel.FULL_INCIDENT,
        should_deliver=True,
        incident_language=disclosure.incident_language,
        message_ref=full_incident_message_ref,
        disclose_incident_nature=True,
        disclose_sensitive_evidence_refs=True,
    )


def _suppressed(
    *,
    incident: CompanyIncidentAssessment,
    alert: AlertPolicyResult,
    recipient_principal_ref: str,
) -> CyberAlertRoutingDecision:
    return _build_decision(
        incident=incident,
        alert=alert,
        recipient_principal_ref=recipient_principal_ref,
        delivery_level=CyberAlertDeliveryLevel.SUPPRESSED,
        should_deliver=False,
        incident_language=None,
        message_ref=None,
        disclose_incident_nature=False,
        disclose_sensitive_evidence_refs=False,
    )


def _build_decision(
    *,
    incident: CompanyIncidentAssessment,
    alert: AlertPolicyResult,
    recipient_principal_ref: str,
    delivery_level: CyberAlertDeliveryLevel,
    should_deliver: bool,
    incident_language: CyberIncidentLanguage | None,
    message_ref: str | None,
    disclose_incident_nature: bool,
    disclose_sensitive_evidence_refs: bool,
) -> CyberAlertRoutingDecision:
    draft = {
        "contract": CYBER_ALERT_ROUTING_CONTRACT,
        "incident_id": incident.incident_id,
        "incident_fingerprint": incident.fingerprint,
        "alert_fingerprint": alert.fingerprint,
        "recipient_principal_ref": recipient_principal_ref,
        "delivery_level": delivery_level.value,
        "should_deliver": should_deliver,
        "incident_language": (
            incident_language.value if incident_language is not None else None
        ),
        "message_ref": message_ref,
        "disclose_incident_nature": disclose_incident_nature,
        "disclose_sensitive_evidence_refs": disclose_sensitive_evidence_refs,
        "notification_send_authority_granted": False,
        "execution_authority_granted": False,
    }
    return CyberAlertRoutingDecision.model_validate(_sealed(draft))


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _verify(model: BaseModel, error: str) -> None:
    if model.fingerprint != _fingerprint(_payload(model)):
        raise ValueError(error)


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
