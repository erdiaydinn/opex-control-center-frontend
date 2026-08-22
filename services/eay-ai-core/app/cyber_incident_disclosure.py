"""Need-to-know disclosure for company cyber incidents.

Cyber incidents are not company-wide broadcast material. Full incident details are
visible only to the exact company security owner and explicitly designated
principals. Everyone else receives either a pre-approved operational-impact-only
message or nothing.

The contract is intentionally non-authoritative:
- it does not send notifications;
- it does not grant incident-response or business execution authority;
- it does not let broad roles imply full incident disclosure;
- it does not reveal incident existence across company boundaries;
- it preserves uncertainty language from the canonical incident assessment.
"""

from __future__ import annotations

import hashlib
import json
import re
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_cyber_incident_intelligence import (
    CompanyIncidentAssessment,
    IncidentStatus,
)

CYBER_INCIDENT_DISCLOSURE_CONTRACT = "eay-cyber-incident-disclosure-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)


class CyberIncidentDisclosureLevel(str, Enum):
    FULL_INCIDENT = "full_incident"
    OPERATIONAL_IMPACT_ONLY = "operational_impact_only"
    NONE = "none"


class CyberIncidentLanguage(str, Enum):
    POSSIBLE_SECURITY_EVENT = "possible_security_event"
    SUSPICIOUS_CYBER_INCIDENT = "suspicious_cyber_incident"
    CONFIRMED_CYBER_INCIDENT = "confirmed_cyber_incident"


class CyberIncidentAudiencePolicy(BaseModel):
    contract: str = CYBER_INCIDENT_DISCLOSURE_CONTRACT
    policy_id: str = Field(min_length=1)
    identity: CompanyIdentity
    owner_principal_ref: str = Field(min_length=1)
    designated_principal_refs: tuple[str, ...] = ()
    role_based_full_disclosure_allowed: bool = False
    company_wide_full_disclosure_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def policy_is_explicit_and_non_authoritative(self) -> CyberIncidentAudiencePolicy:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if self.role_based_full_disclosure_allowed:
            raise ValueError("cyber_incident_role_based_full_disclosure_forbidden")
        if self.company_wide_full_disclosure_allowed:
            raise ValueError("cyber_incident_company_wide_full_disclosure_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_incident_disclosure_never_grants_execution_authority")
        if self.owner_principal_ref in self.designated_principal_refs:
            raise ValueError("cyber_incident_owner_must_not_be_duplicated")
        if len(self.designated_principal_refs) != len(set(self.designated_principal_refs)):
            raise ValueError("cyber_incident_designated_principals_must_be_unique")
        for ref in (
            self.policy_id,
            self.owner_principal_ref,
            *self.designated_principal_refs,
        ):
            _safe_ref(ref, "cyber_incident_unsafe_principal_reference_forbidden")
        _verify(self, "cyber_incident_audience_policy_fingerprint_mismatch")
        return self


class CyberIncidentRecipient(BaseModel):
    identity: CompanyIdentity
    principal_ref: str = Field(min_length=1)

    @model_validator(mode="after")
    def recipient_is_safe(self) -> CyberIncidentRecipient:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _safe_ref(self.principal_ref, "cyber_incident_unsafe_recipient_reference_forbidden")
        return self


class CyberIncidentDisclosureDecision(BaseModel):
    contract: str = CYBER_INCIDENT_DISCLOSURE_CONTRACT
    incident_id: str
    incident_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    recipient_principal_ref: str
    level: CyberIncidentDisclosureLevel
    incident_language: CyberIncidentLanguage | None = None
    disclose_incident_nature: bool = False
    disclose_sensitive_evidence_refs: bool = False
    operational_impact_message_ref: str | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_cannot_expand_authority(self) -> CyberIncidentDisclosureDecision:
        if self.execution_authority_granted:
            raise ValueError("cyber_incident_disclosure_decision_never_grants_execution_authority")
        if self.level is CyberIncidentDisclosureLevel.FULL_INCIDENT:
            if not self.disclose_incident_nature or not self.disclose_sensitive_evidence_refs:
                raise ValueError("cyber_incident_full_disclosure_requires_full_visibility")
            if self.incident_language is None:
                raise ValueError("cyber_incident_full_disclosure_requires_language")
        else:
            if self.disclose_incident_nature or self.disclose_sensitive_evidence_refs:
                raise ValueError("cyber_incident_limited_disclosure_cannot_expose_incident_details")
            if self.incident_language is not None:
                raise ValueError("cyber_incident_limited_disclosure_cannot_expose_incident_language")
        if self.level is CyberIncidentDisclosureLevel.OPERATIONAL_IMPACT_ONLY:
            if self.operational_impact_message_ref is None:
                raise ValueError("cyber_incident_operational_impact_message_required")
        elif (
            self.level is CyberIncidentDisclosureLevel.NONE
            and self.operational_impact_message_ref is not None
        ):
            raise ValueError("cyber_incident_none_disclosure_cannot_include_message")
        return self


