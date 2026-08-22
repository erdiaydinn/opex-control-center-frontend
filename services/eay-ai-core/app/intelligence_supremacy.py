"""Evidence-bound intelligence control loop for Jarvis.

This module closes a deliberate gap between existing EAY capabilities:
Company World, competing hypotheses, adaptive research, local-first reasoning,
decision readiness and outcome learning already exist independently.  The
control loop connects them without becoming a new source of truth, execution
authority, paid-token authority or self-modifying model policy.

The loop is intentionally simple and inspectable:

world / hypotheses / decision blockers
    -> explicit knowledge gaps
    -> read-only information-gain ranking
    -> reasoning-strength recommendation
    -> existing decision / mission fabric
    -> measured outcome
    -> review-gated confidence calibration candidate

A stronger model is never used as a substitute for missing authoritative
company truth.  Paid frontier use remains behind the existing platform-admin
grant/budget runtime.  Outcome evidence may calibrate future reasoning only
after an explicit review binding; it never mutates model weights or business
policy automatically.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from .decision_intelligence import DecisionReadiness, ExecutiveDecisionPacket
from .hypothesis_intelligence import HypothesisRanking
from .outcome_learning import DecisionOutcomeAssessment
from .world_model import WorldSnapshot

INTELLIGENCE_SUPREMACY_CONTRACT = "eay-intelligence-supremacy-loop-v1"


class KnowledgeGapKind(str, Enum):
    WORLD_CONTRADICTION = "world_contradiction"
    HYPOTHESIS_AMBIGUITY = "hypothesis_ambiguity"
    LIVE_COMPANY_TRUTH = "live_company_truth"
    DECISION_EVIDENCE = "decision_evidence"


class InvestigationKind(str, Enum):
    COMPANY_READ = "company_read"
    RESEARCH = "research"
    SIMULATION = "simulation"
    DETERMINISTIC_CHECK = "deterministic_check"


class ReasoningRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ReasoningMode(str, Enum):
    INVESTIGATE_FIRST = "investigate_first"
    LOCAL_SINGLE = "local_single"
    LOCAL_COUNCIL = "local_council"
    FRONTIER_ESCALATION_CANDIDATE = "frontier_escalation_candidate"
    HUMAN_REVIEW = "human_review"


class KnowledgeGap(BaseModel):
    gap_id: str = Field(min_length=1)
    kind: KnowledgeGapKind
    relevance: float = Field(ge=0.0, le=1.0)
    field_key: str | None = None
    hypothesis_ids: tuple[str, ...] = ()
    blocker_ref: str | None = None

    @model_validator(mode="after")
    def gap_is_specific(self) -> "KnowledgeGap":
        if self.kind is KnowledgeGapKind.WORLD_CONTRADICTION and not self.field_key:
            raise ValueError("world_contradiction_gap_requires_field_key")
        if self.kind is KnowledgeGapKind.HYPOTHESIS_AMBIGUITY and not self.hypothesis_ids:
            raise ValueError("hypothesis_gap_requires_hypothesis_ids")
        if self.kind in {KnowledgeGapKind.LIVE_COMPANY_TRUTH, KnowledgeGapKind.DECISION_EVIDENCE} and not self.blocker_ref:
            raise ValueError("decision_gap_requires_blocker_ref")
        return self


class InvestigationCandidate(BaseModel):
    investigation_id: str = Field(min_length=1)
    kind: InvestigationKind
    resolves_gap_ids: tuple[str, ...] = Field(min_length=1)
    discriminates_hypothesis_ids: tuple[str, ...] = ()
    expected_signal_quality: float = Field(ge=0.0, le=1.0)
    independent_source_gain: float = Field(ge=0.0, le=1.0)
    estimated_latency_ms: int = Field(ge=0, le=3_600_000)
    estimated_cost_units: float = Field(ge=0.0, le=10_000.0)
    evidence_ref: str = Field(min_length=1)
    read_only: bool = True
    external_side_effect: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def investigation_is_observational_only(self) -> "InvestigationCandidate":
        if not self.read_only or self.external_side_effect:
            raise ValueError("information_gain_investigation_must_be_read_only")
        if self.execution_authority_granted:
            raise ValueError("information_gain_never_grants_execution_authority")
        if len(self.resolves_gap_ids) != len(set(self.resolves_gap_ids)):
            raise ValueError("information_gain_gap_refs_must_be_unique")
        if len(self.discriminates_hypothesis_ids) != len(set(self.discriminates_hypothesis_ids)):
            raise ValueError("information_gain_hypothesis_refs_must_be_unique")
        return self


class InvestigationScore(BaseModel):
    investigation_id: str
    score: float = Field(ge=0.0)
    expected_gap_reduction: float = Field(ge=0.0)
    hypothesis_discrimination: float = Field(ge=0.0)
    cost_penalty: float = Field(ge=0.0)
    latency_penalty: float = Field(ge=0.0)
    evidence_ref: str


class InformationGainPlan(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    gap_ids: tuple[str, ...]
    ranked: tuple[InvestigationScore, ...]
    selected_investigation_ids: tuple[str, ...]
    total_selected_cost_units: float = Field(ge=0.0)
    unresolved_gap_ids: tuple[str, ...]
    automatic_execution_allowed: bool = False
    paid_frontier_authority_granted: bool = False

    @model_validator(mode="after")
    def plan_never_grants_authority(self) -> "InformationGainPlan":
        if self.automatic_execution_allowed:
            raise ValueError("information_gain_plan_never_auto_executes")
        if self.paid_frontier_authority_granted:
            raise ValueError("information_gain_plan_never_grants_paid_frontier")
        return self


class ReasoningStrengthPlan(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    risk: ReasoningRisk
    mode: ReasoningMode
    unresolved_gap_count: int = Field(ge=0)
    calibrated_confidence_multiplier: float = Field(ge=0.25, le=1.25)
    local_council_required: bool
    frontier_escalation_candidate: bool
    requires_platform_admin_paid_grant: bool
    human_review_required: bool
    blockers: tuple[str, ...] = ()
    paid_frontier_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def reasoning_plan_is_advisory(self) -> "ReasoningStrengthPlan":
        if self.paid_frontier_authority_granted:
            raise ValueError("reasoning_plan_never_grants_paid_frontier")
        if self.execution_authority_granted:
            raise ValueError("reasoning_plan_never_grants_execution_authority")
        return self


class IntelligenceCycle(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    tenant_id: str
    world_snapshot_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    gaps: tuple[KnowledgeGap, ...]
    information_gain: InformationGainPlan
    reasoning: ReasoningStrengthPlan
    decision_readiness: DecisionReadiness
    firm_company_claim_authorized: bool
    production_truth_promoted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def cycle_is_integral_and_non_promoting(self) -> "IntelligenceCycle":
        if self.production_truth_promoted:
            raise ValueError("intelligence_cycle_never_promotes_production_truth")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("intelligence_cycle_fingerprint_mismatch")
        return self


class LearningCalibrationCandidate(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    candidate_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    decision_type: str = Field(min_length=1)
    proposed_confidence_multiplier: float = Field(ge=0.25, le=1.25)
    outcome_evidence_refs: tuple[str, ...] = Field(min_length=1)
    recorded_at: datetime
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    active: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def candidate_requires_review(self) -> "LearningCalibrationCandidate":
        _aware(self.recorded_at, "learning_calibration_recorded_at_requires_timezone")
        if self.automatic_model_weight_update_allowed or self.automatic_policy_update_allowed:
            raise ValueError("learning_calibration_cannot_self_modify_production")
        if self.active:
            raise ValueError("learning_calibration_candidate_cannot_self_activate")
        expected = _fingerprint(_payload(self))
        if self.fingerprint != expected:
            raise ValueError("learning_calibration_candidate_fingerprint_mismatch")
        return self


class LearningCalibrationApproval(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_ref: str = Field(min_length=1)
    approval_evidence_ref: str = Field(min_length=1)
    approved_at: datetime

    @model_validator(mode="after")
    def approval_time_is_aware(self) -> "LearningCalibrationApproval":
        _aware(self.approved_at, "learning_calibration_approval_requires_timezone")
        return self


class ActiveLearningCalibration(BaseModel):
    contract: str = INTELLIGENCE_SUPREMACY_CONTRACT
    tenant_id: str
    decision_type: str
    confidence_multiplier: float = Field(ge=0.25, le=1.25)
    candidate_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    reviewer_ref: str
    approval_evidence_ref: str
    activated_at: datetime
    model_weights_mutated: bool = False
    business_policy_mutated: bool = False

    @model_validator(mode="after")
    def calibration_is_bounded(self) -> "ActiveLearningCalibration":
        _aware(self.activated_at, "active_learning_calibration_requires_timezone")
        if self.model_weights_mutated or self.business_policy_mutated:
            raise ValueError("active_learning_calibration_is_not_self_modification")
        return self


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _payload(model: BaseModel) -> dict[str, Any]:
    value = model.model_dump(mode="json")
    value.pop("fingerprint", None)
    return value


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def identify_knowledge_gaps(
    *,
    world: WorldSnapshot,
    hypotheses: HypothesisRanking | None,
    decision: ExecutiveDecisionPacket,
) -> tuple[KnowledgeGap, ...]:
    """Expose uncertainty instead of asking a stronger model to guess through it."""

    gaps: list[KnowledgeGap] = []
    seen: set[str] = set()

    for field_key in world.blocked_field_keys:
        gap_id = f"world:{field_key}"
        if gap_id in seen:
            continue
        seen.add(gap_id)
        gaps.append(
            KnowledgeGap(
                gap_id=gap_id,
                kind=KnowledgeGapKind.WORLD_CONTRADICTION,
                relevance=1.0,
                field_key=field_key,
            )
        )

    if hypotheses is not None and hypotheses.requires_more_evidence:
        hypothesis_ids = tuple(item.hypothesis_id for item in hypotheses.assessments[:5])
        if hypothesis_ids:
            gap_id = "hypothesis:ranking-ambiguous"
            seen.add(gap_id)
            leader_confidence = hypotheses.assessments[0].confidence if hypotheses.assessments else 0.0
            gaps.append(
                KnowledgeGap(
                    gap_id=gap_id,
                    kind=KnowledgeGapKind.HYPOTHESIS_AMBIGUITY,
                    relevance=max(0.25, min(1.0, 1.0 - leader_confidence)),
                    hypothesis_ids=hypothesis_ids,
                )
            )

    for blocker in decision.blockers:
        if blocker.startswith("live_company_"):
            kind = KnowledgeGapKind.LIVE_COMPANY_TRUTH
            relevance = 1.0
        elif blocker in {
            "hypothesis_requires_more_evidence",
            "blocked_external_source_governance",
            "no_material_attention_signal",
        }:
            kind = KnowledgeGapKind.DECISION_EVIDENCE
            relevance = 0.75
        else:
            continue
        gap_id = f"decision:{blocker}"
        if gap_id in seen:
            continue
        seen.add(gap_id)
        gaps.append(
            KnowledgeGap(
                gap_id=gap_id,
                kind=kind,
                relevance=relevance,
                blocker_ref=blocker,
            )
        )

    return tuple(gaps)


def plan_information_gain(
    *,
    gaps: tuple[KnowledgeGap, ...],
    investigations: tuple[InvestigationCandidate, ...],
    maximum_investigations: int = 3,
    maximum_cost_units: float = 100.0,
) -> InformationGainPlan:
    """Rank read-only tests by expected uncertainty reduction per cost/latency."""

    if maximum_investigations < 1 or maximum_investigations > 32:
        raise ValueError("information_gain_invalid_investigation_limit")
    if maximum_cost_units < 0:
        raise ValueError("information_gain_negative_cost_budget")

    gap_map = {item.gap_id: item for item in gaps}
    if len(gap_map) != len(gaps):
        raise ValueError("information_gain_duplicate_gap_id")

    scores: list[InvestigationScore] = []
    for candidate in investigations:
        relevant_gaps = [gap_map[item] for item in candidate.resolves_gap_ids if item in gap_map]
        gap_reduction = sum(item.relevance for item in relevant_gaps) * candidate.expected_signal_quality
        hypothesis_gap_ids = {
            hypothesis_id
            for gap in relevant_gaps
            for hypothesis_id in gap.hypothesis_ids
        }
        discrimination_count = len(hypothesis_gap_ids.intersection(candidate.discriminates_hypothesis_ids))
        hypothesis_discrimination = (
            discrimination_count * candidate.expected_signal_quality * (0.5 + 0.5 * candidate.independent_source_gain)
        )
        cost_penalty = candidate.estimated_cost_units / max(maximum_cost_units, 1.0)
        latency_penalty = min(candidate.estimated_latency_ms / 60_000.0, 10.0) * 0.05
        score = max(
            0.0,
            gap_reduction + hypothesis_discrimination + 0.25 * candidate.independent_source_gain - cost_penalty - latency_penalty,
        )
        scores.append(
            InvestigationScore(
                investigation_id=candidate.investigation_id,
                score=round(score, 6),
                expected_gap_reduction=round(gap_reduction, 6),
                hypothesis_discrimination=round(hypothesis_discrimination, 6),
                cost_penalty=round(cost_penalty, 6),
                latency_penalty=round(latency_penalty, 6),
                evidence_ref=candidate.evidence_ref,
            )
        )

    ranked = tuple(sorted(scores, key=lambda item: (-item.score, item.investigation_id)))
    candidate_map = {item.investigation_id: item for item in investigations}
    selected: list[str] = []
    covered: set[str] = set()
    total_cost = 0.0
    for item in ranked:
        if item.score <= 0 or len(selected) >= maximum_investigations:
            continue
        candidate = candidate_map[item.investigation_id]
        if total_cost + candidate.estimated_cost_units > maximum_cost_units:
            continue
        newly_covered = set(candidate.resolves_gap_ids).intersection(gap_map) - covered
        if not newly_covered:
            continue
        selected.append(candidate.investigation_id)
        covered.update(newly_covered)
        total_cost += candidate.estimated_cost_units

    unresolved = tuple(sorted(set(gap_map) - covered))
    return InformationGainPlan(
        gap_ids=tuple(sorted(gap_map)),
        ranked=ranked,
        selected_investigation_ids=tuple(selected),
        total_selected_cost_units=round(total_cost, 6),
        unresolved_gap_ids=unresolved,
    )


def select_reasoning_strength(
    *,
    risk: ReasoningRisk,
    decision: ExecutiveDecisionPacket,
    information_gain: InformationGainPlan,
    calibrated_confidence_multiplier: float = 1.0,
) -> ReasoningStrengthPlan:
    """Choose reasoning strength without treating model power as missing evidence."""

    if not 0.25 <= calibrated_confidence_multiplier <= 1.25:
        raise ValueError("reasoning_calibration_multiplier_out_of_bounds")

    unresolved = len(information_gain.unresolved_gap_ids)
    live_truth_blocked = any(item.startswith("live_company_") for item in decision.blockers)
    insufficient_evidence = decision.readiness in {DecisionReadiness.HOLD, DecisionReadiness.INVESTIGATE}

    blockers: list[str] = []
    if live_truth_blocked:
        blockers.append("reasoning_cannot_substitute_for_missing_live_company_truth")
        mode = ReasoningMode.INVESTIGATE_FIRST
        council = False
        frontier = False
        human = risk is ReasoningRisk.CRITICAL
    elif unresolved or insufficient_evidence:
        mode = ReasoningMode.INVESTIGATE_FIRST
        council = risk in {ReasoningRisk.HIGH, ReasoningRisk.CRITICAL}
        frontier = False
        human = risk is ReasoningRisk.CRITICAL
    else:
        calibration_weak = calibrated_confidence_multiplier < 0.85
        if risk is ReasoningRisk.CRITICAL:
            mode = ReasoningMode.HUMAN_REVIEW
            council = True
            frontier = True
            human = True
        elif risk is ReasoningRisk.HIGH or calibration_weak:
            mode = ReasoningMode.LOCAL_COUNCIL
            council = True
            frontier = True
            human = False
        else:
            mode = ReasoningMode.LOCAL_SINGLE
            council = False
            frontier = False
            human = False

    return ReasoningStrengthPlan(
        risk=risk,
        mode=mode,
        unresolved_gap_count=unresolved,
        calibrated_confidence_multiplier=calibrated_confidence_multiplier,
        local_council_required=council,
        frontier_escalation_candidate=frontier,
        requires_platform_admin_paid_grant=frontier,
        human_review_required=human,
        blockers=tuple(blockers),
    )


def build_intelligence_cycle(
    *,
    world: WorldSnapshot,
    hypotheses: HypothesisRanking | None,
    decision: ExecutiveDecisionPacket,
    investigations: tuple[InvestigationCandidate, ...],
    risk: ReasoningRisk,
    calibrated_confidence_multiplier: float = 1.0,
    maximum_investigations: int = 3,
    maximum_cost_units: float = 100.0,
) -> IntelligenceCycle:
    gaps = identify_knowledge_gaps(world=world, hypotheses=hypotheses, decision=decision)
    information_gain = plan_information_gain(
        gaps=gaps,
        investigations=investigations,
        maximum_investigations=maximum_investigations,
        maximum_cost_units=maximum_cost_units,
    )
    reasoning = select_reasoning_strength(
        risk=risk,
        decision=decision,
        information_gain=information_gain,
        calibrated_confidence_multiplier=calibrated_confidence_multiplier,
    )
    draft = {
        "contract": INTELLIGENCE_SUPREMACY_CONTRACT,
        "tenant_id": world.tenant_id,
        "world_snapshot_fingerprint": world.fingerprint,
        "gaps": [item.model_dump(mode="json") for item in gaps],
        "information_gain": information_gain.model_dump(mode="json"),
        "reasoning": reasoning.model_dump(mode="json"),
        "decision_readiness": decision.readiness.value,
        "firm_company_claim_authorized": decision.firm_company_claim_authorized,
        "production_truth_promoted": False,
    }
    return IntelligenceCycle.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def build_learning_calibration_candidate(
    *,
    assessment: DecisionOutcomeAssessment,
    decision_type: str,
    recorded_at: datetime,
) -> LearningCalibrationCandidate:
    _aware(recorded_at, "learning_calibration_recorded_at_requires_timezone")
    if not assessment.learning_evidence_refs:
        raise ValueError("learning_calibration_requires_outcome_evidence")
    draft = {
        "contract": INTELLIGENCE_SUPREMACY_CONTRACT,
        "candidate_id": f"calibration:{assessment.tenant_id}:{assessment.decision_id}",
        "tenant_id": assessment.tenant_id,
        "decision_id": assessment.decision_id,
        "decision_type": decision_type,
        "proposed_confidence_multiplier": assessment.suggested_confidence_multiplier,
        "outcome_evidence_refs": list(assessment.learning_evidence_refs),
        "recorded_at": recorded_at.isoformat().replace("+00:00", "Z"),
        "automatic_model_weight_update_allowed": False,
        "automatic_policy_update_allowed": False,
        "active": False,
    }
    return LearningCalibrationCandidate.model_validate({**draft, "fingerprint": _fingerprint(draft)})


def activate_learning_calibration(
    *,
    candidate: LearningCalibrationCandidate,
    approval: LearningCalibrationApproval,
) -> ActiveLearningCalibration:
    candidate = LearningCalibrationCandidate.model_validate(candidate.model_dump(mode="json"))
    if approval.candidate_fingerprint != candidate.fingerprint:
        raise ValueError("learning_calibration_approval_candidate_mismatch")
    if approval.approved_at < candidate.recorded_at:
        raise ValueError("learning_calibration_approval_predates_candidate")
    return ActiveLearningCalibration(
        tenant_id=candidate.tenant_id,
        decision_type=candidate.decision_type,
        confidence_multiplier=candidate.proposed_confidence_multiplier,
        candidate_fingerprint=candidate.fingerprint,
        reviewer_ref=approval.reviewer_ref,
        approval_evidence_ref=approval.approval_evidence_ref,
        activated_at=approval.approved_at,
    )
