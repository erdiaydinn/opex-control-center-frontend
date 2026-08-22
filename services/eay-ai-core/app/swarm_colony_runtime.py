"""Specialist colony composition for the canonical Jarvis swarm runtime.

Jarvis already executes admitted lanes concurrently through ``swarm_parallel_runtime``.
This module adds a hard specialization layer without creating a second scheduler or
mission engine. Reviewed colony topology is compiled into the existing
``SwarmLaneRequirement`` contract, so the canonical scheduler still owns resource,
idempotency, cost, concurrency, worker-health and mission-execution safety.

A colony is an expertise compartment, never an authority boundary. In particular,
side-effect lanes are compiled only to colonies explicitly reviewed for side effects;
assignment still does not grant business execution authority and canonical mission
execution must independently authorize and verify every effect.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_orchestration import ParallelMissionPlan
from .parallel_mission_scheduler import ParallelLaneSchedulingProfile
from .swarm_parallel_runtime import (
    SwarmExecutionPolicy,
    SwarmExecutionRound,
    SwarmWorkerRuntimeBinding,
    SwarmWave,
    execute_worker_bound_swarm_round,
    schedule_swarm_wave,
)
from .swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerRegistry,
)
from .worker_task_routing import WorkerTaskRoutingPreference

SWARM_COLONY_RUNTIME_CONTRACT = "eay-swarm-colony-runtime-v1"


class SwarmColonyKind(str, Enum):
    DATA = "data"
    OPERATIONS = "operations"
    RESEARCH = "research"
    SIMULATION = "simulation"
    EVIDENCE = "evidence"
    ACTION = "action"
    LEGAL = "legal"
    FINANCE = "finance"
    VISION = "vision"


class SwarmColonyDescriptor(BaseModel):
    contract: str = SWARM_COLONY_RUNTIME_CONTRACT
    colony_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    kind: SwarmColonyKind
    worker_classes: tuple[SwarmWorkerClass, ...] = Field(min_length=1)
    may_handle_side_effect_lanes: bool = False
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def colony_is_specialized_and_non_authoritative(self) -> "SwarmColonyDescriptor":
        if len(self.worker_classes) != len(set(self.worker_classes)):
            raise ValueError("swarm_colony_worker_classes_must_be_unique")
        if self.truth_authority_granted:
            raise ValueError("swarm_colony_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("swarm_colony_never_grants_execution_authority")
        if self.may_handle_side_effect_lanes and self.kind is not SwarmColonyKind.ACTION:
            raise ValueError("swarm_colony_only_action_colony_may_handle_side_effects")
        return self


class SwarmColonyTopology(BaseModel):
    contract: str = SWARM_COLONY_RUNTIME_CONTRACT
    tenant_id: str = Field(min_length=1)
    colonies: tuple[SwarmColonyDescriptor, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def topology_is_partitioned_and_tenant_bound(self) -> "SwarmColonyTopology":
        refs = [item.colony_ref for item in self.colonies]
        if len(refs) != len(set(refs)):
            raise ValueError("swarm_colony_refs_must_be_unique")
        if any(item.tenant_id != self.tenant_id for item in self.colonies):
            raise ValueError("swarm_colony_cross_tenant_descriptor_forbidden")
        classes = [worker_class for item in self.colonies for worker_class in item.worker_classes]
        if len(classes) != len(set(classes)):
            raise ValueError("swarm_worker_class_cannot_belong_to_multiple_colonies")
        return self


class SwarmColonyLanePolicy(BaseModel):
    lane_id: str = Field(min_length=1)
    allowed_colony_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def colonies_are_unique(self) -> "SwarmColonyLanePolicy":
        if len(self.allowed_colony_refs) != len(set(self.allowed_colony_refs)):
            raise ValueError("swarm_lane_colony_refs_must_be_unique")
        return self


class SwarmColonyAssignment(BaseModel):
    contract: str = SWARM_COLONY_RUNTIME_CONTRACT
    lane_id: str
    worker_id: str
    colony_ref: str
    colony_kind: SwarmColonyKind
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def assignment_is_non_authoritative(self) -> "SwarmColonyAssignment":
        if self.execution_authority_granted:
            raise ValueError("swarm_colony_assignment_never_grants_execution_authority")
        return self


class SwarmColonyWave(BaseModel):
    contract: str = SWARM_COLONY_RUNTIME_CONTRACT
    wave: SwarmWave
    assignments: tuple[SwarmColonyAssignment, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def wave_matches_canonical_assignment(self) -> "SwarmColonyWave":
        if self.execution_authority_granted:
            raise ValueError("swarm_colony_wave_never_grants_execution_authority")
        expected = [(item.lane_id, item.worker_id) for item in self.wave.assignments]
        actual = [(item.lane_id, item.worker_id) for item in self.assignments]
        if expected != actual:
            raise ValueError("swarm_colony_assignment_drift")
        return self


class SwarmColonyExecutionRound(BaseModel):
    contract: str = SWARM_COLONY_RUNTIME_CONTRACT
    execution: SwarmExecutionRound
    colony_wave: SwarmColonyWave
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def execution_matches_wave(self) -> "SwarmColonyExecutionRound":
        if self.execution_authority_granted:
            raise ValueError("swarm_colony_execution_never_grants_execution_authority")
        if self.execution.wave != self.colony_wave.wave:
            raise ValueError("swarm_colony_execution_wave_mismatch")
        return self


@dataclass(frozen=True)
class CompiledColonyRequirements:
    requirements: Mapping[str, SwarmLaneRequirement]


def _colony_by_ref(topology: SwarmColonyTopology) -> dict[str, SwarmColonyDescriptor]:
    return {item.colony_ref: item for item in topology.colonies}


def _colony_by_worker_class(
    topology: SwarmColonyTopology,
) -> dict[SwarmWorkerClass, SwarmColonyDescriptor]:
    return {
        worker_class: colony
        for colony in topology.colonies
        for worker_class in colony.worker_classes
    }


def _lane_has_side_effect(lane) -> bool:
    return any(step.side_effect for step in lane.definition.steps)


def compile_colony_requirements(
    *,
    plan: ParallelMissionPlan,
    base_requirements: Mapping[str, SwarmLaneRequirement],
    lane_policies: Mapping[str, SwarmColonyLanePolicy],
    topology: SwarmColonyTopology,
) -> CompiledColonyRequirements:
    """Compile reviewed colony specialization into canonical worker requirements."""

    if topology.tenant_id != plan.tenant_id:
        raise ValueError("swarm_colony_topology_plan_tenant_mismatch")
    lane_map = {item.lane_id: item for item in plan.lanes}
    if set(base_requirements) != set(lane_map):
        raise ValueError("swarm_colony_base_requirements_must_cover_plan_exactly")
    if set(lane_policies) != set(lane_map):
        raise ValueError("swarm_colony_lane_policies_must_cover_plan_exactly")

    colony_map = _colony_by_ref(topology)
    compiled: dict[str, SwarmLaneRequirement] = {}
    for lane_id, lane in lane_map.items():
        base = base_requirements[lane_id]
        policy = lane_policies[lane_id]
        if base.lane_id != lane_id or policy.lane_id != lane_id:
            raise ValueError("swarm_colony_lane_requirement_mismatch")

        selected_colonies: list[SwarmColonyDescriptor] = []
        for colony_ref in policy.allowed_colony_refs:
            colony = colony_map.get(colony_ref)
            if colony is None:
                raise ValueError("swarm_colony_lane_references_unknown_colony")
            selected_colonies.append(colony)

        if _lane_has_side_effect(lane):
            # A read/research/evidence colony may help reason about a write, but it may
            # never become the runtime owner of the mutating lane. The canonical mission
            # engine will still perform the actual authorization/effect verification.
            selected_colonies = [
                item for item in selected_colonies if item.may_handle_side_effect_lanes
            ]
            if not selected_colonies:
                raise ValueError("swarm_colony_side_effect_requires_action_colony")

        allowed_classes = {
            worker_class
            for colony in selected_colonies
            for worker_class in colony.worker_classes
        }
        if base.required_worker_classes:
            allowed_classes &= set(base.required_worker_classes)
        if not allowed_classes:
            raise ValueError("swarm_colony_requirement_has_no_eligible_worker_class")

        compiled[lane_id] = SwarmLaneRequirement(
            lane_id=lane_id,
            required_worker_classes=tuple(sorted(allowed_classes, key=lambda item: item.value)),
            required_capability_refs=base.required_capability_refs,
        )
    return CompiledColonyRequirements(requirements=compiled)


def _colony_assignments(
    *,
    wave: SwarmWave,
    registry: SwarmWorkerRegistry,
    topology: SwarmColonyTopology,
) -> tuple[SwarmColonyAssignment, ...]:
    worker_map = {item.worker_id: item for item in registry.workers}
    colony_by_class = _colony_by_worker_class(topology)
    assignments: list[SwarmColonyAssignment] = []
    for item in wave.assignments:
        worker = worker_map.get(item.worker_id)
        if worker is None:
            raise ValueError("swarm_colony_assignment_unknown_worker")
        colony = colony_by_class.get(worker.worker_class)
        if colony is None:
            raise ValueError("swarm_colony_worker_class_unmapped")
        assignments.append(
            SwarmColonyAssignment(
                lane_id=item.lane_id,
                worker_id=item.worker_id,
                colony_ref=colony.colony_ref,
                colony_kind=colony.kind,
            )
        )
    return tuple(assignments)


def schedule_colony_swarm_wave(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    base_requirements: Mapping[str, SwarmLaneRequirement],
    lane_policies: Mapping[str, SwarmColonyLanePolicy],
    topology: SwarmColonyTopology,
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    now,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
) -> SwarmColonyWave:
    """Schedule specialist colonies through the existing canonical swarm scheduler."""

    compiled = compile_colony_requirements(
        plan=plan,
        base_requirements=base_requirements,
        lane_policies=lane_policies,
        topology=topology,
    )
    wave = schedule_swarm_wave(
        plan=plan,
        profiles=profiles,
        requirements=compiled.requirements,
        registry=registry,
        policy=policy,
        now=now,
        routing_preferences=routing_preferences,
    )
    return SwarmColonyWave(
        wave=wave,
        assignments=_colony_assignments(
            wave=wave,
            registry=registry,
            topology=topology,
        ),
    )


async def execute_colony_swarm_round(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    base_requirements: Mapping[str, SwarmLaneRequirement],
    lane_policies: Mapping[str, SwarmColonyLanePolicy],
    topology: SwarmColonyTopology,
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    worker_bindings: Mapping[str, SwarmWorkerRuntimeBinding],
    now,
    max_transitions_per_lane: int = 100,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
) -> SwarmColonyExecutionRound:
    """Execute the reviewed colony wave through the canonical worker-bound runtime."""

    compiled = compile_colony_requirements(
        plan=plan,
        base_requirements=base_requirements,
        lane_policies=lane_policies,
        topology=topology,
    )
    execution = await execute_worker_bound_swarm_round(
        plan=plan,
        profiles=profiles,
        requirements=compiled.requirements,
        registry=registry,
        policy=policy,
        worker_bindings=worker_bindings,
        now=now,
        max_transitions_per_lane=max_transitions_per_lane,
        routing_preferences=routing_preferences,
    )
    colony_wave = SwarmColonyWave(
        wave=execution.wave,
        assignments=_colony_assignments(
            wave=execution.wave,
            registry=registry,
            topology=topology,
        ),
    )
    return SwarmColonyExecutionRound(execution=execution, colony_wave=colony_wave)
