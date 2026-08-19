"""Evidence-bound replanning scope for long-running Jarvis objectives.

Reality can change while a durable objective is running. This module determines
which mission lanes may be regenerated safely and which must be held for review.
It never rewinds an attempted side effect and never converts a reality signal into
execution authority.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .mission_execution import MissionExecutionKind
from .mission_runtime import MissionStatus, StepStatus
from .parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan

OBJECTIVE_REPLANNING_CONTRACT = "eay-objective-replanning-v1"


class RealityChangeSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RealityChangeSignal(BaseModel):
    contract: str = OBJECTIVE_REPLANNING_CONTRACT
    signal_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    observed_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    affected_resource_refs: tuple[str, ...] = ()
    invalidated_truth_requirement_ids: tuple[str, ...] = ()
    changed_capability_refs: tuple[str, ...] = ()
    severity: RealityChangeSeverity = RealityChangeSeverity.MEDIUM
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def signal_is_evidence_bound_and_non_authoritative(self) -> "RealityChangeSignal":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("objective_replan_signal_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("objective_replan_signal_never_grants_execution_authority")
        if not (
            self.affected_resource_refs
            or self.invalidated_truth_requirement_ids
            or self.changed_capability_refs
        ):
            raise ValueError("objective_replan_signal_requires_affected_scope")
        for values, label in (
            (self.evidence_refs, "evidence_refs"),
            (self.affected_resource_refs, "resource_refs"),
            (self.invalidated_truth_requirement_ids, "truth_requirements"),
            (self.changed_capability_refs, "capabilities"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"objective_replan_signal_{label}_must_be_unique")
        return self


class LaneReplanDisposition(str, Enum):
    PRESERVE = "preserve"
    REPLAN_SAFE = "replan_safe"
    HOLD_FOR_REVIEW = "hold_for_review"


class LaneReplanAssessment(BaseModel):
    lane_id: str
    disposition: LaneReplanDisposition
    reason_codes: tuple[str, ...]
    triggering_signal_ids: tuple[str, ...] = ()


class ObjectiveReplanScope(BaseModel):
    contract: str = OBJECTIVE_REPLANNING_CONTRACT
    objective_ref: str
    tenant_id: str
    assessments: tuple[LaneReplanAssessment, ...]
    preserved_lane_ids: tuple[str, ...]
    auto_replan_lane_ids: tuple[str, ...]
    review_lane_ids: tuple[str, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def scope_is_partitioned_and_non_authoritative(self) -> "ObjectiveReplanScope":
        if self.execution_authority_granted:
            raise ValueError("objective_replan_never_grants_execution_authority")
        all_ids = [
            *self.preserved_lane_ids,
            *self.auto_replan_lane_ids,
            *self.review_lane_ids,
        ]
        if len(all_ids) != len(set(all_ids)):
            raise ValueError("objective_replan_lane_partition_overlap")
        if set(all_ids) != {item.lane_id for item in self.assessments}:
            raise ValueError("objective_replan_lane_partition_incomplete")
        return self


def _lane_change_reasons(
    lane: ParallelMissionLane,
    signal: RealityChangeSignal,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if set(lane.exclusive_resource_refs) & set(signal.affected_resource_refs):
        reasons.append("objective_replan_resource_changed")

    truth_requirements = {
        spec.decision_truth_requirement_id
        for spec in lane.specs
        if spec.decision_truth_requirement_id
    }
    if truth_requirements & set(signal.invalidated_truth_requirement_ids):
        reasons.append("objective_replan_truth_invalidated")

    capability_refs = {
        spec.capability_ref
        for spec in lane.specs
        if spec.kind is MissionExecutionKind.CAPABILITY and spec.capability_ref
    }
    if capability_refs & set(signal.changed_capability_refs):
        reasons.append("objective_replan_capability_changed")
    return tuple(reasons)


def _attempted_side_effect(lane: ParallelMissionLane) -> bool:
    step_map = {item.step_id: item for item in lane.definition.steps}
    return any(
        step_map[state.step_id].side_effect and state.attempts > 0
        for state in lane.checkpoint.steps
    )


def _ambiguous_side_effect(lane: ParallelMissionLane) -> bool:
    return any(
        state.status is StepStatus.BLOCKED and state.ambiguous_outcome
        for state in lane.checkpoint.steps
    )


def assess_objective_replan_scope(
    *,
    plan: ParallelMissionPlan,
    signals: tuple[RealityChangeSignal, ...],
) -> ObjectiveReplanScope:
    if not signals:
        raise ValueError("objective_replan_requires_signal")
    if any(signal.tenant_id != plan.tenant_id for signal in signals):
        raise ValueError("objective_replan_cross_tenant_signal_forbidden")
    signal_ids = [item.signal_id for item in signals]
    if len(signal_ids) != len(set(signal_ids)):
        raise ValueError("objective_replan_signal_ids_must_be_unique")

    assessments: list[LaneReplanAssessment] = []
    preserve: list[str] = []
    safe: list[str] = []
    review: list[str] = []

    for lane in plan.lanes:
        reasons: list[str] = []
        triggers: list[str] = []
        for signal in signals:
            matched = _lane_change_reasons(lane, signal)
            if matched:
                reasons.extend(matched)
                triggers.append(signal.signal_id)

        if not reasons:
            disposition = LaneReplanDisposition.PRESERVE
            reasons = ["objective_replan_lane_unaffected"]
            preserve.append(lane.lane_id)
        elif _ambiguous_side_effect(lane):
            disposition = LaneReplanDisposition.HOLD_FOR_REVIEW
            reasons.append("objective_replan_ambiguous_side_effect_requires_review")
            review.append(lane.lane_id)
        elif _attempted_side_effect(lane):
            disposition = LaneReplanDisposition.HOLD_FOR_REVIEW
            reasons.append("objective_replan_attempted_side_effect_requires_review")
            review.append(lane.lane_id)
        elif lane.checkpoint.status is MissionStatus.HALTED:
            disposition = LaneReplanDisposition.HOLD_FOR_REVIEW
            reasons.append("objective_replan_halted_lane_requires_review")
            review.append(lane.lane_id)
        else:
            disposition = LaneReplanDisposition.REPLAN_SAFE
            reasons.append("objective_replan_no_side_effect_attempted")
            safe.append(lane.lane_id)

        assessments.append(
            LaneReplanAssessment(
                lane_id=lane.lane_id,
                disposition=disposition,
                reason_codes=tuple(dict.fromkeys(reasons)),
                triggering_signal_ids=tuple(dict.fromkeys(triggers)),
            )
        )

    return ObjectiveReplanScope(
        objective_ref=plan.objective_ref,
        tenant_id=plan.tenant_id,
        assessments=tuple(assessments),
        preserved_lane_ids=tuple(preserve),
        auto_replan_lane_ids=tuple(safe),
        review_lane_ids=tuple(review),
    )


def compose_replanned_parallel_plan(
    *,
    original: ParallelMissionPlan,
    scope: ObjectiveReplanScope,
    replacements: Mapping[str, ParallelMissionLane],
) -> ParallelMissionPlan:
    """Replace only lanes explicitly classified safe for regeneration."""

    if scope.objective_ref != original.objective_ref:
        raise ValueError("objective_replan_scope_objective_mismatch")
    if scope.tenant_id != original.tenant_id:
        raise ValueError("objective_replan_scope_tenant_mismatch")
    if {item.lane_id for item in scope.assessments} != {item.lane_id for item in original.lanes}:
        raise ValueError("objective_replan_scope_lane_set_mismatch")
    if scope.review_lane_ids:
        raise ValueError("objective_replan_review_required")
    if set(replacements) != set(scope.auto_replan_lane_ids):
        raise ValueError("objective_replan_replacements_must_cover_safe_lanes_exactly")

    replacement_map = dict(replacements)
    updated: list[ParallelMissionLane] = []
    for lane in original.lanes:
        replacement = replacement_map.get(lane.lane_id)
        if replacement is None:
            updated.append(lane)
            continue
        if replacement.lane_id != lane.lane_id:
            raise ValueError("objective_replan_replacement_lane_id_mismatch")
        if replacement.definition.tenant_id != original.tenant_id:
            raise ValueError("objective_replan_replacement_tenant_mismatch")
        if replacement.checkpoint.sequence != 0:
            raise ValueError("objective_replan_replacement_requires_fresh_checkpoint")
        updated.append(replacement)

    return ParallelMissionPlan(
        objective_ref=original.objective_ref,
        tenant_id=original.tenant_id,
        lanes=tuple(updated),
        max_parallel_lanes=original.max_parallel_lanes,
    )
