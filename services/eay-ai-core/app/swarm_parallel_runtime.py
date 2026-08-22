"""High-scale, shard-based swarm scheduling and execution for Jarvis.

The swarm layer can admit up to hundreds of logical workers in one global wave.
It performs one global resource/idempotency safety pass, assigns reviewed workers,
then partitions the safe wave into small shards. Shards execute concurrently, while
each shard delegates mission semantics to the canonical parallel orchestrator.

Worker-bound execution resolves the actual lane runtime from the assigned worker id.
This makes quarantine/draining meaningful: a later round can route the same durable
lane to a different worker runtime without changing business authority. Legacy
lane-bound execution remains available for compatibility and uses the same admitted
wave executor.

Evidence-based routing preferences may reorder only the workers that are already
eligible under tenant/capability/scheduling/health rules. A preference can never make
a draining, suspended or otherwise ineligible worker executable.

No swarm path grants truth, permission or business authority.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Mapping

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelLaneResult,
    ParallelMissionLane,
    ParallelMissionPlan,
    ParallelMissionRound,
    execute_parallel_mission_round,
    parallel_lane_conflict_blockers,
)
from .parallel_mission_scheduler import (
    ParallelLaneSchedulingProfile,
    lane_preemption_allowed,
)
from .swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    eligible_swarm_workers,
)
from .worker_task_routing import WorkerTaskRoutingPreference

SWARM_PARALLEL_RUNTIME_CONTRACT = "eay-swarm-parallel-runtime-v1"


class SwarmExecutionPolicy(BaseModel):
    contract: str = SWARM_PARALLEL_RUNTIME_CONTRACT
    max_active_workers: int = Field(default=64, ge=1, le=256)
    shard_size: int = Field(default=16, ge=1, le=16)
    max_total_concurrency_weight: int = Field(default=256, ge=1, le=4096)
    max_round_cost_units: int = Field(default=10_000, ge=1, le=100_000_000)
    overload_mode: bool = False
    overload_shed_priority_below: int = Field(default=40, ge=0, le=100)


class SwarmAssignment(BaseModel):
    contract: str = SWARM_PARALLEL_RUNTIME_CONTRACT
    lane_id: str
    worker_id: str
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def assignment_is_non_authoritative(self) -> "SwarmAssignment":
        if self.execution_authority_granted:
            raise ValueError("swarm_assignment_never_grants_execution_authority")
        return self


class SwarmShard(BaseModel):
    contract: str = SWARM_PARALLEL_RUNTIME_CONTRACT
    shard_id: str
    assignments: tuple[SwarmAssignment, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def shard_is_unique(self) -> "SwarmShard":
        lane_ids = [item.lane_id for item in self.assignments]
        if len(lane_ids) != len(set(lane_ids)):
            raise ValueError("swarm_shard_lane_ids_must_be_unique")
        return self


class SwarmWave(BaseModel):
    contract: str = SWARM_PARALLEL_RUNTIME_CONTRACT
    objective_ref: str
    tenant_id: str
    selected_lane_ids: tuple[str, ...]
    assignments: tuple[SwarmAssignment, ...]
    shards: tuple[SwarmShard, ...]
    deferred: dict[str, tuple[str, ...]]
    total_concurrency_weight: int = Field(ge=0)
    total_cost_units: int = Field(ge=0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def wave_is_consistent_and_non_authoritative(self) -> "SwarmWave":
        if self.execution_authority_granted:
            raise ValueError("swarm_wave_never_grants_execution_authority")
        selected = list(self.selected_lane_ids)
        if len(selected) != len(set(selected)):
            raise ValueError("swarm_selected_lane_ids_must_be_unique")
        assignment_ids = [item.lane_id for item in self.assignments]
        if assignment_ids != selected:
            raise ValueError("swarm_assignment_selection_mismatch")
        shard_lane_ids = [item.lane_id for shard in self.shards for item in shard.assignments]
        if shard_lane_ids != selected:
            raise ValueError("swarm_shard_selection_mismatch")
        return self


class SwarmExecutionRound(BaseModel):
    contract: str = SWARM_PARALLEL_RUNTIME_CONTRACT
    wave: SwarmWave
    shard_rounds: tuple[ParallelMissionRound, ...]
    results: tuple[ParallelLaneResult, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def execution_is_bound_and_non_authoritative(self) -> "SwarmExecutionRound":
        if self.execution_authority_granted:
            raise ValueError("swarm_execution_never_grants_execution_authority")
        selected = set(self.wave.selected_lane_ids)
        result_ids = {item.lane_id for item in self.results}
        if selected != result_ids:
            raise ValueError("swarm_execution_result_selection_mismatch")
        if any(item.shared_execution_authority_granted for item in self.shard_rounds):
            raise ValueError("swarm_execution_shared_authority_forbidden")
        return self


SwarmLaneBindingResolver = Callable[[ParallelMissionLane], ParallelLaneBindings]


@dataclass(frozen=True)
class SwarmWorkerRuntimeBinding:
    worker_id: str
    resolve_lane_binding: SwarmLaneBindingResolver


def _terminal(lane: ParallelMissionLane) -> bool:
    return lane.checkpoint.status in {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.HALTED,
    }


def _ranking_key(
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
) -> tuple[int, float, int, str]:
    if profile.deadline_at is None:
        return (1, float("inf"), -lane.priority, lane.lane_id)
    return (0, profile.deadline_at.timestamp(), -lane.priority, lane.lane_id)


def _pick_worker(
    *,
    candidates: tuple[SwarmWorkerDescriptor, ...],
    assigned_counts: Mapping[str, int],
    preference: WorkerTaskRoutingPreference | None = None,
) -> SwarmWorkerDescriptor | None:
    available = [
        item
        for item in candidates
        if assigned_counts.get(item.worker_id, 0) < item.max_concurrent_assignments
    ]
    if not available:
        return None

    preference_rank = (
        {worker_id: index for index, worker_id in enumerate(preference.ordered_worker_ids)}
        if preference is not None
        else {}
    )
    fallback_rank = len(preference_rank) + 1
    return min(
        available,
        key=lambda item: (
            preference_rank.get(item.worker_id, fallback_rank),
            assigned_counts.get(item.worker_id, 0),
            item.worker_id,
        ),
    )


def _build_shards(
    assignments: tuple[SwarmAssignment, ...],
    *,
    shard_size: int,
) -> tuple[SwarmShard, ...]:
    shards: list[SwarmShard] = []
    for index in range(0, len(assignments), shard_size):
        shard_assignments = assignments[index : index + shard_size]
        shards.append(
            SwarmShard(
                shard_id=f"swarm-shard-{len(shards) + 1:03d}",
                assignments=shard_assignments,
            )
        )
    return tuple(shards)


def _validated_routing_preferences(
    *,
    plan: ParallelMissionPlan,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None,
) -> dict[str, WorkerTaskRoutingPreference]:
    preferences = dict(routing_preferences or {})
    lane_ids = {item.lane_id for item in plan.lanes}
    unknown = set(preferences) - lane_ids
    if unknown:
        raise ValueError("swarm_routing_preference_unknown_lane")
    for lane_id, preference in preferences.items():
        if preference.lane_id != lane_id:
            raise ValueError("swarm_routing_preference_lane_mismatch")
        if preference.tenant_id != plan.tenant_id:
            raise ValueError("swarm_routing_preference_tenant_mismatch")
        if preference.execution_authority_granted:
            raise ValueError("swarm_routing_preference_authority_forbidden")
    return preferences


def schedule_swarm_wave(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    requirements: Mapping[str, SwarmLaneRequirement],
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    now: datetime,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
) -> SwarmWave:
    """Globally admit a safe wave before any shard begins execution."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("swarm_scheduler_now_requires_timezone")
    if registry.tenant_id != plan.tenant_id:
        raise ValueError("swarm_registry_plan_tenant_mismatch")

    lane_map = {item.lane_id: item for item in plan.lanes}
    if set(profiles) != set(lane_map):
        raise ValueError("swarm_profiles_must_cover_plan_exactly")
    if set(requirements) != set(lane_map):
        raise ValueError("swarm_requirements_must_cover_plan_exactly")
    preferences = _validated_routing_preferences(
        plan=plan,
        routing_preferences=routing_preferences,
    )

    for lane_id, lane in lane_map.items():
        lane_preemption_allowed(lane=lane, profile=profiles[lane_id])

    ordered = sorted(
        plan.lanes,
        key=lambda lane: _ranking_key(lane, profiles[lane.lane_id]),
    )
    selected: list[ParallelMissionLane] = []
    assignments: list[SwarmAssignment] = []
    deferred: dict[str, tuple[str, ...]] = {}
    assigned_counts: dict[str, int] = {}
    total_weight = 0
    total_cost = 0

    for lane in ordered:
        profile = profiles[lane.lane_id]
        requirement = requirements[lane.lane_id]

        if _terminal(lane):
            deferred[lane.lane_id] = ("parallel_lane_terminal",)
            continue
        if (
            policy.overload_mode
            and profile.shedable
            and lane.priority < policy.overload_shed_priority_below
        ):
            deferred[lane.lane_id] = ("swarm_overload_shed",)
            continue
        if len(selected) >= policy.max_active_workers:
            deferred[lane.lane_id] = ("swarm_active_worker_capacity_deferred",)
            continue

        conflicts = parallel_lane_conflict_blockers(lane, tuple(selected))
        if conflicts:
            deferred[lane.lane_id] = conflicts
            continue
        if total_weight + profile.concurrency_weight > policy.max_total_concurrency_weight:
            deferred[lane.lane_id] = ("swarm_weight_capacity_deferred",)
            continue
        if total_cost + profile.estimated_cost_units > policy.max_round_cost_units:
            deferred[lane.lane_id] = (
                "swarm_cost_budget_shed" if profile.shedable else "swarm_cost_budget_deferred",
            )
            continue

        candidates = eligible_swarm_workers(
            registry=registry,
            lane=lane,
            profile=profile,
            requirement=requirement,
        )
        worker = _pick_worker(
            candidates=candidates,
            assigned_counts=assigned_counts,
            preference=preferences.get(lane.lane_id),
        )
        if worker is None:
            deferred[lane.lane_id] = ("swarm_worker_unavailable",)
            continue

        selected.append(lane)
        assignments.append(SwarmAssignment(lane_id=lane.lane_id, worker_id=worker.worker_id))
        assigned_counts[worker.worker_id] = assigned_counts.get(worker.worker_id, 0) + 1
        total_weight += profile.concurrency_weight
        total_cost += profile.estimated_cost_units

    assignment_tuple = tuple(assignments)
    shard_size = min(policy.shard_size, plan.max_parallel_lanes)
    return SwarmWave(
        objective_ref=plan.objective_ref,
        tenant_id=plan.tenant_id,
        selected_lane_ids=tuple(item.lane_id for item in selected),
        assignments=assignment_tuple,
        shards=_build_shards(assignment_tuple, shard_size=shard_size),
        deferred=deferred,
        total_concurrency_weight=total_weight,
        total_cost_units=total_cost,
    )


