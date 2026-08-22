"""Tenant-neutral cyber threat enrichment for EAY Jarvis.

This module fuses existing canonical threat records with FIRST EPSS observations and
MITRE ATT&CK defensive coverage metadata. It deliberately does not create company
risk truth. Global urgency may guide investigation order, but only company-bound
exposure/incident contracts may establish firm company impact.

V1 is defensive by construction:
- EPSS is treated as exploitation-likelihood, never proof of exploitation;
- CISA KEV remains the only canonical source allowed to assert known exploitation;
- ATT&CK mappings contain detection strategies, data components and telemetry refs,
  not attack instructions;
- no tenant/company identity is represented in the global receipt;
- no exploit generation, credential capture, remediation or execution authority is
  granted by this contract.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.cyber_defense_intelligence import (
    ThreatIntelligenceSource,
    ThreatKnowledgeRecord,
)

CYBER_THREAT_ENRICHMENT_CONTRACT = "eay-cyber-threat-enrichment-v1"

_CVE_ID = re.compile(r"^CVE-\d{4}-\d{4,}$")
_ATTACK_TECHNIQUE_ID = re.compile(r"^T\d{4}(?:\.\d{3})?$")
_ATTACK_DETECTION_ID = re.compile(r"^DET\d{4}$")
_ATTACK_DATA_COMPONENT_ID = re.compile(r"^DC\d{4}$")
_UNSAFE_REF = re.compile(
    r"(?i)(?:bearer(?:[-_: ]|$)|api[_-]?key|password|passwd|"
    r"session[_-]?(?:token|cookie|id)(?:[-_: ]|$)|access[_-]?token|"
    r"refresh[_-]?token|signed[_-]?url|x-goog-signature|x-amz-signature|"
    r"exploit[_-]?payload|reverse[_-]?shell|credential[_-]?dump|"
    r"persistence[_-]?payload|ransomware[_-]?payload|shellcode)"
)


class GlobalDefensiveUrgency(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EpssObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_THREAT_ENRICHMENT_CONTRACT
    source: Literal["first_epss"] = "first_epss"
    cve_id: str
    score: float = Field(ge=0.0, le=1.0)
    percentile: float = Field(ge=0.0, le=1.0)
    score_date: date
    observed_at: datetime
    recorded_at: datetime
    source_evidence_ref: str = Field(min_length=1)
    exploitation_confirmed: bool = False
    company_truth_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def observation_is_probabilistic_and_non_authoritative(self) -> EpssObservation:
        _cve(self.cve_id, "cyber_epss_invalid_cve_id")
        _aware(self.observed_at, "cyber_epss_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_epss_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_epss_recorded_at_predates_observation")
        if self.score_date > self.observed_at.date():
            raise ValueError("cyber_epss_score_date_after_observation")
        if self.exploitation_confirmed:
            raise ValueError("cyber_epss_never_confirms_exploitation")
        if self.company_truth_granted:
            raise ValueError("cyber_epss_never_grants_company_truth")
        if self.execution_authority_granted:
            raise ValueError("cyber_epss_never_grants_execution_authority")
        _safe_ref(self.source_evidence_ref, "cyber_epss_unsafe_reference_forbidden")
        _verify(self, "cyber_epss_fingerprint_mismatch")
        return self


class DefensiveTechniqueCoverage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_THREAT_ENRICHMENT_CONTRACT
    source: Literal["mitre_attack"] = "mitre_attack"
    technique_id: str
    attack_release_ref: str = Field(min_length=1)
    detection_strategy_ids: tuple[str, ...] = ()
    data_component_ids: tuple[str, ...] = ()
    telemetry_refs: tuple[str, ...] = ()
    observed_at: datetime
    recorded_at: datetime
    source_evidence_ref: str = Field(min_length=1)
    attack_instruction_content_allowed: bool = False
    exploit_generation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def coverage_is_detection_only(self) -> DefensiveTechniqueCoverage:
        _aware(self.observed_at, "cyber_attack_coverage_observed_at_requires_timezone")
        _aware(self.recorded_at, "cyber_attack_coverage_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("cyber_attack_coverage_recorded_at_predates_observation")
        if not _ATTACK_TECHNIQUE_ID.fullmatch(self.technique_id):
            raise ValueError("cyber_attack_coverage_invalid_technique_id")
        if not (
            self.detection_strategy_ids or self.data_component_ids or self.telemetry_refs
        ):
            raise ValueError("cyber_attack_coverage_requires_defensive_signal")
        _unique(
            self.detection_strategy_ids,
            "cyber_attack_detection_strategy_ids_must_be_unique",
        )
        _unique(self.data_component_ids, "cyber_attack_data_component_ids_must_be_unique")
        _unique(self.telemetry_refs, "cyber_attack_telemetry_refs_must_be_unique")
        if any(
            not _ATTACK_DETECTION_ID.fullmatch(value)
            for value in self.detection_strategy_ids
        ):
            raise ValueError("cyber_attack_coverage_invalid_detection_strategy_id")
        if any(
            not _ATTACK_DATA_COMPONENT_ID.fullmatch(value)
            for value in self.data_component_ids
        ):
            raise ValueError("cyber_attack_coverage_invalid_data_component_id")
        if self.attack_instruction_content_allowed:
            raise ValueError("cyber_attack_instruction_content_forbidden")
        if self.exploit_generation_permitted:
            raise ValueError("cyber_attack_exploit_generation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_attack_coverage_never_grants_execution_authority")
        for ref in (
            self.attack_release_ref,
            self.source_evidence_ref,
            *self.telemetry_refs,
        ):
            _safe_ref(ref, "cyber_attack_coverage_unsafe_reference_forbidden")
        _verify(self, "cyber_attack_coverage_fingerprint_mismatch")
        return self


class GlobalThreatEnrichmentReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    contract: str = CYBER_THREAT_ENRICHMENT_CONTRACT
    receipt_id: str = Field(min_length=1)
    cve_id: str
    as_of: datetime
    max_epss_age_days: int = Field(gt=0)
    threat_record_ids: tuple[str, ...] = Field(min_length=1)
    threat_record_fingerprints: tuple[str, ...] = Field(min_length=1)
    source_families: tuple[ThreatIntelligenceSource, ...] = Field(min_length=1)
    source_diversity_count: int = Field(ge=1)
    source_evidence_refs: tuple[str, ...] = Field(min_length=1)
    known_exploited_in_wild: bool
    severity_score_max: float | None = Field(default=None, ge=0.0, le=10.0)
    epss_score: float | None = Field(default=None, ge=0.0, le=1.0)
    epss_percentile: float | None = Field(default=None, ge=0.0, le=1.0)
    epss_score_date: date | None = None
    epss_current: bool = False
    attack_technique_ids: tuple[str, ...] = ()
    detection_strategy_ids: tuple[str, ...] = ()
    data_component_ids: tuple[str, ...] = ()
    telemetry_refs: tuple[str, ...] = ()
    global_defensive_urgency: GlobalDefensiveUrgency
    reason_codes: tuple[str, ...] = Field(min_length=1)
    advisory_only: bool = True
    exploitation_prediction_is_company_risk: bool = False
    company_exposure_granted: bool = False
    company_truth_granted: bool = False
    incident_confirmation_granted: bool = False
    exploit_generation_permitted: bool = False
    automatic_remediation_permitted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def receipt_is_global_and_non_authoritative(self) -> GlobalThreatEnrichmentReceipt:
        _cve(self.cve_id, "cyber_enrichment_invalid_cve_id")
        _aware(self.as_of, "cyber_enrichment_as_of_requires_timezone")
        _unique(self.threat_record_ids, "cyber_enrichment_record_ids_must_be_unique")
        _unique(
            self.threat_record_fingerprints,
            "cyber_enrichment_record_fingerprints_must_be_unique",
        )
        _unique(
            tuple(source.value for source in self.source_families),
            "cyber_enrichment_source_families_must_be_unique",
        )
        _unique(
            self.source_evidence_refs,
            "cyber_enrichment_source_evidence_refs_must_be_unique",
        )
        _unique(self.attack_technique_ids, "cyber_enrichment_attack_ids_must_be_unique")
        _unique(
            self.detection_strategy_ids,
            "cyber_enrichment_detection_ids_must_be_unique",
        )
        _unique(
            self.data_component_ids,
            "cyber_enrichment_data_component_ids_must_be_unique",
        )
        _unique(self.telemetry_refs, "cyber_enrichment_telemetry_refs_must_be_unique")
        _unique(self.reason_codes, "cyber_enrichment_reason_codes_must_be_unique")
        if len(self.threat_record_ids) != len(self.threat_record_fingerprints):
            raise ValueError("cyber_enrichment_record_binding_length_mismatch")
        if self.source_diversity_count != len(self.source_families):
            raise ValueError("cyber_enrichment_source_diversity_mismatch")
        epss_values = (self.epss_score, self.epss_percentile, self.epss_score_date)
        if any(value is not None for value in epss_values) and not all(
            value is not None for value in epss_values
        ):
            raise ValueError("cyber_enrichment_partial_epss_state_forbidden")
        if self.epss_current and self.epss_score is None:
            raise ValueError("cyber_enrichment_current_epss_requires_observation")
        if not self.advisory_only:
            raise ValueError("cyber_enrichment_must_remain_advisory")
        if self.exploitation_prediction_is_company_risk:
            raise ValueError("cyber_enrichment_epss_never_becomes_company_risk")
        if self.company_exposure_granted:
            raise ValueError("cyber_enrichment_never_grants_company_exposure")
        if self.company_truth_granted:
            raise ValueError("cyber_enrichment_never_grants_company_truth")
        if self.incident_confirmation_granted:
            raise ValueError("cyber_enrichment_never_confirms_incident")
        if self.exploit_generation_permitted:
            raise ValueError("cyber_enrichment_exploit_generation_forbidden")
        if self.automatic_remediation_permitted:
            raise ValueError("cyber_enrichment_auto_remediation_forbidden")
        if self.execution_authority_granted:
            raise ValueError("cyber_enrichment_never_grants_execution_authority")
        for ref in (
            self.receipt_id,
            *self.threat_record_ids,
            *self.source_evidence_refs,
            *self.telemetry_refs,
            *self.reason_codes,
        ):
            _safe_ref(ref, "cyber_enrichment_unsafe_reference_forbidden")
        _verify(self, "cyber_enrichment_receipt_fingerprint_mismatch")
        return self


def build_epss_observation(
    *,
    cve_id: str,
    score: float,
    percentile: float,
    score_date: date,
    observed_at: datetime,
    recorded_at: datetime,
    source_evidence_ref: str,
) -> EpssObservation:
    draft = {
        "contract": CYBER_THREAT_ENRICHMENT_CONTRACT,
        "source": "first_epss",
        "cve_id": cve_id,
        "score": score,
        "percentile": percentile,
        "score_date": score_date.isoformat(),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "source_evidence_ref": source_evidence_ref,
        "exploitation_confirmed": False,
        "company_truth_granted": False,
        "execution_authority_granted": False,
    }
    return EpssObservation.model_validate(_sealed(draft))


def build_attack_defensive_coverage(
    *,
    technique_id: str,
    attack_release_ref: str,
    detection_strategy_ids: tuple[str, ...] = (),
    data_component_ids: tuple[str, ...] = (),
    telemetry_refs: tuple[str, ...] = (),
    observed_at: datetime,
    recorded_at: datetime,
    source_evidence_ref: str,
) -> DefensiveTechniqueCoverage:
    draft = {
        "contract": CYBER_THREAT_ENRICHMENT_CONTRACT,
        "source": "mitre_attack",
        "technique_id": technique_id,
        "attack_release_ref": attack_release_ref,
        "detection_strategy_ids": list(detection_strategy_ids),
        "data_component_ids": list(data_component_ids),
        "telemetry_refs": list(telemetry_refs),
        "observed_at": _iso(observed_at),
        "recorded_at": _iso(recorded_at),
        "source_evidence_ref": source_evidence_ref,
        "attack_instruction_content_allowed": False,
        "exploit_generation_permitted": False,
        "execution_authority_granted": False,
    }
    return DefensiveTechniqueCoverage.model_validate(_sealed(draft))


def fuse_global_threat_intelligence(
    *,
    cve_id: str,
    threat_records: tuple[ThreatKnowledgeRecord, ...],
    as_of: datetime,
    max_epss_age_days: int,
    epss: EpssObservation | None = None,
    defensive_coverages: tuple[DefensiveTechniqueCoverage, ...] = (),
) -> GlobalThreatEnrichmentReceipt:
    """Fuse public threat evidence without creating company exposure or risk truth."""

    _cve(cve_id, "cyber_enrichment_invalid_cve_id")
    _aware(as_of, "cyber_enrichment_as_of_requires_timezone")
    if max_epss_age_days <= 0:
        raise ValueError("cyber_enrichment_max_epss_age_days_must_be_positive")
    if not threat_records:
        raise ValueError("cyber_enrichment_requires_threat_record")

    records = tuple(
        ThreatKnowledgeRecord.model_validate(item.model_dump(mode="json"))
        for item in threat_records
    )
    _unique(
        tuple(item.record_id for item in records),
        "cyber_enrichment_record_ids_must_be_unique",
    )
    _unique(
        tuple(item.fingerprint for item in records),
        "cyber_enrichment_record_fingerprints_must_be_unique",
    )
    for record in records:
        if cve_id not in record.cve_ids:
            raise ValueError("cyber_enrichment_record_cve_mismatch")
        if record.published_at > as_of or record.recorded_at > as_of:
            raise ValueError("cyber_enrichment_future_known_threat_record_forbidden")

    ordered_records = tuple(sorted(records, key=lambda item: item.record_id))
    attack_ids = tuple(
        sorted(
            {
                attack_id
                for record in ordered_records
                for attack_id in record.attack_technique_ids
            }
        )
    )
    source_families = tuple(
        sorted({item.source for item in ordered_records}, key=lambda item: item.value)
    )
    source_evidence = {item.source_evidence_ref for item in records}
    known_exploited = any(
        item.source is ThreatIntelligenceSource.CISA_KEV
        and item.known_exploited_in_wild
        for item in records
    )
    severity_values = tuple(
        item.severity_score for item in records if item.severity_score is not None
    )
    severity_max = max(severity_values) if severity_values else None

    epss_score: float | None = None
    epss_percentile: float | None = None
    epss_score_date: date | None = None
    epss_current = False
    if epss is not None:
        epss = EpssObservation.model_validate(epss.model_dump(mode="json"))
        if epss.cve_id != cve_id:
            raise ValueError("cyber_enrichment_epss_cve_mismatch")
        if epss.observed_at > as_of or epss.recorded_at > as_of:
            raise ValueError("cyber_enrichment_future_known_epss_forbidden")
        if epss.score_date > as_of.date():
            raise ValueError("cyber_enrichment_future_epss_score_forbidden")
        epss_score = epss.score
        epss_percentile = epss.percentile
        epss_score_date = epss.score_date
        epss_current = (as_of.date() - epss.score_date).days <= max_epss_age_days
        source_evidence.add(epss.source_evidence_ref)

    detection_ids: set[str] = set()
    component_ids: set[str] = set()
    telemetry_refs: set[str] = set()
    for raw in defensive_coverages:
        coverage = DefensiveTechniqueCoverage.model_validate(raw.model_dump(mode="json"))
        if coverage.observed_at > as_of or coverage.recorded_at > as_of:
            raise ValueError("cyber_enrichment_future_known_attack_coverage_forbidden")
        if coverage.technique_id not in attack_ids:
            raise ValueError("cyber_enrichment_attack_coverage_not_bound_to_threat")
        detection_ids.update(coverage.detection_strategy_ids)
        component_ids.update(coverage.data_component_ids)
        telemetry_refs.update(coverage.telemetry_refs)
        source_evidence.add(coverage.source_evidence_ref)

    urgency, reasons = _global_urgency(
        known_exploited=known_exploited,
        severity_score=severity_max,
        epss_score=epss_score if epss_current else None,
        epss_percentile=epss_percentile if epss_current else None,
        epss_present=epss is not None,
        epss_current=epss_current,
    )
    if attack_ids:
        reasons.append("attack_technique_context_present")
    if detection_ids or component_ids or telemetry_refs:
        reasons.append("defensive_detection_coverage_present")

    receipt_seed = {
        "cve_id": cve_id,
        "as_of": _iso(as_of),
        "record_fingerprints": [item.fingerprint for item in ordered_records],
        "epss_fingerprint": epss.fingerprint if epss is not None else None,
        "coverage_fingerprints": sorted(
            item.fingerprint for item in defensive_coverages
        ),
        "max_epss_age_days": max_epss_age_days,
    }
    receipt_id = f"global-threat-enrichment:{_fingerprint(receipt_seed)[:24]}"
    draft = {
        "contract": CYBER_THREAT_ENRICHMENT_CONTRACT,
        "receipt_id": receipt_id,
        "cve_id": cve_id,
        "as_of": _iso(as_of),
        "max_epss_age_days": max_epss_age_days,
        "threat_record_ids": [item.record_id for item in ordered_records],
        "threat_record_fingerprints": [item.fingerprint for item in ordered_records],
        "source_families": [item.value for item in source_families],
        "source_diversity_count": len(source_families),
        "source_evidence_refs": sorted(source_evidence),
        "known_exploited_in_wild": known_exploited,
        "severity_score_max": severity_max,
        "epss_score": epss_score,
        "epss_percentile": epss_percentile,
        "epss_score_date": epss_score_date.isoformat() if epss_score_date else None,
        "epss_current": epss_current,
        "attack_technique_ids": list(attack_ids),
        "detection_strategy_ids": sorted(detection_ids),
        "data_component_ids": sorted(component_ids),
        "telemetry_refs": sorted(telemetry_refs),
        "global_defensive_urgency": urgency.value,
        "reason_codes": reasons,
        "advisory_only": True,
        "exploitation_prediction_is_company_risk": False,
        "company_exposure_granted": False,
        "company_truth_granted": False,
        "incident_confirmation_granted": False,
        "exploit_generation_permitted": False,
        "automatic_remediation_permitted": False,
        "execution_authority_granted": False,
    }
    return GlobalThreatEnrichmentReceipt.model_validate(_sealed(draft))


def verify_global_threat_enrichment_receipt(
    *,
    receipt: GlobalThreatEnrichmentReceipt,
) -> None:
    GlobalThreatEnrichmentReceipt.model_validate(receipt.model_dump(mode="json"))


def _global_urgency(
    *,
    known_exploited: bool,
    severity_score: float | None,
    epss_score: float | None,
    epss_percentile: float | None,
    epss_present: bool,
    epss_current: bool,
) -> tuple[GlobalDefensiveUrgency, list[str]]:
    reasons: list[str] = []
    if known_exploited:
        reasons.append("cisa_kev_known_exploited")
    if epss_present:
        reasons.append("epss_current" if epss_current else "epss_stale")
    if epss_current and epss_score is not None:
        if epss_score >= 0.50:
            reasons.append("epss_high_probability")
        elif epss_score >= 0.10:
            reasons.append("epss_elevated_probability")
    if epss_current and epss_percentile is not None and epss_percentile >= 0.95:
        reasons.append("epss_top_percentile_band")
    if severity_score is not None:
        if severity_score >= 9.0:
            reasons.append("high_technical_severity")
        elif severity_score >= 7.0:
            reasons.append("elevated_technical_severity")

    if known_exploited:
        urgency = GlobalDefensiveUrgency.CRITICAL
    elif (
        epss_current
        and epss_score is not None
        and epss_score >= 0.50
        and (severity_score or 0.0) >= 7.0
    ):
        urgency = GlobalDefensiveUrgency.HIGH
    elif (
        (epss_current and epss_percentile is not None and epss_percentile >= 0.95)
        or (severity_score or 0.0) >= 7.0
    ):
        urgency = GlobalDefensiveUrgency.MEDIUM
    else:
        urgency = GlobalDefensiveUrgency.LOW

    if not reasons:
        reasons.append("limited_global_defensive_signal")
    return urgency, reasons


def _cve(value: str, error: str) -> None:
    if not _CVE_ID.fullmatch(value):
        raise ValueError(error)


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
    _aware(value, "cyber_enrichment_datetime_requires_timezone")
    return value.isoformat().replace("+00:00", "Z")


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
