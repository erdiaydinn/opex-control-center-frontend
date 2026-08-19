"""Evidence-bound cyber defense intelligence for EAY Jarvis.

Global threat knowledge may be shared. Company exposure, incidents and response
authority may not. This module is deliberately advisory and defensive:
- threat intelligence never proves company exposure;
- company exposure never proves exploitation or incident causality;
- a mitigation candidate never grants execution authority;
- no exploit payload, credential material or raw secret-bearing evidence is
  retained by this contract.
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

CYBER_DEFENSE_INTELLIGENCE_CONTRACT = "eay-cyber-defense-intelligence-v1"

_SECRET_REF = re.compile(
    r"(?i)(?:authorization|bearer|api[_-]?key|token|password|passwd|secret|"
    r"session(?:id)?|cookie|signed[_-]?url|x-goog-signature|x-amz-signature)"
)
_OFFENSIVE_REF = re.compile(
    r"(?i)(?:exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|"
    r"persistence[_-]?payload|ransomware[_-]?payload|shellcode)"
)


class ThreatIntelligenceSource(str, Enum):
    CISA_KEV = "cisa_kev"
    NVD = "nvd"
    MITRE_ATTACK = "mitre_attack"
    OWASP = "owasp"
    VENDOR_ADVISORY = "vendor_advisory"


class ThreatFreshness(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    FUTURE_DATED = "future_dated"


class ExposureStatus(str, Enum):
    UNKNOWN = "unknown"
    NOT_EXPOSED = "not_exposed"
    POTENTIALLY_EXPOSED = "potentially_exposed"
    CONFIRMED_EXPOSED = "confirmed_exposed"


class AssetCriticality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class PatchStatus(str, Enum):
    UNKNOWN = "unknown"
    UNPATCHED = "unpatched"
    PATCH_PLANNED = "patch_planned"
    PATCHED = "patched"
    NOT_APPLICABLE = "not_applicable"


class DefensivePriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DefensiveAction(str, Enum):
    PATCH_OR_UPDATE = "patch_or_update"
    ISOLATE_ASSET_CANDIDATE = "isolate_asset_candidate"
    DISABLE_VULNERABLE_INTEGRATION_CANDIDATE = "disable_vulnerable_integration_candidate"
    ROTATE_CREDENTIAL_CANDIDATE = "rotate_credential_candidate"
    REVOKE_SESSION_CANDIDATE = "revoke_session_candidate"
    DEPLOY_DETECTION_RULE = "deploy_detection_rule"
    INCREASE_TELEMETRY = "increase_telemetry"
    WAF_OR_IPS_RULE_CANDIDATE = "waf_or_ips_rule_candidate"
    BACKUP_RESTORE_READINESS = "backup_restore_readiness"
    CONFIG_HARDENING = "config_hardening"


class ThreatKnowledgeRecord(BaseModel):
    contract: str = CYBER_DEFENSE_INTELLIGENCE_CONTRACT
    record_id: str = Field(min_length=1)
    source: ThreatIntelligenceSource
    source_record_id: str = Field(min_length=1)
    published_at: datetime
    recorded_at: datetime
    source_evidence_ref: str = Field(min_length=1)
    product_refs: tuple[str, ...] = ()
    cve_ids: tuple[str, ...] = ()
    cwe_ids: tuple[str, ...] = ()
    attack_technique_ids: tuple[str, ...] = ()
    severity_score: float | None = Field(default=None, ge=0.0, le=10.0)
    known_exploited_in_wild: bool = False
    inference_only: bool = False
    company_truth_granted: bool = False
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def record_is_integral_and_non_authoritative(self) -> ThreatKnowledgeRecord:
        _aware(self.published_at, "cyber_threat_published_at_requires_timezone")
        _aware(self.recorded_at, "cyber_threat_recorded_at_requires_timezone")
        if self.recorded_at < self.published_at:
            raise ValueError("cyber_threat_recorded_at_predates_publication")
        if self.known_exploited_in_wild and self.source is not ThreatIntelligenceSource.CISA_KEV:
            raise ValueError("cyber_known_exploited_requires_kev_source")
        if self.known_exploited_in_wild and self.inference_only:
            raise ValueError("cyber_known_exploited_cannot_be_inferred")
        if self.company_truth_granted:
            raise ValueError("cyber_global_threat_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_global_threat_never_confirms_company_incident")
        if self.execution_authority_granted:
            raise ValueError("cyber_global_threat_never_grants_execution_authority")
        _unique(self.product_refs, "cyber_threat_product_refs_must_be_unique")
        _unique(self.cve_ids, "cyber_threat_cve_ids_must_be_unique")
        _unique(self.cwe_ids, "cyber_threat_cwe_ids_must_be_unique")
        _unique(self.attack_technique_ids, "cyber_threat_attack_technique_ids_must_be_unique")
        for ref in (
            self.record_id,
            self.source_record_id,
            self.source_evidence_ref,
            *self.product_refs,
            *self.cve_ids,
            *self.cwe_ids,
            *self.attack_technique_ids,
        ):
            _safe_ref(ref, "cyber_threat_unsafe_reference_forbidden")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("cyber_threat_record_fingerprint_mismatch")
        return self


class ThreatKnowledgeLedgerSnapshot(BaseModel):
    contract: str = CYBER_DEFENSE_INTELLIGENCE_CONTRACT
    as_of: datetime
    records: tuple[ThreatKnowledgeRecord, ...]
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ledger_is_integral_and_non_authoritative(self) -> ThreatKnowledgeLedgerSnapshot:
        _aware(self.as_of, "cyber_threat_ledger_as_of_requires_timezone")
        seen: set[str] = set()
        for record in self.records:
            record = ThreatKnowledgeRecord.model_validate(record.model_dump(mode="json"))
            if record.record_id in seen:
                raise ValueError("cyber_threat_ledger_duplicate_record_id")
            seen.add(record.record_id)
            if record.published_at > self.as_of or record.recorded_at > self.as_of:
                raise ValueError("cyber_threat_ledger_contains_future_known_record")
        if self.execution_authority_granted:
            raise ValueError("cyber_threat_ledger_never_grants_execution_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("cyber_threat_ledger_fingerprint_mismatch")
        return self


class CompanyCyberExposure(BaseModel):
    contract: str = CYBER_DEFENSE_INTELLIGENCE_CONTRACT
    exposure_id: str = Field(min_length=1)
    identity: CompanyIdentity
    threat_record_id: str = Field(min_length=1)
    threat_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    asset_ref: str = Field(min_length=1)
    company_evidence_refs: tuple[str, ...] = ()
    status: ExposureStatus
    criticality: AssetCriticality
    patch_status: PatchStatus = PatchStatus.UNKNOWN
    internet_reachable: bool = False
    privileged_identity_surface: bool = False
    compensating_control_present: bool = False
    assessed_at: datetime
    recorded_at: datetime
    incident_confirmation_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def exposure_is_company_bound_and_non_authoritative(self) -> CompanyCyberExposure:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _aware(self.assessed_at, "cyber_exposure_assessed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_exposure_recorded_at_requires_timezone")
        if self.recorded_at < self.assessed_at:
            raise ValueError("cyber_exposure_recorded_at_predates_assessment")
        _unique(self.company_evidence_refs, "cyber_exposure_company_evidence_refs_must_be_unique")
        if self.status in {
            ExposureStatus.POTENTIALLY_EXPOSED,
            ExposureStatus.CONFIRMED_EXPOSED,
        } and not self.company_evidence_refs:
            raise ValueError("cyber_exposure_company_evidence_required")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_exposure_never_confirms_company_incident")
        if self.execution_authority_granted:
            raise ValueError("cyber_exposure_never_grants_execution_authority")
        for ref in (
            self.exposure_id,
            self.threat_record_id,
            self.asset_ref,
            *self.company_evidence_refs,
        ):
            _safe_ref(ref, "cyber_exposure_unsafe_reference_forbidden")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("cyber_exposure_fingerprint_mismatch")
        return self


class CyberRiskAssessment(BaseModel):
    contract: str = CYBER_DEFENSE_INTELLIGENCE_CONTRACT
    identity: CompanyIdentity
    exposure_id: str = Field(min_length=1)
    threat_record_id: str = Field(min_length=1)
    priority: DefensivePriority
    score: int = Field(ge=0, le=100)
    reason_codes: tuple[str, ...]
    advisory_only: bool = True
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def assessment_is_advisory(self) -> CyberRiskAssessment:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        if not self.advisory_only:
            raise ValueError("cyber_risk_assessment_must_remain_advisory")
        if self.execution_authority_granted:
            raise ValueError("cyber_risk_assessment_never_grants_execution_authority")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("cyber_risk_assessment_fingerprint_mismatch")
        return self


class DefensiveResponseCandidate(BaseModel):
    contract: str = CYBER_DEFENSE_INTELLIGENCE_CONTRACT
    candidate_id: str = Field(min_length=1)
    identity: CompanyIdentity
    exposure_id: str = Field(min_length=1)
    threat_record_id: str = Field(min_length=1)
    action: DefensiveAction
    target_ref: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    requires_human_approval: bool
    requires_effect_verification: bool = True
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def response_candidate_is_safe_and_non_authoritative(self) -> DefensiveResponseCandidate:
        CompanyIdentity.model_validate(self.identity.model_dump(mode="json"))
        _unique(self.evidence_refs, "cyber_response_evidence_refs_must_be_unique")
        mutating = {
            DefensiveAction.PATCH_OR_UPDATE,
            DefensiveAction.ISOLATE_ASSET_CANDIDATE,
            DefensiveAction.DISABLE_VULNERABLE_INTEGRATION_CANDIDATE,
            DefensiveAction.ROTATE_CREDENTIAL_CANDIDATE,
            DefensiveAction.REVOKE_SESSION_CANDIDATE,
            DefensiveAction.DEPLOY_DETECTION_RULE,
            DefensiveAction.WAF_OR_IPS_RULE_CANDIDATE,
            DefensiveAction.CONFIG_HARDENING,
        }
        if self.action in mutating and not self.requires_human_approval:
            raise ValueError("cyber_mutating_response_requires_human_approval")
        if not self.requires_effect_verification:
            raise ValueError("cyber_response_requires_effect_verification")
        if self.execution_authority_granted:
            raise ValueError("cyber_response_candidate_never_grants_execution_authority")
        for ref in (
            self.candidate_id,
            self.exposure_id,
            self.threat_record_id,
            self.target_ref,
            *self.evidence_refs,
        ):
            _safe_ref(ref, "cyber_response_unsafe_reference_forbidden")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("cyber_response_candidate_fingerprint_mismatch")
        return self


def build_threat_record(
    *,
    record_id: str,
    source: ThreatIntelligenceSource,
    source_record_id: str,
    published_at: datetime,
    recorded_at: datetime,
    source_evidence_ref: str,
    product_refs: tuple[str, ...] = (),
    cve_ids: tuple[str, ...] = (),
    cwe_ids: tuple[str, ...] = (),
    attack_technique_ids: tuple[str, ...] = (),
    severity_score: float | None = None,
    known_exploited_in_wild: bool = False,
    inference_only: bool = False,
) -> ThreatKnowledgeRecord:
    draft = {
        "contract": CYBER_DEFENSE_INTELLIGENCE_CONTRACT,
        "record_id": record_id,
        "source": source.value,
        "source_record_id": source_record_id,
        "published_at": _iso(published_at),
        "recorded_at": _iso(recorded_at),
        "source_evidence_ref": source_evidence_ref,
        "product_refs": list(product_refs),
        "cve_ids": list(cve_ids),
        "cwe_ids": list(cwe_ids),
        "attack_technique_ids": list(attack_technique_ids),
        "severity_score": severity_score,
        "known_exploited_in_wild": known_exploited_in_wild,
        "inference_only": inference_only,
        "company_truth_granted": False,
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    return ThreatKnowledgeRecord.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def new_threat_ledger(*, as_of: datetime) -> ThreatKnowledgeLedgerSnapshot:
    return _build_threat_ledger(records=(), as_of=as_of)


def append_threat_record(
    *,
    ledger: ThreatKnowledgeLedgerSnapshot,
    record: ThreatKnowledgeRecord,
    as_of: datetime,
) -> ThreatKnowledgeLedgerSnapshot:
    ledger = ThreatKnowledgeLedgerSnapshot.model_validate(ledger.model_dump(mode="json"))
    record = ThreatKnowledgeRecord.model_validate(record.model_dump(mode="json"))
    _aware(as_of, "cyber_threat_ledger_as_of_requires_timezone")
    existing = {item.record_id: item for item in ledger.records}
    if record.record_id in existing:
        if existing[record.record_id].fingerprint == record.fingerprint:
            return _build_threat_ledger(records=ledger.records, as_of=as_of)
        raise ValueError("cyber_threat_record_identity_payload_conflict")
    return _build_threat_ledger(records=(*ledger.records, record), as_of=as_of)


def threat_ledger_as_of(
    *,
    ledger: ThreatKnowledgeLedgerSnapshot,
    as_of: datetime,
) -> ThreatKnowledgeLedgerSnapshot:
    ledger = ThreatKnowledgeLedgerSnapshot.model_validate(ledger.model_dump(mode="json"))
    _aware(as_of, "cyber_threat_ledger_as_of_requires_timezone")
    records = tuple(
        record
        for record in ledger.records
        if record.published_at <= as_of and record.recorded_at <= as_of
    )
    return _build_threat_ledger(records=records, as_of=as_of)


def assess_threat_freshness(
    *,
    record: ThreatKnowledgeRecord,
    as_of: datetime,
    max_age_days: int = 7,
) -> ThreatFreshness:
    record = ThreatKnowledgeRecord.model_validate(record.model_dump(mode="json"))
    _aware(as_of, "cyber_threat_freshness_as_of_requires_timezone")
    if max_age_days < 0:
        raise ValueError("cyber_threat_freshness_max_age_must_be_nonnegative")
    if record.published_at > as_of or record.recorded_at > as_of:
        return ThreatFreshness.FUTURE_DATED
    age_seconds = (as_of - max(record.published_at, record.recorded_at)).total_seconds()
    if age_seconds <= max_age_days * 86400:
        return ThreatFreshness.FRESH
    return ThreatFreshness.STALE


def build_company_exposure(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure_id: str,
    asset_ref: str,
    company_evidence_refs: tuple[str, ...],
    status: ExposureStatus,
    criticality: AssetCriticality,
    assessed_at: datetime,
    recorded_at: datetime,
    patch_status: PatchStatus = PatchStatus.UNKNOWN,
    internet_reachable: bool = False,
    privileged_identity_surface: bool = False,
    compensating_control_present: bool = False,
) -> CompanyCyberExposure:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    threat = ThreatKnowledgeRecord.model_validate(threat.model_dump(mode="json"))
    draft = {
        "contract": CYBER_DEFENSE_INTELLIGENCE_CONTRACT,
        "exposure_id": exposure_id,
        "identity": identity.model_dump(mode="json"),
        "threat_record_id": threat.record_id,
        "threat_fingerprint": threat.fingerprint,
        "asset_ref": asset_ref,
        "company_evidence_refs": list(company_evidence_refs),
        "status": status.value,
        "criticality": criticality.value,
        "patch_status": patch_status.value,
        "internet_reachable": internet_reachable,
        "privileged_identity_surface": privileged_identity_surface,
        "compensating_control_present": compensating_control_present,
        "assessed_at": _iso(assessed_at),
        "recorded_at": _iso(recorded_at),
        "incident_confirmation_granted": False,
        "execution_authority_granted": False,
    }
    return CompanyCyberExposure.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def verify_exposure_binding(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure: CompanyCyberExposure,
) -> None:
    identity = CompanyIdentity.model_validate(identity.model_dump(mode="json"))
    threat = ThreatKnowledgeRecord.model_validate(threat.model_dump(mode="json"))
    exposure = CompanyCyberExposure.model_validate(exposure.model_dump(mode="json"))
    if exposure.identity.fingerprint != identity.fingerprint:
        raise ValueError("cyber_exposure_company_identity_mismatch")
    if exposure.threat_record_id != threat.record_id:
        raise ValueError("cyber_exposure_threat_record_mismatch")
    if exposure.threat_fingerprint != threat.fingerprint:
        raise ValueError("cyber_exposure_threat_fingerprint_mismatch")


def prioritize_company_exposure(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure: CompanyCyberExposure,
) -> CyberRiskAssessment:
    verify_exposure_binding(identity=identity, threat=threat, exposure=exposure)
    score = 0
    reasons: list[str] = []

    exposure_points = {
        ExposureStatus.UNKNOWN: 0,
        ExposureStatus.NOT_EXPOSED: 0,
        ExposureStatus.POTENTIALLY_EXPOSED: 20,
        ExposureStatus.CONFIRMED_EXPOSED: 35,
    }
    score += exposure_points[exposure.status]
    if exposure.status in {
        ExposureStatus.POTENTIALLY_EXPOSED,
        ExposureStatus.CONFIRMED_EXPOSED,
    }:
        reasons.append(f"exposure:{exposure.status.value}")

    if threat.known_exploited_in_wild:
        score += 25
        reasons.append("known_exploited_in_wild")
    if threat.severity_score is not None:
        score += round(threat.severity_score * 2)
        reasons.append("severity_observed")
    if exposure.internet_reachable:
        score += 10
        reasons.append("internet_reachable")
    if exposure.privileged_identity_surface:
        score += 10
        reasons.append("privileged_identity_surface")

    criticality_points = {
        AssetCriticality.LOW: 0,
        AssetCriticality.MEDIUM: 5,
        AssetCriticality.HIGH: 10,
        AssetCriticality.CRITICAL: 15,
    }
    score += criticality_points[exposure.criticality]
    if exposure.criticality in {AssetCriticality.HIGH, AssetCriticality.CRITICAL}:
        reasons.append(f"asset_criticality:{exposure.criticality.value}")

    if exposure.compensating_control_present:
        score -= 15
        reasons.append("compensating_control_present")
    if exposure.patch_status in {PatchStatus.PATCHED, PatchStatus.NOT_APPLICABLE}:
        score -= 40
        reasons.append(f"patch_status:{exposure.patch_status.value}")
    elif exposure.patch_status is PatchStatus.PATCH_PLANNED:
        score -= 5
        reasons.append("patch_status:patch_planned")

    if exposure.status is ExposureStatus.NOT_EXPOSED:
        score = 0
        reasons.append("company_evidence_not_exposed")

    score = min(100, max(0, score))
    if score >= 80:
        priority = DefensivePriority.CRITICAL
    elif score >= 60:
        priority = DefensivePriority.HIGH
    elif score >= 35:
        priority = DefensivePriority.MEDIUM
    else:
        priority = DefensivePriority.LOW

    draft = {
        "contract": CYBER_DEFENSE_INTELLIGENCE_CONTRACT,
        "identity": identity.model_dump(mode="json"),
        "exposure_id": exposure.exposure_id,
        "threat_record_id": threat.record_id,
        "priority": priority.value,
        "score": score,
        "reason_codes": reasons,
        "advisory_only": True,
        "execution_authority_granted": False,
    }
    return CyberRiskAssessment.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_defensive_response_candidate(
    *,
    identity: CompanyIdentity,
    threat: ThreatKnowledgeRecord,
    exposure: CompanyCyberExposure,
    candidate_id: str,
    action: DefensiveAction,
    target_ref: str,
    evidence_refs: tuple[str, ...],
    requires_human_approval: bool,
) -> DefensiveResponseCandidate:
    verify_exposure_binding(identity=identity, threat=threat, exposure=exposure)
    draft = {
        "contract": CYBER_DEFENSE_INTELLIGENCE_CONTRACT,
        "candidate_id": candidate_id,
        "identity": identity.model_dump(mode="json"),
        "exposure_id": exposure.exposure_id,
        "threat_record_id": threat.record_id,
        "action": action.value,
        "target_ref": target_ref,
        "evidence_refs": list(evidence_refs),
        "requires_human_approval": requires_human_approval,
        "requires_effect_verification": True,
        "execution_authority_granted": False,
    }
    return DefensiveResponseCandidate.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def _build_threat_ledger(
    *,
    records: tuple[ThreatKnowledgeRecord, ...],
    as_of: datetime,
) -> ThreatKnowledgeLedgerSnapshot:
    _aware(as_of, "cyber_threat_ledger_as_of_requires_timezone")
    safe_records = tuple(
        ThreatKnowledgeRecord.model_validate(item.model_dump(mode="json"))
        for item in records
        if item.published_at <= as_of and item.recorded_at <= as_of
    )
    draft = {
        "contract": CYBER_DEFENSE_INTELLIGENCE_CONTRACT,
        "as_of": _iso(as_of),
        "records": [item.model_dump(mode="json") for item in safe_records],
        "execution_authority_granted": False,
    }
    return ThreatKnowledgeLedgerSnapshot.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def _safe_ref(value: str, error: str) -> None:
    if _SECRET_REF.search(value) or _OFFENSIVE_REF.search(value):
        raise ValueError(error)


def _unique(values: tuple[str, ...], error: str) -> None:
    if len(values) != len(set(values)):
        raise ValueError(error)


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _iso(value: datetime) -> str:
    _aware(value, "cyber_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
