"""Company-bound cyber incident assessment and defensive planning.

Public threat knowledge, company exposure, company incidents and response
authority are intentionally separate. A KEV entry, ATT&CK mapping or lone alert
never proves compromise. Strong company evidence may confirm an incident, but
this layer never proves actor attribution, causality or execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.company_context_boundary import CompanyIdentity
from app.cyber_defense_intelligence import DefensiveAction

COMPANY_CYBER_INCIDENT_CONTRACT = "eay-company-cyber-incident-intelligence-v1"

_UNSAFE_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|shellcode)"
)
_ATTACK = re.compile(r"^T\d{4}(?:\.\d{3})?$", re.IGNORECASE)


class SecuritySignalType(str, Enum):
    VULNERABILITY_EXPOSURE = "vulnerability_exposure"
    SUSPICIOUS_AUTH = "suspicious_auth"
    MALWARE_DETECTION = "malware_detection"
    ANOMALOUS_PROCESS = "anomalous_process"
    NETWORK_INDICATOR = "network_indicator"
    IDENTITY_RISK = "identity_risk"
    CONFIGURATION_DRIFT = "configuration_drift"
    SUPPLY_CHAIN_ALERT = "supply_chain_alert"
    CLOUD_CONTROL_ALERT = "cloud_control_alert"


class SecurityEvidenceStrength(str, Enum):
    OBSERVATION = "observation"
    CORRELATED = "correlated"
    VERIFIED_DETECTION = "verified_detection"
    HUMAN_CONFIRMATION = "human_confirmation"


class SecuritySourceFamily(str, Enum):
    VULNERABILITY = "vulnerability"
    ENDPOINT = "endpoint"
    IDENTITY = "identity"
    NETWORK = "network"
    CLOUD = "cloud"
    APPLICATION = "application"
    SUPPLY_CHAIN = "supply_chain"
    HUMAN = "human"


class IncidentStatus(str, Enum):
    UNCONFIRMED = "unconfirmed"
    SUSPICIOUS = "suspicious"
    CONFIRMED = "confirmed"


class CompanySecuritySignal(BaseModel):
    contract: str = COMPANY_CYBER_INCIDENT_CONTRACT
    signal_id: str = Field(min_length=1)
    identity: CompanyIdentity
    signal_type: SecuritySignalType
    evidence_strength: SecurityEvidenceStrength
    source_family: SecuritySourceFamily
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    asset_refs: tuple[str, ...] = ()
    exposure_refs: tuple[str, ...] = ()
    threat_record_refs: tuple[str, ...] = ()
    attack_technique_ids: tuple[str, ...] = ()
    observed_at: datetime
    recorded_at: datetime
    compromise_confirmed: bool = False
    threat_actor_attribution_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def signal_is_integral_and_non_authoritative(self) -> "CompanySecuritySignal":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.observed_at, "cyber_signal_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_signal_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_signal_recorded_at_predates_observation")
        if (
            self.evidence_strength is SecurityEvidenceStrength.HUMAN_CONFIRMATION
            and self.source_family is not SecuritySourceFamily.HUMAN
        ):
            raise ValueError("cyber_human_confirmation_requires_human_source")
        if self.compromise_confirmed:
            raise ValueError("cyber_signal_never_confirms_compromise")
        if self.threat_actor_attribution_proven:
            raise ValueError("cyber_signal_never_proves_threat_actor_attribution")
        if self.execution_authority_granted:
            raise ValueError("cyber_signal_never_grants_execution_authority")
        for values, error in (
            (self.evidence_refs, "cyber_signal_evidence_refs_must_be_unique"),
            (self.asset_refs, "cyber_signal_asset_refs_must_be_unique"),
            (self.exposure_refs, "cyber_signal_exposure_refs_must_be_unique"),
            (self.threat_record_refs, "cyber_signal_threat_refs_must_be_unique"),
            (self.attack_technique_ids, "cyber_signal_attack_ids_must_be_unique"),
        ):
            _unique(values, error)
        for technique_id in self.attack_technique_ids:
            if not _ATTACK.fullmatch(technique_id):
                raise ValueError("cyber_signal_attack_technique_invalid")
        for ref in (
            self.signal_id,
            *self.evidence_refs,
            *self.asset_refs,
            *self.exposure_refs,
            *self.threat_record_refs,
        ):
            _safe_ref(ref, "cyber_signal_unsafe_reference_forbidden")
        _verify_fingerprint(self, "cyber_signal_fingerprint_mismatch")
        return self


class CompanyIncidentAssessment(BaseModel):
    contract: str = COMPANY_CYBER_INCIDENT_CONTRACT
    incident_id: str = Field(min_length=1)
    identity: CompanyIdentity
    as_of: datetime
    status: IncidentStatus
    signal_ids: tuple[str, ...] = Field(min_length=1)
    signal_fingerprints: tuple[str, ...] = Field(min_length=1)
    independent_source_families: tuple[SecuritySourceFamily, ...]
    attack_technique_ids: tuple[str, ...]
    reason_codes: tuple[str, ...]
    actor_attribution_ref: str | None = None
    threat_actor_attribution_proven: bool = False
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def assessment_is_integral_and_bounded(self) -> "CompanyIncidentAssessment":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.as_of, "cyber_incident_as_of_requires_timezone")
        if len(self.signal_ids) != len(self.signal_fingerprints):
            raise ValueError("cyber_incident_signal_binding_length_mismatch")
        _unique(self.signal_ids, "cyber_incident_signal_ids_must_be_unique")
        _unique(
            self.signal_fingerprints,
            "cyber_incident_signal_fingerprints_must_be_unique",
        )
        _unique(
            tuple(item.value for item in self.independent_source_families),
            "cyber_incident_source_families_must_be_unique",
        )
        _unique(
            self.attack_technique_ids,
            "cyber_incident_attack_techniques_must_be_unique",
        )
        if self.actor_attribution_ref is not None:
            raise ValueError("cyber_incident_actor_attribution_not_supported_v1")
        if self.threat_actor_attribution_proven:
            raise ValueError("cyber_incident_never_self_proves_actor_attribution")
        if self.causal_claim_proven:
            raise ValueError("cyber_incident_never_self_proves_causality")
        if self.execution_authority_granted:
            raise ValueError("cyber_incident_never_grants_execution_authority")
        _verify_fingerprint(self, "cyber_incident_fingerprint_mismatch")
        return self


class DefensiveControlCandidate(BaseModel):
    contract: str = COMPANY_CYBER_INCIDENT_CONTRACT
    candidate_id: str = Field(min_length=1)
    identity: CompanyIdentity
    incident_id: str = Field(min_length=1)
    incident_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    action: DefensiveAction
    target_refs: tuple[str, ...] = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    reason_code: str = Field(min_length=1)
    requires_human_approval: bool
    requires_effect_verification: bool = True
    candidate_only: bool = True
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def candidate_is_non_authoritative(self) -> "DefensiveControlCandidate":
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _unique(self.target_refs, "cyber_control_target_refs_must_be_unique")
        _unique(self.evidence_refs, "cyber_control_evidence_refs_must_be_unique")
        if not self.candidate_only:
            raise ValueError("cyber_control_must_remain_candidate_only")
        if not self.requires_effect_verification:
            raise ValueError("cyber_control_requires_effect_verification")
        if _action_is_mutating(self.action) and not self.requires_human_approval:
            raise ValueError("cyber_control_mutation_requires_human_approval")
        if self.execution_authority_granted:
            raise ValueError("cyber_control_never_grants_execution_authority")
        # candidate_id is generated below from a fingerprint; user/company
        # evidence still passes the strict secret/offensive-reference filter.
        for ref in (self.incident_id, *self.target_refs, *self.evidence_refs):
            _safe_ref(ref, "cyber_control_unsafe_reference_forbidden")
        _verify_fingerprint(self, "cyber_control_fingerprint_mismatch")
        return self


class CompanyCyberDefensePlan(BaseModel):
    contract: str = COMPANY_CYBER_INCIDENT_CONTRACT
    identity: CompanyIdentity
    incident: CompanyIncidentAssessment
    generated_at: datetime
    candidates: tuple[DefensiveControlCandidate, ...]
    automatic_execution_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def plan_is_integral_and_non_authoritative(self) -> "CompanyCyberDefensePlan":
        identity = CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        incident = CompanyIncidentAssessment.model_validate(
            self.incident.model_dump(mode="json")
        )
        _aware(self.generated_at, "cyber_defense_plan_generated_at_requires_timezone")
        if incident.identity.fingerprint != identity.fingerprint:
            raise ValueError("cyber_defense_plan_incident_company_mismatch")
        seen: set[str] = set()
        for raw in self.candidates:
            candidate = DefensiveControlCandidate.model_validate(
                raw.model_dump(mode="json")
            )
            if candidate.candidate_id in seen:
                raise ValueError("cyber_defense_plan_duplicate_candidate_id")
            seen.add(candidate.candidate_id)
            if candidate.identity.fingerprint != identity.fingerprint:
                raise ValueError("cyber_defense_plan_candidate_company_mismatch")
            if candidate.incident_id != incident.incident_id:
                raise ValueError("cyber_defense_plan_candidate_incident_mismatch")
            if candidate.incident_fingerprint != incident.fingerprint:
                raise ValueError("cyber_defense_plan_incident_fingerprint_mismatch")
        if self.automatic_execution_permitted:
            raise ValueError("cyber_defense_plan_never_permits_automatic_execution")
        if self.execution_authority_granted:
            raise ValueError("cyber_defense_plan_never_grants_execution_authority")
        _verify_fingerprint(self, "cyber_defense_plan_fingerprint_mismatch")
        return self


def build_company_security_signal(
    *,
    identity: CompanyIdentity,
    signal_id: str,
    signal_type: SecuritySignalType,
    evidence_strength: SecurityEvidenceStrength,
    source_family: SecuritySourceFamily,
    evidence_refs: tuple[str, ...],
    observed_at: datetime,
    recorded_at: datetime,
    asset_refs: tuple[str, ...] = (),
    exposure_refs: tuple[str, ...] = (),
    threat_record_refs: tuple[str, ...] = (),
    attack_technique_ids: tuple[str, ...] = (),
) -> CompanySecuritySignal:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    draft = {
        "contract": COMPANY_CYBER_INCIDENT_CONTRACT,
        "signal_id": signal_id,
        "identity": identity.model_dump(mode="json"),
        "signal_type": signal_type.value,
        "evidence_strength": evidence_strength.value,
        "source_family": source_family.value,
        "evidence_refs": list(evidence_refs),
        "asset_refs": list(asset_refs),
        "exposure_refs": list(exposure_refs),
        "threat_record_refs": list(threat_record_refs),
        "attack_technique_ids": list(attack_technique_ids),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "compromise_confirmed": False,
        "threat_actor_attribution_proven": False,
        "execution_authority_granted": False,
    }
    return CompanySecuritySignal.model_validate(_sealed(draft))


def assess_company_incident(
    *,
    identity: CompanyIdentity,
    incident_id: str,
    signals: tuple[CompanySecuritySignal, ...],
    as_of: datetime,
) -> CompanyIncidentAssessment:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    _aware(as_of, "cyber_incident_as_of_requires_timezone")
    if not signals:
        raise ValueError("cyber_incident_requires_company_signal")

    eligible: list[CompanySecuritySignal] = []
    signal_ids: set[str] = set()
    for raw in signals:
        signal = CompanySecuritySignal.model_validate(raw.model_dump(mode="json"))
        if signal.identity.fingerprint != identity.fingerprint:
            raise ValueError("cyber_incident_cross_company_signal_forbidden")
        if signal.signal_id in signal_ids:
            raise ValueError("cyber_incident_duplicate_signal_id")
        signal_ids.add(signal.signal_id)
        if signal.observed_at <= as_of and signal.recorded_at <= as_of:
            eligible.append(signal)
    if not eligible:
        raise ValueError("cyber_incident_no_signal_known_as_of")

    families = {
        signal.source_family
        for signal in eligible
        if signal.evidence_strength is not SecurityEvidenceStrength.HUMAN_CONFIRMATION
    }
    human_confirmed = any(
        signal.evidence_strength is SecurityEvidenceStrength.HUMAN_CONFIRMATION
        and signal.source_family is SecuritySourceFamily.HUMAN
        for signal in eligible
    )
    verified = any(
        signal.evidence_strength is SecurityEvidenceStrength.VERIFIED_DETECTION
        for signal in eligible
    )
    correlated = any(
        signal.evidence_strength is SecurityEvidenceStrength.CORRELATED
        for signal in eligible
    )

    if human_confirmed:
        status = IncidentStatus.CONFIRMED
        reasons = ["human_incident_confirmation"]
    elif verified and len(families) >= 2:
        status = IncidentStatus.CONFIRMED
        reasons = ["verified_company_detection", "independent_company_signal_quorum"]
    elif verified or correlated or len(families) >= 2:
        status = IncidentStatus.SUSPICIOUS
        if verified:
            reasons = ["verified_detection_without_independent_quorum"]
        elif correlated:
            reasons = ["correlated_company_security_signal"]
        else:
            reasons = ["multiple_independent_observations"]
    else:
        status = IncidentStatus.UNCONFIRMED
        reasons = ["single_or_weak_company_observation"]

    techniques = tuple(
        sorted(
            {
                technique
                for signal in eligible
                for technique in signal.attack_technique_ids
            }
        )
    )
    draft = {
        "contract": COMPANY_CYBER_INCIDENT_CONTRACT,
        "incident_id": incident_id,
        "identity": identity.model_dump(mode="json"),
        "as_of": _iso(as_of),
        "status": status.value,
        "signal_ids": [signal.signal_id for signal in eligible],
        "signal_fingerprints": [signal.fingerprint for signal in eligible],
        "independent_source_families": [
            family.value for family in sorted(families, key=lambda item: item.value)
        ],
        "attack_technique_ids": list(techniques),
        "reason_codes": reasons,
        "actor_attribution_ref": None,
        "threat_actor_attribution_proven": False,
        "causal_claim_proven": False,
        "execution_authority_granted": False,
    }
    return CompanyIncidentAssessment.model_validate(_sealed(draft))


def build_company_cyber_defense_plan(
    *,
    identity: CompanyIdentity,
    incident: CompanyIncidentAssessment,
    signals: tuple[CompanySecuritySignal, ...],
    generated_at: datetime,
) -> CompanyCyberDefensePlan:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    incident = CompanyIncidentAssessment.model_validate(
        incident.model_dump(mode="json")
    )
    _aware(generated_at, "cyber_defense_plan_generated_at_requires_timezone")
    if incident.identity.fingerprint != identity.fingerprint:
        raise ValueError("cyber_defense_plan_incident_company_mismatch")

    signal_by_id: dict[str, CompanySecuritySignal] = {}
    for raw in signals:
        signal = CompanySecuritySignal.model_validate(raw.model_dump(mode="json"))
        if signal.identity.fingerprint != identity.fingerprint:
            raise ValueError("cyber_defense_plan_cross_company_signal_forbidden")
        if signal.signal_id in signal_by_id:
            raise ValueError("cyber_defense_plan_duplicate_signal_id")
        signal_by_id[signal.signal_id] = signal
    if set(signal_by_id) != set(incident.signal_ids):
        raise ValueError("cyber_defense_plan_signal_set_mismatch")
    for signal_id, fingerprint in zip(
        incident.signal_ids,
        incident.signal_fingerprints,
        strict=True,
    ):
        if signal_by_id[signal_id].fingerprint != fingerprint:
            raise ValueError("cyber_defense_plan_signal_fingerprint_mismatch")

    evidence_refs = tuple(
        sorted(
            {
                ref
                for signal in signal_by_id.values()
                for ref in signal.evidence_refs
            }
        )
    )
    asset_refs = tuple(
        sorted(
            {
                ref
                for signal in signal_by_id.values()
                for ref in signal.asset_refs
            }
        )
    ) or (f"incident:{incident.incident_id}",)

    families = {signal.source_family for signal in signal_by_id.values()}
    types = {signal.signal_type for signal in signal_by_id.values()}
    proposals: list[tuple[DefensiveAction, str]] = [
        (
            DefensiveAction.INCREASE_TELEMETRY,
            "preserve_and_increase_defensive_observability",
        )
    ]
    if incident.attack_technique_ids:
        proposals.append(
            (
                DefensiveAction.DEPLOY_DETECTION_RULE,
                "mapped_attack_technique_detection_candidate",
            )
        )
    if SecuritySignalType.VULNERABILITY_EXPOSURE in types:
        proposals.append(
            (
                DefensiveAction.PATCH_OR_UPDATE,
                "verified_or_suspected_vulnerability_exposure",
            )
        )
    if SecuritySourceFamily.IDENTITY in families:
        proposals.extend(
            (
                (
                    DefensiveAction.REVOKE_SESSION_CANDIDATE,
                    "identity_risk_session_containment_candidate",
                ),
                (
                    DefensiveAction.ROTATE_CREDENTIAL_CANDIDATE,
                    "identity_risk_credential_rotation_candidate",
                ),
            )
        )
    if SecuritySourceFamily.ENDPOINT in families:
        proposals.append(
            (
                DefensiveAction.ISOLATE_ASSET_CANDIDATE,
                "endpoint_containment_candidate",
            )
        )
    if SecuritySourceFamily.NETWORK in families:
        proposals.append(
            (
                DefensiveAction.WAF_OR_IPS_RULE_CANDIDATE,
                "network_containment_candidate",
            )
        )
    if SecuritySourceFamily.SUPPLY_CHAIN in families:
        proposals.append(
            (
                DefensiveAction.DISABLE_VULNERABLE_INTEGRATION_CANDIDATE,
                "supply_chain_integration_containment_candidate",
            )
        )
    if incident.status is IncidentStatus.CONFIRMED:
        proposals.append(
            (
                DefensiveAction.BACKUP_RESTORE_READINESS,
                "confirmed_incident_recovery_readiness",
            )
        )

    candidates: list[DefensiveControlCandidate] = []
    seen_actions: set[DefensiveAction] = set()
    for action, reason in proposals:
        if action in seen_actions:
            continue
        seen_actions.add(action)
        candidate_key = hashlib.sha256(
            f"{incident.fingerprint}|{action.value}".encode("utf-8")
        ).hexdigest()[:24]
        draft = {
            "contract": COMPANY_CYBER_INCIDENT_CONTRACT,
            "candidate_id": f"control:{candidate_key}",
            "identity": identity.model_dump(mode="json"),
            "incident_id": incident.incident_id,
            "incident_fingerprint": incident.fingerprint,
            "action": action.value,
            "target_refs": list(asset_refs),
            "evidence_refs": list(evidence_refs),
            "reason_code": reason,
            "requires_human_approval": _action_is_mutating(action),
            "requires_effect_verification": True,
            "candidate_only": True,
            "execution_authority_granted": False,
        }
        candidates.append(DefensiveControlCandidate.model_validate(_sealed(draft)))

    plan_draft = {
        "contract": COMPANY_CYBER_INCIDENT_CONTRACT,
        "identity": identity.model_dump(mode="json"),
        "incident": incident.model_dump(mode="json"),
        "generated_at": _iso(generated_at),
        "candidates": [item.model_dump(mode="json") for item in candidates],
        "automatic_execution_permitted": False,
        "execution_authority_granted": False,
    }
    return CompanyCyberDefensePlan.model_validate(_sealed(plan_draft))


def _action_is_mutating(action: DefensiveAction) -> bool:
    return action not in {
        DefensiveAction.INCREASE_TELEMETRY,
        DefensiveAction.BACKUP_RESTORE_READINESS,
    }


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
    _aware(value, "cyber_incident_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _sealed(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "fingerprint": _fingerprint(payload)}


def _verify_fingerprint(model: BaseModel, error: str) -> None:
    if getattr(model, "fingerprint") != _fingerprint(_payload(model)):
        raise ValueError(error)


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