def build_cyber_incident_audience_policy(
    *,
    identity: CompanyIdentity,
    policy_id: str,
    owner_principal_ref: str,
    designated_principal_refs: tuple[str, ...] = (),
) -> CyberIncidentAudiencePolicy:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": CYBER_INCIDENT_DISCLOSURE_CONTRACT,
        "policy_id": policy_id,
        "identity": identity.model_dump(mode="json"),
        "owner_principal_ref": owner_principal_ref,
        "designated_principal_refs": list(designated_principal_refs),
        "role_based_full_disclosure_allowed": False,
        "company_wide_full_disclosure_allowed": False,
        "execution_authority_granted": False,
    }
    return CyberIncidentAudiencePolicy.model_validate(_sealed(draft))


def evaluate_cyber_incident_disclosure(
    *,
    incident: CompanyIncidentAssessment,
    policy: CyberIncidentAudiencePolicy,
    recipient: CyberIncidentRecipient,
    operational_impact_required: bool,
    operational_impact_message_ref: str | None = None,
) -> CyberIncidentDisclosureDecision:
    incident = CompanyIncidentAssessment.model_validate(incident.model_dump(mode="json"))
    policy = CyberIncidentAudiencePolicy.model_validate(policy.model_dump(mode="json"))
    recipient = CyberIncidentRecipient.model_validate(recipient.model_dump(mode="json"))

    if incident.identity.fingerprint != policy.identity.fingerprint:
        raise ValueError("cyber_incident_disclosure_policy_company_mismatch")

    if recipient.identity.fingerprint != policy.identity.fingerprint:
        return _none(incident=incident, recipient=recipient)

    privileged = {policy.owner_principal_ref, *policy.designated_principal_refs}
    if recipient.principal_ref in privileged:
        return CyberIncidentDisclosureDecision(
            incident_id=incident.incident_id,
            incident_fingerprint=incident.fingerprint,
            recipient_principal_ref=recipient.principal_ref,
            level=CyberIncidentDisclosureLevel.FULL_INCIDENT,
            incident_language=_incident_language(incident.status),
            disclose_incident_nature=True,
            disclose_sensitive_evidence_refs=True,
            operational_impact_message_ref=(
                _validated_impact_ref(operational_impact_message_ref)
                if operational_impact_message_ref is not None
                else None
            ),
            execution_authority_granted=False,
        )

    if not operational_impact_required:
        return _none(incident=incident, recipient=recipient)

    if operational_impact_message_ref is None:
        raise ValueError("cyber_incident_operational_impact_message_required")
    impact_ref = _validated_impact_ref(operational_impact_message_ref)
    return CyberIncidentDisclosureDecision(
        incident_id=incident.incident_id,
        incident_fingerprint=incident.fingerprint,
        recipient_principal_ref=recipient.principal_ref,
        level=CyberIncidentDisclosureLevel.OPERATIONAL_IMPACT_ONLY,
        incident_language=None,
        disclose_incident_nature=False,
        disclose_sensitive_evidence_refs=False,
        operational_impact_message_ref=impact_ref,
        execution_authority_granted=False,
    )


def _none(
    *,
    incident: CompanyIncidentAssessment,
    recipient: CyberIncidentRecipient,
) -> CyberIncidentDisclosureDecision:
    return CyberIncidentDisclosureDecision(
        incident_id=incident.incident_id,
        incident_fingerprint=incident.fingerprint,
        recipient_principal_ref=recipient.principal_ref,
        level=CyberIncidentDisclosureLevel.NONE,
        incident_language=None,
        disclose_incident_nature=False,
        disclose_sensitive_evidence_refs=False,
        operational_impact_message_ref=None,
        execution_authority_granted=False,
    )


def _incident_language(status: IncidentStatus) -> CyberIncidentLanguage:
    if status is IncidentStatus.CONFIRMED:
        return CyberIncidentLanguage.CONFIRMED_CYBER_INCIDENT
    if status is IncidentStatus.SUSPICIOUS:
        return CyberIncidentLanguage.SUSPICIOUS_CYBER_INCIDENT
    return CyberIncidentLanguage.POSSIBLE_SECURITY_EVENT


def _validated_impact_ref(value: str) -> str:
    _safe_ref(value, "cyber_incident_unsafe_operational_message_reference_forbidden")
    if not value.startswith("operational-impact:"):
        raise ValueError("cyber_incident_operational_message_must_be_impact_only")
    return value


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