async def _execute_admitted_wave(
    *,
    plan: ParallelMissionPlan,
    wave: SwarmWave,
    lane_bindings: Mapping[str, ParallelLaneBindings],
    max_transitions_per_lane: int,
) -> SwarmExecutionRound:
    missing_bindings = set(wave.selected_lane_ids) - set(lane_bindings)
    if missing_bindings:
        raise ValueError(
            "swarm_selected_lane_binding_missing:" + ",".join(sorted(missing_bindings))
        )
    if not wave.shards:
        return SwarmExecutionRound(wave=wave, shard_rounds=(), results=())

    lane_map = {item.lane_id: item for item in plan.lanes}

    async def run_shard(shard: SwarmShard) -> ParallelMissionRound:
        lane_ids = tuple(item.lane_id for item in shard.assignments)
        lanes = tuple(lane_map[lane_id] for lane_id in lane_ids)
        shard_plan = ParallelMissionPlan(
            objective_ref=plan.objective_ref,
            tenant_id=plan.tenant_id,
            lanes=lanes,
            max_parallel_lanes=len(lanes),
        )
        shard_bindings = {lane_id: lane_bindings[lane_id] for lane_id in lane_ids}
        return await execute_parallel_mission_round(
            plan=shard_plan,
            bindings=shard_bindings,
            max_transitions_per_lane=max_transitions_per_lane,
        )

    shard_rounds = tuple(await asyncio.gather(*(run_shard(item) for item in wave.shards)))
    selected_set = set(wave.selected_lane_ids)
    results = tuple(
        result
        for shard_round in shard_rounds
        for result in shard_round.results
        if result.lane_id in selected_set
    )
    result_map = {item.lane_id: item for item in results}
    ordered_results = tuple(result_map[lane_id] for lane_id in wave.selected_lane_ids)
    return SwarmExecutionRound(
        wave=wave,
        shard_rounds=shard_rounds,
        results=ordered_results,
    )


