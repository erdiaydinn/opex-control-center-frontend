"""Bind durable reviewed outcome calibration to Jarvis reasoning strength.

Decision calibration is intentionally stored in an append-only, review-gated
ledger. This bridge is the only narrow adaptation surface from an active
calibration snapshot into the Intelligence Supremacy reasoning selector.

The bridge never mutates model weights, routing catalogs, business policy,
paid-token grants or execution authority. Missing/insufficient history remains
neutral. Conflicting reviewed field evidence strengthens reasoning instead of
averaging disagreement away. Missing live-company truth still wins and forces
the canonical INVESTIGATE_FIRST mode.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .decision_calibration_ledger import (
    ActiveCalibrationSnapshot,
    CalibrationSnapshotStatus,
)
from .decision_intelligence import ExecutiveDecisionPacket
from .intelligence_supremacy import (
    InformationGainPlan,
    ReasoningRisk,
    ReasoningStrengthPlan,
    select_reasoning_strength,
)

REASONING_CALIBRATION_BRIDGE_CONTRACT = "eay-reasoning-calibration-bridge-v1"
_CONFLICT_REASONING_MULTIPLIER = 0.84


class ReasoningCalibrationBinding(BaseModel):
    contract: str = REASONING_CALIBRATION_BRIDGE_CONTRACT
    tenant_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    task_family: str = Field(min_length=1)
    as_of: datetime
    snapshot_status: CalibrationSnapshotStatus
    snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    field_sample_count: int = Field(ge=0)
    effective_confidence_multiplier: float = Field(ge=0.5, le=1.05)
    evidence_refs: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    model_weights_mutated: bool = False
    business_policy_mutated: bool = False
    paid_frontier_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def binding_is_integral_and_non_authoritative(self) -> "ReasoningCalibrationBinding":
        _aware(self.as_of, "reasoning_calibration_binding_as_of_requires_timezone")
        if self.model_weights_mutated or self.business_policy_mutated:
            raise ValueError("reasoning_calibration_bridge_never_self_modifies_production")
        if self.paid_frontier_authority_granted:
            raise ValueError("reasoning_calibration_bridge_never_grants_paid_frontier")
        if self.execution_authority_granted:
            raise ValueError("reasoning_calibration_bridge_never_grants_execution_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("reasoning_calibration_evidence_refs_must_be_unique")
        if len(self.blockers) != len(set(self.blockers)):
            raise ValueError("reasoning_calibration_blockers_must_be_unique")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("reasoning_calibration_binding_fingerprint_mismatch")
        return self


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


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


def build_reasoning_calibration_binding(
    *,
    snapshot: ActiveCalibrationSnapshot,
    tenant_id: str,
    decision_type: str,
    task_family: str,
    as_of: datetime,
) -> ReasoningCalibrationBinding:
    """Convert one exact reviewed calibration snapshot into routing evidence.

    ACTIVE snapshots use the reviewed median multiplier. INSUFFICIENT snapshots
    are neutral. CONFLICT snapshots conservatively strengthen reasoning; they do
    not alter confidence thresholds or average contradictory field evidence.
    """

    _aware(as_of, "reasoning_calibration_binding_as_of_requires_timezone")
    snapshot = ActiveCalibrationSnapshot.model_validate(snapshot.model_dump(mode="json"))
    if snapshot.tenant_id != tenant_id:
        raise ValueError("reasoning_calibration_cross_tenant_snapshot")
    if snapshot.decision_type != decision_type:
        raise ValueError("reasoning_calibration_decision_type_mismatch")
    if snapshot.task_family != task_family:
        raise ValueError("reasoning_calibration_task_family_mismatch")
    if snapshot.as_of > as_of:
        raise ValueError("reasoning_calibration_future_snapshot_forbidden")

    blockers = list(snapshot.blockers)
    if snapshot.status is CalibrationSnapshotStatus.ACTIVE:
        multiplier = snapshot.confidence_multiplier
    elif snapshot.status is CalibrationSnapshotStatus.CONFLICT:
        multiplier = _CONFLICT_REASONING_MULTIPLIER
        blockers.append("reasoning_calibration_conflict_requires_stronger_reasoning")
    else:
        multiplier = 1.0
        blockers.append("reasoning_calibration_insufficient_history_neutral")

    draft = {
        "contract": REASONING_CALIBRATION_BRIDGE_CONTRACT,
        "tenant_id": tenant_id,
        "decision_type": decision_type,
        "task_family": task_family,
        "as_of": as_of.isoformat().replace("+00:00", "Z"),
        "snapshot_status": snapshot.status.value,
        "snapshot_fingerprint": snapshot.fingerprint,
        "field_sample_count": snapshot.eligible_sample_count,
        "effective_confidence_multiplier": multiplier,
        "evidence_refs": list(snapshot.evidence_refs),
        "blockers": list(dict.fromkeys(blockers)),
        "model_weights_mutated": False,
        "business_policy_mutated": False,
        "paid_frontier_authority_granted": False,
        "execution_authority_granted": False,
    }
    return ReasoningCalibrationBinding.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


def select_reasoning_strength_with_calibration(
    *,
    risk: ReasoningRisk,
    decision: ExecutiveDecisionPacket,
    information_gain: InformationGainPlan,
    binding: ReasoningCalibrationBinding,
) -> ReasoningStrengthPlan:
    """Feed reviewed field calibration into the canonical reasoning selector."""

    binding = ReasoningCalibrationBinding.model_validate(binding.model_dump(mode="json"))
    plan = select_reasoning_strength(
        risk=risk,
        decision=decision,
        information_gain=information_gain,
        calibrated_confidence_multiplier=binding.effective_confidence_multiplier,
    )
    payload = plan.model_dump(mode="json")
    payload["blockers"] = list(dict.fromkeys((*plan.blockers, *binding.blockers)))
    return ReasoningStrengthPlan.model_validate(payload)
