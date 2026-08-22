"""Durable multi-round objective execution across a worker-bound Jarvis swarm.

Each round performs global swarm admission, executes worker-bound shards through the
canonical mission runtime, carries forward only validated MissionCheckpoints, degrades
unhealthy workers, and re-schedules remaining work. Resolved deferrals stay in round
history; final blockers contain only unresolved stopping reasons.

A worker assignment is a bounded lease. By default one worker may advance a lane by
one durable transition before control returns to checkpoint/health/scheduling. This
prevents one unhealthy runtime from consuming a mission retry budget before the swarm
can quarantine it or route the same durable lane to another worker.

Evidence-based routing preferences may guide worker selection inside the already
eligible worker set. Health degradation always wins: a preferred worker that becomes
draining or suspended is excluded by canonical eligibility in the next round.

The runtime is bounded and fail-closed. It never re-enables quarantined workers,
never grants shared execution authority, and never replays an ambiguous side effect.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from .parallel_mission_scheduler import ParallelLaneSchedulingProfile
from .swarm_parallel_runtime import (
    SwarmExecutionPolicy,
    SwarmExecutionRound,
    SwarmWorkerRuntimeBinding,
    execute_worker_bound_swarm_round,
)
from .swarm_worker_health import (
    SwarmWorkerHealthRecord,
    WorkerHealthPolicy,
    health_adjusted_swarm_policy,
    update_swarm_worker_health,
    worker_health_observations_from_round,
)
from .swarm_worker_registry import SwarmLaneRequirement, SwarmWorkerRegistry
from .worker_task_routing import WorkerTaskRoutingPreference

SWARM_OBJECTIVE_RUNTIME_CONTRACT = "eay-swarm-objective-runtime-v1"


class SwarmObjectiveStatus(str, Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"
    ROUND_BUDGET_EXHAUSTED = "round_budget_exhausted"


class SwarmObjectiveExecution(BaseModel):
    contract: str = SWARM_OBJECTIVE_RUNTIME_CONTRACT
    objective_ref: str
    tenant_id: str
    status: SwarmObjectiveStatus
    final_plan: ParallelMissionPlan
    final_registry: SwarmWorkerRegistry
    health_records: tuple[SwarmWorkerHealthRecord, ...]
    rounds: tuple[SwarmExecutionRound, ...]
    total_transitions_executed: int = Field(ge=0)
    blockers: tuple[str, ...] = ()
    shared_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_is_bound_and_non_authoritative(self) -> "SwarmObjectiveExecution":
        if self.shared_execution_authority_granted:
            raise ValueError("swarm_objective_never_grants_shared_execution_authority")
        if self.final_plan.objective_ref != self.objective_ref:
            raise ValueError("swarm_objective_final_plan_objective_mismatch")
        if self.final_plan.tenant_id != self.tenant_id:
            raise ValueError("swarm_objective_final_plan_tenant_mismatch")
        if self.final_registry.tenant_id != self.tenant_id:
            raise ValueError("swarm_objective_final_registry_tenant_mismatch")
        return self


def _terminal_status(plan: ParallelMissionPlan) -> SwarmObjectiveStatus | None:
    statuses = {lane.checkpoint.status for lane in plan.lanes}
    if statuses and statuses == {MissionStatus.COMPLETED}:
        return SwarmObjectiveStatus.COMPLETED
    if MissionStatus.HALTED in statuses:
        return SwarmObjectiveStatus.HALTED
    if MissionStatus.FAILED in statuses:
        return SwarmObjectiveStatus.FAILED
    return None


def _apply_round_checkpoints(
    *,
    plan: ParallelMissionPlan,
    execution: SwarmExecutionRound,
) -> ParallelMissionPlan:
    if execution.wave.objective_ref != plan.objective_ref:
        raise ValueError("swarm_objective_round_objective_mismatch")
    if execution.wave.tenant_id != plan.tenant_id:
        raise ValueError("swarm_objective_round_tenant_mismatch")

    result_map = {item.lane_id: item for item in execution.results}
    updated_lanes: list[ParallelMissionLane] = []
    for lane in plan.lanes:
        result = result_map.get(lane.lane_id)
        if result is None or result.summary is None:
            updated_lanes.append(lane)
            continue
        checkpoint = result.summary.checkpoint
        if checkpoint.mission_id != lane.definition.mission_id:
            raise ValueError("swarm_objective_checkpoint_mission_mismatch")
        if checkpoint.tenant_id != lane.definition.tenant_id:
            raise ValueError("swarm_objective_checkpoint_tenant_mismatch")
        if checkpoint.definition_fingerprint != lane.definition.fingerprint():
            raise ValueError("swarm_objective_checkpoint_definition_drift")
        if checkpoint.sequence < lane.checkpoint.sequence:
            raise ValueError("swarm_objective_checkpoint_sequence_regression")
        updated_lanes.append(lane.model_copy(update={"checkpoint": checkpoint}))
    return plan.model_copy(update={"lanes": tuple(updated_lanes)})


def _round_transition_count(execution: SwarmExecutionRound) -> int:
    return sum(
        result.summary.transitions_executed
        for result in execution.results
        if result.summary is not None
    )


def _round_blockers(execution: SwarmExecutionRound) -> tuple[str, ...]:
    blockers: list[str] = []
    for lane_id, reasons in execution.wave.deferred.items():
        if reasons == ("parallel_lane_terminal",):
            continue
        blockers.extend(f"{reason}:{lane_id}" for reason in reasons)
    for result in execution.results:
        blockers.extend(f"{reason}:{result.lane_id}" for reason in result.blockers)
    return tuple(dict.fromkeys(blockers))


def _record_map(
    records: tuple[SwarmWorkerHealthRecord, ...],
) -> dict[str, SwarmWorkerHealthRecord]:
    return {item.worker_id: item for item in records}


async def execute_swarm_objective_until_stable(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    requirements: Mapping[str, SwarmLaneRequirement],
    registry: SwarmWorkerRegistry,
    policy: SwarmExecutionPolicy,
    worker_bindings: Mapping[str, SwarmWorkerRuntimeBinding],
    now: datetime,
    health_policy: WorkerHealthPolicy | None = None,
    existing_health_records: Mapping[str, SwarmWorkerHealthRecord] | None = None,
    routing_preferences: Mapping[str, WorkerTaskRoutingPreference] | None = None,
    max_rounds: int = 16,
    max_transitions_per_worker_lease: int = 1,
) -> SwarmObjectiveExecution:
    """Advance a large worker-bound objective until terminal, blocked or bounded."""

    if max_rounds < 1:
        raise ValueError("swarm_objective_max_rounds_must_be_positive")
    if max_transitions_per_worker_lease < 1:
        raise ValueError("swarm_objective_worker_lease_transition_budget_must_be_positive")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("swarm_objective_now_requires_timezone")
    if registry.tenant_id != plan.tenant_id:
        raise ValueError("swarm_objective_registry_tenant_mismatch")

    current_plan = plan
    current_registry = registry
    current_policy = policy
    current_records = dict(existing_health_records or {})
    health_rules = health_policy or WorkerHealthPolicy()
    rounds: list[SwarmExecutionRound] = []
    total_transitions = 0
    last_round_blockers: tuple[str, ...] = ()

    terminal = _terminal_status(current_plan)
    if terminal is not None:
        initial_health = update_swarm_worker_health(
            registry=current_registry,
            existing_records=current_records,
            observations=(),
            policy=health_rules,
        )
        return SwarmObjectiveExecution(
            objective_ref=current_plan.objective_ref,
            tenant_id=current_plan.tenant_id,
            status=terminal,
            final_plan=current_plan,
            final_registry=initial_health.registry,
            health_records=initial_health.records,
            rounds=(),
            total_transitions_executed=0,
        )

    for _ in range(max_rounds):
        before_sequences = {
            lane.lane_id: lane.checkpoint.sequence for lane in current_plan.lanes
        }
        round_result = await execute_worker_bound_swarm_round(
            plan=current_plan,
            profiles=profiles,
            requirements=requirements,
            registry=current_registry,
            policy=current_policy,
            worker_bindings=worker_bindings,
            now=now,
            max_transitions_per_lane=max_transitions_per_worker_lease,
            routing_preferences=routing_preferences,
        )
        rounds.append(round_result)
        last_round_blockers = _round_blockers(round_result)
        transitions = _round_transition_count(round_result)
        total_transitions += transitions
        current_plan = _apply_round_checkpoints(
            plan=current_plan,
            execution=round_result,
        )

        observations = worker_health_observations_from_round(
            execution=round_result,
            observed_at=now,
        )
        health_update = update_swarm_worker_health(
            registry=current_registry,
            existing_records=current_records,
            observations=observations,
            policy=health_rules,
        )
        current_registry = health_update.registry
        current_records = _record_map(health_update.records)
        current_policy = health_adjusted_swarm_policy(
            policy=current_policy,
            health=health_update,
        )

        terminal = _terminal_status(current_plan)
        if terminal is not None:
            unresolved = () if terminal is SwarmObjectiveStatus.COMPLETED else last_round_blockers
            return SwarmObjectiveExecution(
                objective_ref=current_plan.objective_ref,
                tenant_id=current_plan.tenant_id,
                status=terminal,
                final_plan=current_plan,
                final_registry=current_registry,
                health_records=tuple(current_records[item.worker_id] for item in current_registry.workers),
                rounds=tuple(rounds),
                total_transitions_executed=total_transitions,
                blockers=unresolved,
            )

        after_sequences = {
            lane.lane_id: lane.checkpoint.sequence for lane in current_plan.lanes
        }
        sequence_progress = any(
            after_sequences[lane_id] > sequence
            for lane_id, sequence in before_sequences.items()
        )
        if transitions == 0 or not sequence_progress:
            return SwarmObjectiveExecution(
                objective_ref=current_plan.objective_ref,
                tenant_id=current_plan.tenant_id,
                status=SwarmObjectiveStatus.BLOCKED,
                final_plan=current_plan,
                final_registry=current_registry,
                health_records=tuple(current_records[item.worker_id] for item in current_registry.workers),
                rounds=tuple(rounds),
                total_transitions_executed=total_transitions,
                blockers=tuple(
                    dict.fromkeys((*last_round_blockers, "swarm_objective_no_progress"))
                ),
            )

    return SwarmObjectiveExecution(
        objective_ref=current_plan.objective_ref,
        tenant_id=current_plan.tenant_id,
        status=SwarmObjectiveStatus.ROUND_BUDGET_EXHAUSTED,
        final_plan=current_plan,
        final_registry=current_registry,
        health_records=tuple(current_records[item.worker_id] for item in current_registry.workers),
        rounds=tuple(rounds),
        total_transitions_executed=total_transitions,
        blockers=tuple(
            dict.fromkeys(
                (*last_round_blockers, "swarm_objective_round_budget_exhausted")
            )
        ),
    )
