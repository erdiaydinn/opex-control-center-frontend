"""Durable, review-gated decision calibration for Jarvis.

Outcome learning already produces bounded confidence-calibration candidates.
This module makes that feedback durable without turning historical telemetry,
CI or simulation into production truth. Candidate and approval records are
append-only, tenant/task scoped, time-cutoff safe and fingerprint sealed.

Only reviewed field evidence may contribute to an active production confidence
multiplier. Synthetic/repository/simulation evidence may be retained for
analysis but never votes in the production calibration snapshot. Conflicting
field calibrations fail closed rather than being silently averaged.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .intelligence_supremacy import LearningCalibrationApproval, LearningCalibrationCandidate
from .outcome_learning import AttributionStrength

DECISION_CALIBRATION_LEDGER_CONTRACT = "eay-decision-calibration-ledger-v1"


class CalibrationEvidenceClass(str, Enum):
    REAL_COMPANY_OUTCOME = "real_company_outcome"
    CONTROLLED_FIELD = "controlled_field"
    SYNTHETIC = "synthetic"
    REPOSITORY = "repository"
    SIMULATION = "simulation"


class CalibrationSnapshotStatus(str, Enum):
    ACTIVE = "active"
    INSUFFICIENT = "insufficient"
    CONFLICT = "conflict"


_PRODUCTION_EVIDENCE = {
    CalibrationEvidenceClass.REAL_COMPANY_OUTCOME,
    CalibrationEvidenceClass.CONTROLLED_FIELD,
}


class CalibrationCandidateRecord(BaseModel):
    contract: str = DECISION_CALIBRATION_LEDGER_CONTRACT
    record_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    task_family: str = Field(min_length=1)
    candidate: LearningCalibrationCandidate
    evidence_class: CalibrationEvidenceClass
    attribution_strength: AttributionStrength
    observed_at: datetime
    recorded_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def record_is_integral(self) -> "CalibrationCandidateRecord":
        _aware(self.observed_at, "calibration_record_observed_at_requires_timezone")
        _aware(self.recorded_at, "calibration_record_recorded_at_requires_timezone")
        if self.recorded_at < self.observed_at:
            raise ValueError("calibration_record_recorded_at_predates_observation")
        if self.candidate.tenant_id != self.tenant_id:
            raise ValueError("calibration_record_candidate_tenant_mismatch")
        if self.candidate.decision_type != self.decision_type:
            raise ValueError("calibration_record_candidate_decision_type_mismatch")
        if self.candidate.recorded_at > self.recorded_at:
            raise ValueError("calibration_record_predates_candidate")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("calibration_record_evidence_refs_must_be_unique")
        candidate = LearningCalibrationCandidate.model_validate(
            self.candidate.model_dump(mode="json")
        )
        if candidate.fingerprint != self.candidate.fingerprint:
            raise ValueError("calibration_record_candidate_integrity_mismatch")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("calibration_record_fingerprint_mismatch")
        return self


class CalibrationApprovalRecord(BaseModel):
    contract: str = DECISION_CALIBRATION_LEDGER_CONTRACT
    approval_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval: LearningCalibrationApproval
    recorded_at: datetime
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def approval_is_integral(self) -> "CalibrationApprovalRecord":
        _aware(self.recorded_at, "calibration_approval_recorded_at_requires_timezone")
        if self.approval.candidate_fingerprint != self.candidate_fingerprint:
            raise ValueError("calibration_approval_candidate_mismatch")
        if self.recorded_at < self.approval.approved_at:
            raise ValueError("calibration_approval_recorded_at_predates_approval")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("calibration_approval_record_fingerprint_mismatch")
        return self


class DecisionCalibrationLedger(BaseModel):
    contract: str = DECISION_CALIBRATION_LEDGER_CONTRACT
    tenant_id: str = Field(min_length=1)
    candidate_records: tuple[CalibrationCandidateRecord, ...] = ()
    approval_records: tuple[CalibrationApprovalRecord, ...] = ()
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ledger_is_append_only_shape(self) -> "DecisionCalibrationLedger":
        if any(item.tenant_id != self.tenant_id for item in self.candidate_records):
            raise ValueError("calibration_ledger_cross_tenant_candidate")
        if any(item.tenant_id != self.tenant_id for item in self.approval_records):
            raise ValueError("calibration_ledger_cross_tenant_approval")
        record_ids = [item.record_id for item in self.candidate_records]
        approval_ids = [item.approval_id for item in self.approval_records]
        candidate_fps = [item.candidate.fingerprint for item in self.candidate_records]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("calibration_ledger_duplicate_record_id")
        if len(approval_ids) != len(set(approval_ids)):
            raise ValueError("calibration_ledger_duplicate_approval_id")
        if len(candidate_fps) != len(set(candidate_fps)):
            raise ValueError("calibration_ledger_duplicate_candidate_fingerprint")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("calibration_ledger_fingerprint_mismatch")
        return self


class ActiveCalibrationSnapshot(BaseModel):
    contract: str = DECISION_CALIBRATION_LEDGER_CONTRACT
    tenant_id: str
    decision_type: str
    task_family: str
    as_of: datetime
    status: CalibrationSnapshotStatus
    confidence_multiplier: float = Field(ge=0.5, le=1.05)
    eligible_sample_count: int = Field(ge=0)
    candidate_fingerprints: tuple[str, ...]
    approval_fingerprints: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    blockers: tuple[str, ...] = ()
    model_weights_mutated: bool = False
    business_policy_mutated: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def snapshot_is_bounded(self) -> "ActiveCalibrationSnapshot":
        _aware(self.as_of, "active_calibration_as_of_requires_timezone")
        if self.model_weights_mutated or self.business_policy_mutated:
            raise ValueError("active_calibration_never_self_modifies_production")
        if self.execution_authority_granted:
            raise ValueError("active_calibration_never_grants_execution_authority")
        if self.status is not CalibrationSnapshotStatus.ACTIVE and self.confidence_multiplier != 1.0:
            raise ValueError("inactive_calibration_must_be_neutral")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("active_calibration_fingerprint_mismatch")
        return self


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    payload = model.model_dump(mode="json")
    payload.pop("fingerprint", None)
    return payload


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def new_decision_calibration_ledger(*, tenant_id: str) -> DecisionCalibrationLedger:
    draft = {
        "contract": DECISION_CALIBRATION_LEDGER_CONTRACT,
        "tenant_id": tenant_id,
        "candidate_records": [],
        "approval_records": [],
    }
    return DecisionCalibrationLedger.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_calibration_candidate_record(
    *,
    record_id: str,
    candidate: LearningCalibrationCandidate,
    task_family: str,
    evidence_class: CalibrationEvidenceClass,
    attribution_strength: AttributionStrength,
    observed_at: datetime,
    recorded_at: datetime,
    evidence_refs: tuple[str, ...],
) -> CalibrationCandidateRecord:
    candidate = LearningCalibrationCandidate.model_validate(candidate.model_dump(mode="json"))
    draft = {
        "contract": DECISION_CALIBRATION_LEDGER_CONTRACT,
        "record_id": record_id,
        "tenant_id": candidate.tenant_id,
        "decision_type": candidate.decision_type,
        "task_family": task_family,
        "candidate": candidate.model_dump(mode="json"),
        "evidence_class": evidence_class.value,
        "attribution_strength": attribution_strength.value,
        "observed_at": observed_at.isoformat().replace("+00:00", "Z"),
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "evidence_refs": list(evidence_refs),
    }
    return CalibrationCandidateRecord.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_calibration_approval_record(
    *,
    approval_id: str,
    tenant_id: str,
    approval: LearningCalibrationApproval,
    recorded_at: datetime,
) -> CalibrationApprovalRecord:
    draft = {
        "contract": DECISION_CALIBRATION_LEDGER_CONTRACT,
        "approval_id": approval_id,
        "tenant_id": tenant_id,
        "candidate_fingerprint": approval.candidate_fingerprint,
        "approval": approval.model_dump(mode="json"),
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
    }
    return CalibrationApprovalRecord.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def append_calibration_candidate(
    *,
    ledger: DecisionCalibrationLedger,
    record: CalibrationCandidateRecord,
) -> DecisionCalibrationLedger:
    ledger = DecisionCalibrationLedger.model_validate(ledger.model_dump(mode="json"))
    record = CalibrationCandidateRecord.model_validate(record.model_dump(mode="json"))
    if record.tenant_id != ledger.tenant_id:
        raise ValueError("calibration_ledger_cross_tenant_candidate")
    same_id = [item for item in ledger.candidate_records if item.record_id == record.record_id]
    same_fp = [item for item in ledger.candidate_records if item.candidate.fingerprint == record.candidate.fingerprint]
    if same_id or same_fp:
        existing = (same_id or same_fp)[0]
        if existing.fingerprint == record.fingerprint:
            return ledger
        raise ValueError("calibration_ledger_conflicting_candidate_duplicate")
    draft = {
        "contract": ledger.contract,
        "tenant_id": ledger.tenant_id,
        "candidate_records": [
            *(item.model_dump(mode="json") for item in ledger.candidate_records),
            record.model_dump(mode="json"),
        ],
        "approval_records": [item.model_dump(mode="json") for item in ledger.approval_records],
    }
    return DecisionCalibrationLedger.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def append_calibration_approval(
    *,
    ledger: DecisionCalibrationLedger,
    record: CalibrationApprovalRecord,
) -> DecisionCalibrationLedger:
    ledger = DecisionCalibrationLedger.model_validate(ledger.model_dump(mode="json"))
    record = CalibrationApprovalRecord.model_validate(record.model_dump(mode="json"))
    if record.tenant_id != ledger.tenant_id:
        raise ValueError("calibration_ledger_cross_tenant_approval")
    candidates = {
        item.candidate.fingerprint: item for item in ledger.candidate_records
    }
    candidate = candidates.get(record.candidate_fingerprint)
    if candidate is None:
        raise ValueError("calibration_approval_candidate_not_in_ledger")
    if record.approval.approved_at < candidate.recorded_at:
        raise ValueError("calibration_approval_predates_candidate_record")
    same_id = [item for item in ledger.approval_records if item.approval_id == record.approval_id]
    same_candidate = [
        item for item in ledger.approval_records
        if item.candidate_fingerprint == record.candidate_fingerprint
    ]
    if same_id or same_candidate:
        existing = (same_id or same_candidate)[0]
        if existing.fingerprint == record.fingerprint:
            return ledger
        raise ValueError("calibration_ledger_conflicting_approval_duplicate")
    draft = {
        "contract": ledger.contract,
        "tenant_id": ledger.tenant_id,
        "candidate_records": [item.model_dump(mode="json") for item in ledger.candidate_records],
        "approval_records": [
            *(item.model_dump(mode="json") for item in ledger.approval_records),
            record.model_dump(mode="json"),
        ],
    }
    return DecisionCalibrationLedger.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_active_calibration_snapshot(
    *,
    ledger: DecisionCalibrationLedger,
    decision_type: str,
    task_family: str,
    as_of: datetime,
    minimum_field_samples: int = 3,
    maximum_multiplier_spread: float = 0.30,
) -> ActiveCalibrationSnapshot:
    _aware(as_of, "active_calibration_as_of_requires_timezone")
    if minimum_field_samples < 1 or minimum_field_samples > 100:
        raise ValueError("active_calibration_invalid_minimum_samples")
    if maximum_multiplier_spread < 0 or maximum_multiplier_spread > 0.80:
        raise ValueError("active_calibration_invalid_spread")
    ledger = DecisionCalibrationLedger.model_validate(ledger.model_dump(mode="json"))

    approvals = {
        item.candidate_fingerprint: item
        for item in ledger.approval_records
        if item.approval.approved_at <= as_of and item.recorded_at <= as_of
    }
    eligible: list[CalibrationCandidateRecord] = []
    approval_records: list[CalibrationApprovalRecord] = []
    for item in ledger.candidate_records:
        if item.decision_type != decision_type or item.task_family != task_family:
            continue
        if item.observed_at > as_of or item.recorded_at > as_of:
            continue
        if item.evidence_class not in _PRODUCTION_EVIDENCE:
            continue
        approval = approvals.get(item.candidate.fingerprint)
        if approval is None:
            continue
        eligible.append(item)
        approval_records.append(approval)

    evidence_refs = tuple(
        dict.fromkeys(
            ref
            for item in eligible
            for ref in (
                *item.evidence_refs,
                *item.candidate.outcome_evidence_refs,
            )
        )
    )
    candidate_fps = tuple(item.candidate.fingerprint for item in eligible)
    approval_fps = tuple(item.fingerprint for item in approval_records)
    blockers: list[str] = []

    if len(eligible) < minimum_field_samples:
        status = CalibrationSnapshotStatus.INSUFFICIENT
        multiplier = 1.0
        blockers.append("active_calibration_field_sample_quorum_missing")
    else:
        multipliers = [item.candidate.proposed_confidence_multiplier for item in eligible]
        spread = max(multipliers) - min(multipliers)
        if spread > maximum_multiplier_spread:
            status = CalibrationSnapshotStatus.CONFLICT
            multiplier = 1.0
            blockers.append("active_calibration_field_evidence_conflict")
        else:
            status = CalibrationSnapshotStatus.ACTIVE
            multiplier = max(0.50, min(1.05, float(statistics.median(multipliers))))

    draft = {
        "contract": DECISION_CALIBRATION_LEDGER_CONTRACT,
        "tenant_id": ledger.tenant_id,
        "decision_type": decision_type,
        "task_family": task_family,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "status": status.value,
        "confidence_multiplier": round(multiplier, 6),
        "eligible_sample_count": len(eligible),
        "candidate_fingerprints": list(candidate_fps),
        "approval_fingerprints": list(approval_fps),
        "evidence_refs": list(evidence_refs),
        "blockers": blockers,
        "model_weights_mutated": False,
        "business_policy_mutated": False,
        "execution_authority_granted": False,
    }
    return ActiveCalibrationSnapshot.model_validate({**draft, "fingerprint": _fingerprint(draft)})
