"""Capability-aware worker registry for large Jarvis swarms.

Workers are execution resources, not business identities or authorities. The registry
can describe hundreds of logical workers while keeping tenant, capability and
scheduling-class boundaries explicit. Routing a lane to a worker never grants truth,
permission or side-effect authority.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .mission_execution import MissionExecutionKind
from .parallel_mission_orchestration import ParallelMissionLane
from .parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile

SWARM_WORKER_REGISTRY_CONTRACT = "eay-swarm-worker-registry-v1"


class SwarmWorkerClass(str, Enum):
    GENERAL = "general"
    REASONING = "reasoning"
    RESEARCH = "research"
    COMPANY_READ = "company_read"
    EXECUTION = "execution"
    SIMULATION = "simulation"
    LEGAL = "legal"
    FINANCE = "finance"
    VISION = "vision"
    BROWSER = "browser"
    PHYSICAL = "physical"


class SwarmWorkerState(str, Enum):
    READY = "ready"
    DRAINING = "draining"
    SUSPENDED = "suspended"


class SwarmWorkerDescriptor(BaseModel):
    contract: str = SWARM_WORKER_REGISTRY_CONTRACT
    worker_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    worker_class: SwarmWorkerClass = SwarmWorkerClass.GENERAL
    supported_scheduling_classes: tuple[LaneSchedulingClass, ...] = Field(min_length=1)
    capability_refs: tuple[str, ...] = ()
    max_concurrent_assignments: int = Field(default=1, ge=1, le=8)
    state: SwarmWorkerState = SwarmWorkerState.READY
    local_first: bool = True
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    human_identity_asserted: bool = False

    @model_validator(mode="after")
    def worker_is_non_authoritative(self) -> "SwarmWorkerDescriptor":
        if self.truth_authority_granted:
            raise ValueError("swarm_worker_never_grants_truth_authority")
        if self.execution_authority_granted:
            raise ValueError("swarm_worker_never_grants_execution_authority")
        if self.human_identity_asserted:
            raise ValueError("swarm_worker_cannot_assert_human_identity")
        if len(self.supported_scheduling_classes) != len(set(self.supported_scheduling_classes)):
            raise ValueError("swarm_worker_scheduling_classes_must_be_unique")
        if len(self.capability_refs) != len(set(self.capability_refs)):
            raise ValueError("swarm_worker_capability_refs_must_be_unique")
        return self


class SwarmWorkerRegistry(BaseModel):
    contract: str = SWARM_WORKER_REGISTRY_CONTRACT
    tenant_id: str = Field(min_length=1)
    workers: tuple[SwarmWorkerDescriptor, ...] = Field(min_length=1, max_length=512)

    @model_validator(mode="after")
    def registry_is_tenant_bound(self) -> "SwarmWorkerRegistry":
        worker_ids = [item.worker_id for item in self.workers]
        if len(worker_ids) != len(set(worker_ids)):
            raise ValueError("swarm_worker_ids_must_be_unique")
        if any(item.tenant_id != self.tenant_id for item in self.workers):
            raise ValueError("swarm_cross_tenant_worker_forbidden")
        return self


class SwarmLaneRequirement(BaseModel):
    lane_id: str = Field(min_length=1)
    required_worker_classes: tuple[SwarmWorkerClass, ...] = ()
    required_capability_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def requirement_is_unique(self) -> "SwarmLaneRequirement":
        if len(self.required_worker_classes) != len(set(self.required_worker_classes)):
            raise ValueError("swarm_required_worker_classes_must_be_unique")
        if len(self.required_capability_refs) != len(set(self.required_capability_refs)):
            raise ValueError("swarm_required_capability_refs_must_be_unique")
        return self


def inferred_lane_capability_refs(lane: ParallelMissionLane) -> frozenset[str]:
    return frozenset(
        spec.capability_ref
        for spec in lane.specs
        if spec.kind is MissionExecutionKind.CAPABILITY and spec.capability_ref
    )


def eligible_swarm_workers(
    *,
    registry: SwarmWorkerRegistry,
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
    requirement: SwarmLaneRequirement,
) -> tuple[SwarmWorkerDescriptor, ...]:
    """Return deterministic routing candidates without granting execution authority."""

    if lane.definition.tenant_id != registry.tenant_id:
        raise ValueError("swarm_worker_route_tenant_mismatch")
    if requirement.lane_id != lane.lane_id or profile.lane_id != lane.lane_id:
        raise ValueError("swarm_worker_route_lane_mismatch")

    required_capabilities = set(requirement.required_capability_refs)
    required_capabilities.update(inferred_lane_capability_refs(lane))
    required_classes = set(requirement.required_worker_classes)

    matches = [
        worker
        for worker in registry.workers
        if worker.state is SwarmWorkerState.READY
        and profile.scheduling_class in worker.supported_scheduling_classes
        and (not required_classes or worker.worker_class in required_classes)
        and required_capabilities.issubset(set(worker.capability_refs))
    ]
    return tuple(sorted(matches, key=lambda item: item.worker_id))