async def execute_swarm_round(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    requirements: Mapping[str, SwarmLaneRequirement],
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    bindings: Mapping[str, ParallelLaneBindings],
    now: datetime,
    max_transitions_per_lane: int = 100,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
) -> SwarmExecutionRound:
    """Compatibility path using lane-bound runtimes after global swarm admission."""

    wave = schedule_swarm_wave(
        plan=plan,
        profiles=profiles,
        requirements=requirements,
        registry=registry,
        policy=policy,
        now=now,
        routing_preferences=routing_preferences,
    )
    return await _execute_admitted_wave(
        plan=plan,
        wave=wave,
        lane_bindings=bindings,
        max_transitions_per_lane=max_transitions_per_lane,
    )


async def execute_worker_bound_swarm_round(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    requirements: Mapping[str, SwarmLaneRequirement],
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    worker_bindings: Mapping[str, SwarmWorkerRuntimeBinding],
    now: datetime,
    max_transitions_per_lane: int = 100,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
) -> SwarmExecutionRound:
    """Resolve the actual mission runtime from each globally assigned worker id."""

    wave = schedule_swarm_wave(
        plan=plan,
        profiles=profiles,
        requirements=requirements,
        registry=registry,
        policy=policy,
        now=now,
        routing_preferences=routing_preferences,
    )
    assignment_map = {item.lane_id: item for item in wave.assignments}
    lane_map = {item.lane_id: item for item in plan.lanes}
    required_workers = {item.worker_id for item in wave.assignments}
    missing_workers = required_workers - set(worker_bindings)
    if missing_workers:
        raise ValueError(
            "swarm_worker_runtime_binding_missing:" + ",".join(sorted(missing_workers))
        )

    lane_bindings: dict[str, ParallelLaneBindings] = {}
    for lane_id in wave.selected_lane_ids:
        assignment = assignment_map[lane_id]
        runtime = worker_bindings[assignment.worker_id]
        if runtime.worker_id != assignment.worker_id:
            raise ValueError("swarm_worker_runtime_binding_identity_mismatch")
        lane_bindings[lane_id] = runtime.resolve_lane_binding(lane_map[lane_id])

    return await _execute_admitted_wave(
        plan=plan,
        wave=wave,
        lane_bindings=lane_bindings,
        max_transitions_per_lane=max_transitions_per_lane,
    )
