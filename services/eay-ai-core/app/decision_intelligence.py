"""Executive decision-readiness synthesis for EAY Jarvis.

This module combines source quality, competing hypotheses, proactive risk
signals and Live Company Reality readiness into a fail-closed decision packet.
It does not execute tools or mutate company state. Safe internal preparation
may be suggested only when the truth surface is sufficient; external or
irreversible actions stay blocked behind explicit human approval and existing
EAY authorization/policy layers.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from .decision_truth_integrity import validate_decision_truth_receipt_integrity
from .hypothesis_intelligence import HypothesisRanking
from .live_company_readiness import DecisionTruthReceipt, DecisionTruthStatus
from .proactive_intelligence import GovernedActionProposal, RadarDisposition, RiskRadar
from .source_governance import SourceGovernanceReport, SourceGovernanceStatus

DECISION_INTELLIGENCE_CONTRACT = "eay-decision-intelligence-v1"


class DecisionReadiness(str, Enum):
    HOLD = "hold"
    INVESTIGATE = "investigate"
    PREPARE = "prepare"
    ESCALATE = "escalate"


class DecisionPacketInput(BaseModel):
    decision_id: str = Field(min_length=1, max_length=180)
    source_reports: tuple[SourceGovernanceReport, ...] = ()
    hypothesis_ranking: HypothesisRanking | None = None
    risk_radar: RiskRadar
    actions: tuple[GovernedActionProposal, ...] = ()
    decision_truth: DecisionTruthReceipt | None = None
    requires_live_company_truth: bool = False
    requires_firm_company_claim: bool = False


class ExecutiveDecisionPacket(BaseModel):
    contract: str = DECISION_INTELLIGENCE_CONTRACT
    decision_id: str
    readiness: DecisionReadiness
    confidence_cap: float = Field(ge=0.0, le=1.0)
    top_signal_ids: tuple[str, ...] = ()
    leading_hypothesis_id: str | None = None
    safe_prepare_action_ids: tuple[str, ...] = ()
    approval_gated_action_ids: tuple[str, ...] = ()
    automatic_external_execution_allowed: bool = False
    human_review_required: bool = False
    blockers: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    decision_truth_status: DecisionTruthStatus | None = None
    truth_requirement_id: str | None = None
    firm_company_claim_authorized: bool = False


def build_decision_packet(payload: DecisionPacketInput) -> ExecutiveDecisionPacket:
    blockers: list[str] = []
    warnings: list[str] = []

    source_caps = [report.confidence_cap for report in payload.source_reports]
    source_cap = min(source_caps) if source_caps else 0.75
    blocked_sources = [
        report.kind.value
        for report in payload.source_reports
        if report.status is SourceGovernanceStatus.BLOCKED
    ]
    degraded_sources = [
        report.kind.value
        for report in payload.source_reports
        if report.status is SourceGovernanceStatus.DEGRADED
    ]
    if blocked_sources:
        blockers.append("blocked_external_source_governance")
    if degraded_sources:
        warnings.append("degraded_external_source_governance")

    truth = payload.decision_truth
    truth_invalid = False
    if truth is not None:
        try:
            truth = validate_decision_truth_receipt_integrity(truth)
        except ValueError:
            truth = None
            truth_invalid = True

    truth_status = truth.status if truth is not None else None
    truth_requirement_id = truth.requirement_id if truth is not None else None
    truth_cap = 1.0
    truth_hard_block = False
    firm_company_claim_authorized = False

    if payload.requires_firm_company_claim and not payload.requires_live_company_truth:
        blockers.append("firm_company_claim_requires_live_company_truth")
        truth_hard_block = True
        truth_cap = min(truth_cap, 0.25)

    if truth_invalid:
        blockers.append("live_company_truth_receipt_invalid")
        truth_hard_block = True
        truth_cap = min(truth_cap, 0.20)
    elif payload.requires_live_company_truth and truth is None:
        blockers.append("live_company_truth_receipt_missing")
        truth_hard_block = True
        truth_cap = min(truth_cap, 0.25)
    elif truth is not None:
        if truth.status is DecisionTruthStatus.BLOCKED:
            blockers.append("live_company_truth_blocked")
            truth_hard_block = True
            truth_cap = min(truth_cap, 0.25)
        elif truth.status is DecisionTruthStatus.QUALIFIED:
            warnings.append("live_company_truth_qualified")
            truth_cap = min(truth_cap, 0.60)
        elif truth.status is DecisionTruthStatus.PROCEED:
            firm_company_claim_authorized = truth.firm_claim_authorized

        if payload.requires_firm_company_claim and not truth.firm_claim_authorized:
            blockers.append("live_company_firm_claim_not_authorized")
            truth_hard_block = True
            truth_cap = min(truth_cap, 0.40)

    hypothesis_confidence = 0.75
    leading_hypothesis_id = None
    if payload.hypothesis_ranking is not None:
        leading_hypothesis_id = payload.hypothesis_ranking.leading_hypothesis_id
        if payload.hypothesis_ranking.assessments:
            hypothesis_confidence = payload.hypothesis_ranking.assessments[0].confidence
        if payload.hypothesis_ranking.requires_more_evidence:
            blockers.append("hypothesis_requires_more_evidence")

    attention_items = [
        item
        for item in payload.risk_radar.items
        if item.disposition in {RadarDisposition.SURFACE, RadarDisposition.ESCALATE}
    ]
    top_signal_ids = tuple(item.signal_id for item in attention_items[:5])
    radar_requires_review = any(item.requires_human_review for item in attention_items)

    safe_actions: list[str] = []
    gated_actions: list[str] = []
    for action in payload.actions:
        if action.external_side_effect or action.irreversible or action.requires_human_approval:
            gated_actions.append(action.action_id)
        else:
            safe_actions.append(action.action_id)

    if truth_hard_block and safe_actions:
        safe_actions = []
        warnings.append("decision_actions_suppressed_by_live_truth_gate")

    if payload.risk_radar.escalation_count == 0 and not attention_items:
        blockers.append("no_material_attention_signal")

    confidence_cap = min(source_cap, hypothesis_confidence, truth_cap)
    if blocked_sources:
        confidence_cap = min(confidence_cap, 0.40)
    if payload.hypothesis_ranking is not None and payload.hypothesis_ranking.requires_more_evidence:
        confidence_cap = min(confidence_cap, 0.60)

    if blocked_sources or truth_hard_block:
        readiness = DecisionReadiness.HOLD
    elif payload.hypothesis_ranking is not None and payload.hypothesis_ranking.requires_more_evidence:
        readiness = DecisionReadiness.INVESTIGATE
    elif payload.risk_radar.escalation_count > 0 and confidence_cap >= 0.65:
        readiness = DecisionReadiness.ESCALATE
    elif attention_items:
        readiness = DecisionReadiness.PREPARE
    else:
        readiness = DecisionReadiness.HOLD

    human_review_required = bool(
        radar_requires_review
        or gated_actions
        or readiness is DecisionReadiness.ESCALATE
        or truth_hard_block
    )
    if gated_actions:
        warnings.append("external_or_irreversible_actions_remain_approval_gated")

    return ExecutiveDecisionPacket(
        decision_id=payload.decision_id,
        readiness=readiness,
        confidence_cap=round(max(min(confidence_cap, 1.0), 0.0), 6),
        top_signal_ids=top_signal_ids,
        leading_hypothesis_id=leading_hypothesis_id,
        safe_prepare_action_ids=tuple(safe_actions),
        approval_gated_action_ids=tuple(gated_actions),
        automatic_external_execution_allowed=False,
        human_review_required=human_review_required,
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
        decision_truth_status=truth_status,
        truth_requirement_id=truth_requirement_id,
        firm_company_claim_authorized=firm_company_claim_authorized,
    )
