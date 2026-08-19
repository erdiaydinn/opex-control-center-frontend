"""Deterministic admission for model-proposed Jarvis objective decomposition.

A planner may propose hundreds of independent lanes, but proposal is not execution.
This gate validates fan-out, tenant binding, fresh checkpoints, side-effect scheduling,
resource metadata and aggregate cost/concurrency budgets before constructing the
ParallelMissionPlan consumed by the governed swarm runtime.

Admission never grants truth or execution authority.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from .parallel_mission_scheduler import (
    LaneSchedulingClass,
    ParallelLaneSchedulingProfile,
)
from .swarm_worker_registry import SwarmLaneRequirement

OBJECTIVE_DECOMPOSITION_ADMISSION_CONTRACT = "eay-objective-decomposition-admission-v1"


class ProposedObjectiveLane(BaseModel):
    contract: str = OBJECTIVE_DECOMPOSITION_ADMISSION_CONTRACT
    lane: ParallelMissionLane
    profile: ParallelLaneSchedulingProfile
    requirement: SwarmLaneRequirement
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def proposal_is_consistent(self) -> "ProposedObjectiveLane":
        if self.profile.lane_id != self.lane.lane_id:
            raise ValueError("objective_decomposition_profile_lane_mismatch")
        if self.requirement.lane_id != self.lane.lane_id:
            raise ValueError("objective_decomposition_requirement_lane_mismatch")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("objective_decomposition_evidence_refs_must_be_unique")
        return self


class ObjectiveDecompositionProposal(BaseModel):
    contract: str = OBJECTIVE_DECOMPOSITION_ADMISSION_CONTRACT
    objective_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    lanes: tuple[ProposedObjectiveLane, ...] = Field(min_length=1, max_length=512)
    decomposition_evidence_refs: tuple[str, ...] = Field(min_length=1)
    max_parallel_lanes: int = Field(default=16, ge=1, le=16)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def proposal_is_bound_and_non_authoritative(self) -> "ObjectiveDecompositionProposal":
        if self.execution_authority_granted:
            raise ValueError("objective_decomposition_never_grants_execution_authority")
        lane_ids = [item.lane.lane_id for item in self.lanes]
        if len(lane_ids) != len(set(lane_ids)):
            raise ValueError("objective_decomposition_lane_ids_must_be_unique")
        if any(item.lane.definition.tenant_id != self.tenant_id for item in self.lanes):
            raise ValueError("objective_decomposition_cross_tenant_lane_forbidden")
        if len(self.decomposition_evidence_refs) != len(set(self.decomposition_evidence_refs)):
            raise ValueError("objective_decomposition_root_evidence_refs_must_be_unique")
        return self


class ObjectiveDecompositionPolicy(BaseModel):
    contract: str = OBJECTIVE_DECOMPOSITION_ADMISSION_CONTRACT
    max_lanes: int = Field(default=128, ge=1, le=512)
    max_mutating_lanes: int = Field(default=32, ge=0, le=512)
    max_total_cost_units: int = Field(default=50_000, ge=1, le=100_000_000)
    max_total_concurrency_weight: int = Field(default=1024, ge=1, le=8192)


class AdmittedObjectiveDecomposition(BaseModel):
    contract: str = OBJECTIVE_DECOMPOSITION_ADMISSION_CONTRACT
    plan: ParallelMissionPlan
    profiles: dict[str, ParallelLaneSchedulingProfile]
    requirements: dict[str, SwarmLaneRequirement]
    proposal_evidence_refs: tuple[str, ...]
    total_cost_units: int = Field(ge=0)
    total_concurrency_weight: int = Field(ge=0)
    mutating_lane_count: int = Field(ge=0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_is_complete_and_non_authoritative(self) -> "AdmittedObjectiveDecomposition":
        if self.execution_authority_granted:
            raise ValueError("objective_decomposition_admission_never_grants_execution_authority")
        lane_ids = {item.lane_id for item in self.plan.lanes}
        if set(self.profiles) != lane_ids or set(self.requirements) != lane_ids:
            raise ValueError("objective_decomposition_admission_maps_must_cover_plan")
        return self


def admit_objective_decomposition(
    *,
    proposal: ObjectiveDecompositionProposal,
    policy: ObjectiveDecompositionPolicy,
) -> AdmittedObjectiveDecomposition:
    """Fail closed before a model-proposed fan-out may enter swarm scheduling."""

    if len(proposal.lanes) > policy.max_lanes:
        raise ValueError("objective_decomposition_fanout_limit_exceeded")

    profiles: dict[str, ParallelLaneSchedulingProfile] = {}
    requirements: dict[str, SwarmLaneRequirement] = {}
    lanes: list[ParallelMissionLane] = []
    total_cost = 0
    total_weight = 0
    mutating = 0

    for proposed in proposal.lanes:
        lane = proposed.lane
        profile = proposed.profile
        checkpoint = lane.checkpoint
        if checkpoint.sequence != 0 or checkpoint.status is not MissionStatus.READY:
            raise ValueError("objective_decomposition_requires_fresh_checkpoint")

        has_mutation = lane.has_pending_side_effect()
        if has_mutation:
            mutating += 1
            if profile.scheduling_class is not LaneSchedulingClass.EXECUTION:
                raise ValueError("objective_decomposition_mutation_requires_execution_class")
            if profile.shedable or profile.preemptible:
                raise ValueError("objective_decomposition_mutation_cannot_be_shed_or_preempted")
        elif profile.scheduling_class is LaneSchedulingClass.EXECUTION:
            raise ValueError("objective_decomposition_read_lane_cannot_claim_execution_class")

        total_cost += profile.estimated_cost_units
        total_weight += profile.concurrency_weight
        lanes.append(lane)
        profiles[lane.lane_id] = profile
        requirements[lane.lane_id] = proposed.requirement

    if mutating > policy.max_mutating_lanes:
        raise ValueError("objective_decomposition_mutating_lane_limit_exceeded")
    if total_cost > policy.max_total_cost_units:
        raise ValueError("objective_decomposition_cost_budget_exceeded")
    if total_weight > policy.max_total_concurrency_weight:
        raise ValueError("objective_decomposition_concurrency_budget_exceeded")

    plan = ParallelMissionPlan(
        objective_ref=proposal.objective_ref,
        tenant_id=proposal.tenant_id,
        lanes=tuple(lanes),
        max_parallel_lanes=proposal.max_parallel_lanes,
    )
    return AdmittedObjectiveDecomposition(
        plan=plan,
        profiles=profiles,
        requirements=requirements,
        proposal_evidence_refs=proposal.decomposition_evidence_refs,
        total_cost_units=total_cost,
        total_concurrency_weight=total_weight,
        mutating_lane_count=mutating,
    )
