"""Bind situation-scoped Company Reasoning provenance into Jarvis decisions.

Strong reasoning is evidence, not decision authority. This adapter requires the
existing DecisionPacketInput to be explicitly bound to one exact
SituationCompanyReasoningExecution before delegating to the canonical decision
engine. It does not create a second truth or approval system.

All radar signals that can influence decision readiness (SURFACE/ESCALATE) must
carry the exact situation-reasoning fingerprint as provenance. Live Company
Reality remains independently required; strong reasoning cannot upgrade missing,
stale, conflicted or cross-tenant truth into a firm company claim.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .decision_intelligence import (
    DecisionPacketInput,
    ExecutiveDecisionPacket,
    build_decision_packet,
)
from .decision_truth_integrity import validate_decision_truth_receipt_integrity
from .proactive_intelligence import RadarDisposition
from .situation_company_reasoning import SituationCompanyReasoningExecution

SITUATION_REASONED_DECISION_CONTRACT = "eay-situation-reasoned-decision-v1"
_DECISION_INFLUENCING_DISPOSITIONS = frozenset(
    {RadarDisposition.SURFACE, RadarDisposition.ESCALATE}
)


class SituationReasonedDecision(BaseModel):
    contract: str = SITUATION_REASONED_DECISION_CONTRACT
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    situation_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    objective_ref: str = Field(min_length=1)
    reasoning_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reasoning_evidence_ref: str = Field(min_length=1)
    bound_signal_ids: tuple[str, ...] = Field(min_length=1)
    decision_packet: ExecutiveDecisionPacket
    truth_receipt_fingerprint: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    automatic_external_execution_allowed: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def decision_is_integral_and_non_executing(self) -> "SituationReasonedDecision":
        if self.decision_packet.decision_id != self.decision_id:
            raise ValueError("situation_reasoned_decision_packet_id_mismatch")
        if len(self.bound_signal_ids) != len(set(self.bound_signal_ids)):
            raise ValueError("situation_reasoned_decision_duplicate_bound_signal")
        if (
            self.decision_packet.automatic_external_execution_allowed
            or self.automatic_external_execution_allowed
            or self.execution_authority_granted
        ):
            raise ValueError("situation_reasoned_decision_never_grants_execution")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("situation_reasoned_decision_fingerprint_mismatch")
        return self


def situation_reasoning_evidence_ref(
    reasoning: SituationCompanyReasoningExecution,
) -> str:
    reasoning = SituationCompanyReasoningExecution.model_validate(
        reasoning.model_dump(mode="json")
    )
    return f"situation-reasoning://{reasoning.fingerprint}"


def situation_decision_id(
    *,
    reasoning: SituationCompanyReasoningExecution,
    bound_signal_ids: tuple[str, ...],
) -> str:
    reasoning = SituationCompanyReasoningExecution.model_validate(
        reasoning.model_dump(mode="json")
    )
    if not bound_signal_ids:
        raise ValueError("situation_reasoned_decision_requires_bound_signal")
    if len(bound_signal_ids) != len(set(bound_signal_ids)):
        raise ValueError("situation_reasoned_decision_duplicate_bound_signal")
    digest = _fingerprint(
        {
            "tenant_id": reasoning.tenant_id,
            "company_id": reasoning.company_id,
            "situation_fingerprint": reasoning.situation_fingerprint,
            "objective_ref": reasoning.objective_ref,
            "reasoning_fingerprint": reasoning.fingerprint,
            "bound_signal_ids": sorted(bound_signal_ids),
        }
    )
    return f"situation-decision://{reasoning.tenant_id}/{digest}"


def build_situation_reasoned_decision(
    *,
    reasoning: SituationCompanyReasoningExecution,
    payload: DecisionPacketInput,
    bound_signal_ids: tuple[str, ...],
) -> SituationReasonedDecision:
    """Build a canonical decision packet bound to exact situation reasoning."""

    reasoning = SituationCompanyReasoningExecution.model_validate(
        reasoning.model_dump(mode="json")
    )
    payload = DecisionPacketInput.model_validate(payload.model_dump(mode="json"))

    if not payload.requires_live_company_truth:
        raise ValueError("situation_reasoned_decision_requires_live_company_truth_gate")
    if not bound_signal_ids:
        raise ValueError("situation_reasoned_decision_requires_bound_signal")
    if len(bound_signal_ids) != len(set(bound_signal_ids)):
        raise ValueError("situation_reasoned_decision_duplicate_bound_signal")

    expected_id = situation_decision_id(
        reasoning=reasoning,
        bound_signal_ids=bound_signal_ids,
    )
    if payload.decision_id != expected_id:
        raise ValueError("situation_reasoned_decision_id_binding_mismatch")

    radar_by_id = {item.signal_id: item for item in payload.risk_radar.items}
    if len(radar_by_id) != len(payload.risk_radar.items):
        raise ValueError("situation_reasoned_decision_duplicate_radar_signal")
    missing_signal_ids = tuple(
        signal_id for signal_id in bound_signal_ids if signal_id not in radar_by_id
    )
    if missing_signal_ids:
        raise ValueError(
            "situation_reasoned_decision_bound_signal_missing:"
            + ",".join(missing_signal_ids)
        )

    influencing_signal_ids = {
        item.signal_id
        for item in payload.risk_radar.items
        if item.disposition in _DECISION_INFLUENCING_DISPOSITIONS
    }
    if set(bound_signal_ids) != influencing_signal_ids:
        raise ValueError(
            "situation_reasoned_decision_attention_signal_coverage_mismatch"
        )

    reasoning_ref = situation_reasoning_evidence_ref(reasoning)
    missing_provenance = tuple(
        signal_id
        for signal_id in bound_signal_ids
        if reasoning_ref not in set(radar_by_id[signal_id].provenance_refs)
    )
    if missing_provenance:
        raise ValueError(
            "situation_reasoned_decision_signal_reasoning_provenance_missing:"
            + ",".join(missing_provenance)
        )

    truth_fingerprint = None
    if payload.decision_truth is not None:
        truth = validate_decision_truth_receipt_integrity(payload.decision_truth)
        if truth.tenant_id != reasoning.tenant_id:
            raise ValueError("situation_reasoned_decision_truth_tenant_mismatch")
        truth_fingerprint = truth.receipt_fingerprint

    packet = build_decision_packet(payload)
    draft = {
        "contract": SITUATION_REASONED_DECISION_CONTRACT,
        "decision_id": payload.decision_id,
        "tenant_id": reasoning.tenant_id,
        "company_id": reasoning.company_id,
        "situation_fingerprint": reasoning.situation_fingerprint,
        "objective_ref": reasoning.objective_ref,
        "reasoning_fingerprint": reasoning.fingerprint,
        "reasoning_evidence_ref": reasoning_ref,
        "bound_signal_ids": list(bound_signal_ids),
        "decision_packet": packet.model_dump(mode="json"),
        "truth_receipt_fingerprint": truth_fingerprint,
        "automatic_external_execution_allowed": False,
        "execution_authority_granted": False,
    }
    return SituationReasonedDecision.model_validate(
        {**draft, "fingerprint": _fingerprint(draft)}
    )


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
