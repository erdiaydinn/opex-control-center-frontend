"""Company-bound defensive priority receipts for EAY Jarvis cyber defense.

Global threat knowledge is shared and tenant-neutral. Company exposure and
incident truth are not. This layer joins those planes without allowing a public
CVE/KEV record to become a firm company-impact claim by itself.

V1 is intentionally defensive:
- no exploit, payload, PoC or credential material is represented;
- unknown/stale company exposure stays unresolved even for a critical KEV;
- potential exposure can prioritize verification but is not a firm impact claim;
- confirmed company exposure can authorize an affected/not-affected claim;
- a confirmed incident elevates a threat only when its exact company signals bind
  to the same threat/exposure;
- prioritization never grants execution authority or proves causality/attribution.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.company_cyber_incident_intelligence import (
    CompanyIncidentAssessment,
    CompanySecuritySignal,
    IncidentStatus,
)
from app.cyber_defense_intelligence import (
    CompanyCyberExposure,
    DefensiveAction,
    DefensivePriority,
    ExposureStatus,
    ThreatKnowledgeRecord,
    prioritize_company_exposure,
    verify_exposure_binding,
)

CYBER_DEFENSE_PRIORITY_CONTRACT = "eay-cyber-defense-priority-intelligence-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit|payload|proof[_-]?of[_-]?concept|poc[_-]|reverse[_-]?shell|"
    r"credential[_-]?dump|shellcode|ransomware)"
)


class CompanyThreatDisposition(str, Enum):
    HOLD_FOR_COMPANY_EVIDENCE = "hold_for_company_evidence"
    MONITOR = "monitor"
    PRIORITIZE_VERIFICATION = "prioritize_verification"
    PRIORITIZE_MITIGATION = "prioritize_mitigation"
    URGENT_INCIDENT_RESPONSE = "urgent_incident_response"


class CompanyExposureClaim(str, Enum):
    UNRESOLVED = "unresolved"
    POSSIBLY_AFFECTED = "possibly_affected"
    AFFECTED = "affected"
    NOT_AFFECTED = "not_affected"


class DefensivePriorityReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_DEFENSE_PRIORITY_CONTRACT
    receipt_id: str = Field(min_length=1)
    identity: CompanyIdentity
    as_of: datetime
    max_company_evidence_age_seconds: int = Field(gt=0)
    threat_record_id: str = Field(min_length=1)
    threat_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    global_threat_priority: DefensivePriority
    exposure_id: str = Field(min_length=1)
    exposure_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    exposure_status: ExposureStatus
    exposure_claim: CompanyExposureClaim
    company_evidence_current: bool
    company_defensive_priority: DefensivePriority | None = None
    disposition: CompanyThreatDisposition
    incident_id: str | None = None
    incident_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    incident_status: IncidentStatus | None = None
    linked_incident_signal_fingerprints: tuple[str, ...] = ()
    firm_company_exposure_claim_authorized: bool = False
    firm_company_incident_claim_authorized: bool = False
    causal_claim_authorized: bool = False
    actor_attribution_authorized: bool = False
    recommended_defensive_actions: tuple[DefensiveAction, ...]
    reason_codes: tuple[str, ...]
    advisory_only: bool = True
    exploit_generation_permitted: bool = False
    automatic_execution_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_integral_and_defensive(self) -> DefensivePriorityReceipt:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "cyber_priority_as_of_requires_timezone")
        if not self.advisory_only:
            raise ValueError("cyber_priority_receipt_must_remain_advisory")
        if self.exploit_generation_permitted:
            raise ValueError("cyber_priority_exploit_generation_forbidden")
        if self.automatic_execution_permitted:
            raise ValueError("cyber_priority_automatic_execution_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_priority_never_grants_execution_authority")
        if self.causal_claim_authorized:
            raise ValueError("cyber_priority_never_proves_incident_causality")
        if self.actor_attribution_authorized:
            raise ValueError("cyber_priority_never_proves_actor_attribution")

        if self.firm_company_exposure_claim_authorized:
            if not self.company_evidence_current:
                raise ValueError("cyber_priority_firm_exposure_requires_current_company_evidence")
            if self.exposure_claim not in {
                CompanyExposureClaim.AFFECTED,
                CompanyExposureClaim.NOT_AFFECTED,
            }:
                raise ValueError("cyber_priority_firm_exposure_claim_requires_resolved_state")
        elif self.exposure_claim in {
            CompanyExposureClaim.AFFECTED,
            CompanyExposureClaim.NOT_AFFECTED,
        }:
            raise ValueError("cyber_priority_resolved_exposure_requires_firm_authorization")

        if self.firm_company_incident_claim_authorized:
            if self.incident_status is not IncidentStatus.CONFIRMED:
                raise ValueError("cyber_priority_firm_incident_requires_confirmed_incident")
            if not self.incident_id or not self.incident_fingerprint:
                raise ValueError("cyber_priority_firm_incident_requires_bound_incident")
            if not self.linked_incident_signal_fingerprints:
                raise ValueError("cyber_priority_firm_incident_requires_linked_signal")
        if self.disposition is CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE:
            if not self.firm_company_exposure_claim_authorized:
                raise ValueError("cyber_priority_urgent_requires_confirmed_company_exposure")
            if self.exposure_claim is not CompanyExposureClaim.AFFECTED:
                raise ValueError("cyber_priority_urgent_requires_affected_company_claim")
            if not self.firm_company_incident_claim_authorized:
                raise ValueError("cyber_priority_urgent_requires_confirmed_linked_incident")

        _unique(
            tuple(action.value for action in self.recommended_defensive_actions),
            "cyber_priority_actions_must_be_unique",
        )
        _unique(self.reason_codes, "cyber_priority_reasons_must_be_unique")
        _unique(
            self.linked_incident_signal_fingerprints,
            "cyber_priority_linked_signal_fingerprints_must_be_unique",
        )
        for ref in (
            self.receipt_id,
            self.threat_record_id,
            self.exposure_id,
            self.incident_id,
            *self.reason_codes,
        ):
            if ref is not None:
                _safe_ref(ref, "cyber_priority_unsafe_reference_forbidden")
        _verify_fingerprint(self, "cyber_priority_receipt_fingerprint_mismatch")
        return self


def build_defensive_priority_receipt(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure: CompanyCyberExposure,
    as_of: datetime,
    max_company_evidence_age_seconds: int,
    incident: CompanyIncidentAssessment | None = None,
    incident_signals: tuple[CompanySecuritySignal, ...] = (),
) -> DefensivePriorityReceipt:
    """Join shared threat knowledge to exact company truth without over-claiming."""

    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    threat = ThreatKnowledgeRecord.model_validate(threat.model_dump(mode="json"))
    exposure = CompanyCyberExposure.model_validate(exposure.model_dump(mode="json"))
    _aware(as_of, "cyber_priority_as_of_requires_timezone")
    if max_company_evidence_age_seconds <= 0:
        raise ValueError("cyber_priority_max_company_evidence_age_must_be_positive")

    verify_exposure_binding(identity=identity, threat=threat, exposure=exposure)
    if exposure.assessed_at > as_of or exposure.recorded_at > as_of:
        raise ValueError("cyber_priority_company_exposure_future_known_forbidden")

    evidence_age_seconds = (as_of - exposure.assessed_at).total_seconds()
    evidence_present = bool(exposure.company_evidence_refs)
    company_evidence_current = (
        evidence_present
        and evidence_age_seconds <= max_company_evidence_age_seconds
    )

    global_priority = _global_threat_priority(threat)
    reasons: list[str] = [f"global_threat_priority:{global_priority.value}"]
    company_priority: DefensivePriority | None = None
    firm_exposure = False

    if exposure.status is ExposureStatus.UNKNOWN:
        claim = CompanyExposureClaim.UNRESOLVED
        disposition = CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE
        reasons.append("company_exposure_unknown")
    elif not company_evidence_current:
        claim = CompanyExposureClaim.UNRESOLVED
        disposition = CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE
        reasons.append("company_exposure_evidence_missing_or_stale")
    elif exposure.status is ExposureStatus.NOT_EXPOSED:
        claim = CompanyExposureClaim.NOT_AFFECTED
        disposition = CompanyThreatDisposition.MONITOR
        company_priority = DefensivePriority.LOW
        firm_exposure = True
        reasons.append("current_company_evidence_not_exposed")
    elif exposure.status is ExposureStatus.POTENTIALLY_EXPOSED:
        claim = CompanyExposureClaim.POSSIBLY_AFFECTED
        disposition = CompanyThreatDisposition.PRIORITIZE_VERIFICATION
        reasons.append("company_exposure_possible_not_confirmed")
    elif exposure.status is ExposureStatus.CONFIRMED_EXPOSED:
        claim = CompanyExposureClaim.AFFECTED
        disposition = CompanyThreatDisposition.PRIORITIZE_MITIGATION
        company_priority = prioritize_company_exposure(
            identity=identity,
            threat=threat,
            exposure=exposure,
        ).priority
        firm_exposure = True
        reasons.append("current_company_evidence_confirmed_exposure")
    else:  # pragma: no cover - enum exhaustiveness guard
        raise ValueError("cyber_priority_unknown_exposure_status")

    incident_id: str | None = None
    incident_fingerprint: str | None = None
    incident_status: IncidentStatus | None = None
    linked_signal_fingerprints: tuple[str, ...] = ()
    firm_incident = False

    if incident is None:
        if incident_signals:
            raise ValueError("cyber_priority_incident_signals_require_incident")
    else:
        (
            incident,
            linked_signal_fingerprints,
        ) = _verify_incident_binding(
            identity=identity,
            threat=threat,
            exposure=exposure,
            incident=incident,
            signals=incident_signals,
            as_of=as_of,
        )
        incident_id = incident.incident_id
        incident_fingerprint = incident.fingerprint
        incident_status = incident.status
        firm_incident = incident.status is IncidentStatus.CONFIRMED
        reasons.append(f"company_incident:{incident.status.value}")
        if firm_incident:
            reasons.append("confirmed_company_incident_linked_to_threat_or_exposure")
        else:
            reasons.append("incident_link_is_not_confirmed_company_incident")

    if firm_incident and firm_exposure and claim is CompanyExposureClaim.AFFECTED:
        disposition = CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE
        company_priority = DefensivePriority.CRITICAL
        reasons.append("confirmed_exposure_and_linked_confirmed_incident")
    elif firm_incident and not firm_exposure:
        reasons.append("confirmed_incident_does_not_substitute_for_exposure_proof")
        if disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE:
            disposition = CompanyThreatDisposition.PRIORITIZE_VERIFICATION

    actions = _recommended_actions(
        disposition=disposition,
        exposure=exposure,
    )
    receipt_seed = {
        "identity_fingerprint": identity.fingerprint,
        "threat_fingerprint": threat.fingerprint,
        "exposure_fingerprint": exposure.fingerprint,
        "incident_fingerprint": incident_fingerprint,
        "as_of": _iso(as_of),
        "max_company_evidence_age_seconds": max_company_evidence_age_seconds,
    }
    receipt_id = f"cyber-priority:{_fingerprint(receipt_seed)[:24]}"
    draft = {
        "contract": CYBER_DEFENSE_PRIORITY_CONTRACT,
        "receipt_id": receipt_id,
        "identity": identity.model_dump(mode="json"),
        "as_of": _iso(as_of),
        "max_company_evidence_age_seconds": max_company_evidence_age_seconds,
        "threat_record_id": threat.record_id,
        "threat_fingerprint": threat.fingerprint,
        "global_threat_priority": global_priority.value,
        "exposure_id": exposure.exposure_id,
        "exposure_fingerprint": exposure.fingerprint,
        "exposure_status": exposure.status.value,
        "exposure_claim": claim.value,
        "company_evidence_current": company_evidence_current,
        "company_defensive_priority": (
            company_priority.value if company_priority is not None else None
        ),
        "disposition": disposition.value,
        "incident_id": incident_id,
        "incident_fingerprint": incident_fingerprint,
        "incident_status": incident_status.value if incident_status is not None else None,
        "linked_incident_signal_fingerprints": list(linked_signal_fingerprints),
        "firm_company_exposure_claim_authorized": firm_exposure,
        "firm_company_incident_claim_authorized": firm_incident,
        "causal_claim_authorized": False,
        "actor_attribution_authorized": False,
        "recommended_defensive_actions": [action.value for action in actions],
        "reason_codes": reasons,
        "advisory_only": True,
        "exploit_generation_permitted": False,
        "automatic_execution_permitted": False,
        "execution_authority_granted": False,
    }
    return DefensivePriorityReceipt.model_validate(_sealed(draft))


def verify_defensive_priority_receipt(*, receipt: DefensivePriorityReceipt) -> None:
    """Re-validate at a decision boundary so model_copy tampering fails closed."""

    DefensivePriorityReceipt.model_validate(receipt.model_dump(mode="json"))


def _verify_incident_binding(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure: CompanyCyberExposure,
    incident: CompanyIncidentAssessment,
    signals: tuple[CompanySecuritySignal, ...],
    as_of: datetime,
) -> tuple[CompanyIncidentAssessment, tuple[str, ...]]:
    incident = CompanyIncidentAssessment.model_validate(incident.model_dump(mode="json"))
    if incident.identity.fingerprint != identity.fingerprint:
        raise ValueError("cyber_priority_cross_company_incident_forbidden")
    if incident.as_of > as_of:
        raise ValueError("cyber_priority_future_incident_forbidden")
    if not signals:
        raise ValueError("cyber_priority_incident_requires_exact_company_signals")

    validated: list[CompanySecuritySignal] = []
    for raw in signals:
        signal = CompanySecuritySignal.model_validate(raw.model_dump(mode="json"))
        if signal.identity.fingerprint != identity.fingerprint:
            raise ValueError("cyber_priority_cross_company_incident_signal_forbidden")
        if signal.observed_at > as_of or signal.recorded_at > as_of:
            raise ValueError("cyber_priority_future_incident_signal_forbidden")
        validated.append(signal)

    if tuple(signal.signal_id for signal in validated) != incident.signal_ids:
        raise ValueError("cyber_priority_incident_signal_id_binding_mismatch")
    if tuple(signal.fingerprint for signal in validated) != incident.signal_fingerprints:
        raise ValueError("cyber_priority_incident_signal_fingerprint_binding_mismatch")

    linked = tuple(
        signal.fingerprint
        for signal in validated
        if threat.record_id in signal.threat_record_refs
        or exposure.exposure_id in signal.exposure_refs
    )
    if not linked:
        raise ValueError("cyber_priority_incident_not_bound_to_threat_or_exposure")
    return incident, linked


def _global_threat_priority(threat: ThreatKnowledgeRecord) -> DefensivePriority:
    if threat.known_exploited_in_wild:
        return DefensivePriority.CRITICAL
    score = threat.severity_score
    if score is None:
        return DefensivePriority.MEDIUM
    if score >= 9.0:
        return DefensivePriority.CRITICAL
    if score >= 7.0:
        return DefensivePriority.HIGH
    if score >= 4.0:
        return DefensivePriority.MEDIUM
    return DefensivePriority.LOW


def _recommended_actions(
    *,
    disposition: CompanyThreatDisposition,
    exposure: CompanyCyberExposure,
) -> tuple[DefensiveAction, ...]:
    if disposition is CompanyThreatDisposition.MONITOR:
        return (DefensiveAction.INCREASE_TELEMETRY,)
    if disposition is CompanyThreatDisposition.HOLD_FOR_COMPANY_EVIDENCE:
        return (
            DefensiveAction.INCREASE_TELEMETRY,
            DefensiveAction.DEPLOY_DETECTION_RULE,
        )
    if disposition is CompanyThreatDisposition.PRIORITIZE_VERIFICATION:
        return (
            DefensiveAction.INCREASE_TELEMETRY,
            DefensiveAction.DEPLOY_DETECTION_RULE,
        )
    if disposition is CompanyThreatDisposition.URGENT_INCIDENT_RESPONSE:
        actions = [
            DefensiveAction.ISOLATE_ASSET_CANDIDATE,
            DefensiveAction.DEPLOY_DETECTION_RULE,
            DefensiveAction.INCREASE_TELEMETRY,
            DefensiveAction.PATCH_OR_UPDATE,
        ]
        if exposure.privileged_identity_surface:
            actions.append(DefensiveAction.REVOKE_SESSION_CANDIDATE)
        return tuple(actions)
    return (
        DefensiveAction.PATCH_OR_UPDATE,
        DefensiveAction.DEPLOY_DETECTION_RULE,
        DefensiveAction.CONFIG_HARDENING,
    )


def _safe_ref(value: str, error: str) -> None:
    if _UNSAFE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_priority_datetime_requires_timezone")
    return value.isoformat()


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    if isinstance(model, DefensivePriorityReceipt):
        # Pydantic may normalize UTC datetimes to a trailing ``Z`` in JSON mode,
        # while the sealed draft intentionally uses ``datetime.isoformat()``.
        # Re-normalize the semantic timestamp before verifying the fingerprint so
        # equivalent timestamps do not look like tampering.
        payload["as_of"] = _iso(model.as_of)
    return payload


def _verify_fingerprint(model: BaseModel, error: str) -> None:
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
