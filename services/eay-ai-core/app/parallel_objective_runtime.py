"""Durable multi-round objective execution for Jarvis parallel missions.

One scheduled parallel round is not enough for a long-horizon objective: a lane
may be safely deferred because another lane currently owns a conflicting write
resource, then become runnable after the first lane completes. This layer carries
forward only the canonical MissionCheckpoint returned by mission execution and
re-schedules the updated plan.

The runtime is bounded and fail-closed:
- no checkpoint-sequence progress => stop instead of spinning;
- ambiguous/failed mission checkpoints stop the objective;
- overload or truth-gated empty waves surface blockers rather than busy-looping;
- round budget exhaustion is explicit;
- scheduling/execution still never grants shared business authority.

Round history preserves transient deferrals. Final ``blockers`` contains only
unresolved reasons from the stopping round so a conflict resolved in a later
round is not misreported as an active blocker.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelMissionLane,
    ParallelMissionPlan,
)
from .parallel_mission_scheduler import (
    ParallelLaneSchedulingProfile,
    ParallelSchedulingPolicy,
    ScheduledParallelExecutionRound,
    execute_scheduled_parallel_round,
)

PARALLEL_OBJECTIVE_RUNTIME_CONTRACT = "eay-parallel-objective-runtime-v1"


class ParallelObjectiveStatus(str, Enum):
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    FAILED = "failed"
    HALTED = "halted"
    ROUND_BUDGET_EXHAUSTED = "round_budget_exhausted"


class ParallelObjectiveExecution(BaseModel):
    contract: str = PARALLEL_OBJECTIVE_RUNTIME_CONTRACT
    objective_ref: str
    tenant_id: str
    status: ParallelObjectiveStatus
    final_plan: ParallelMissionPlan
    rounds: tuple[ScheduledParallelExecutionRound, ...]
    total_transitions_executed: int = Field(ge=0)
    blockers: tuple[str, ...] = ()
    shared_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def result_is_bound_and_non_authoritative(self) -> "ParallelObjectiveExecution":
        if self.shared_execution_authority_granted:
            raise ValueError("parallel_objective_never_grants_shared_execution_authority")
        if self.final_plan.objective_ref != self.objective_ref:
            raise ValueError("parallel_objective_final_plan_objective_mismatch")
        if self.final_plan.tenant_id != self.tenant_id:
            raise ValueError("parallel_objective_final_plan_tenant_mismatch")
        return self


def _terminal_status(plan: ParallelMissionPlan) -> ParallelObjectiveStatus | None:
    statuses = {lane.checkpoint.status for lane in plan.lanes}
    if statuses and statuses == {MissionStatus.COMPLETED}:
        return ParallelObjectiveStatus.COMPLETED
    if MissionStatus.HALTED in statuses:
        return ParallelObjectiveStatus.HALTED
    if MissionStatus.FAILED in statuses:
        return ParallelObjectiveStatus.FAILED
    return None


def _apply_round_checkpoints(
    *,
    plan: ParallelMissionPlan,
    result: ScheduledParallelExecutionRound,
) -> ParallelMissionPlan:
    if result.schedule.objective_ref != plan.objective_ref:
        raise ValueError("parallel_objective_round_objective_mismatch")
    if result.schedule.tenant_id != plan.tenant_id:
        raise ValueError("parallel_objective_round_tenant_mismatch")
    if result.execution is None:
        return plan

    execution_map = {item.lane_id: item for item in result.execution.results}
    updated_lanes: list[ParallelMissionLane] = []
    for lane in plan.lanes:
        lane_result = execution_map.get(lane.lane_id)
        if lane_result is None or lane_result.summary is None:
            updated_lanes.append(lane)
            continue

        checkpoint = lane_result.summary.checkpoint
        if checkpoint.mission_id != lane.definition.mission_id:
            raise ValueError("parallel_objective_checkpoint_mission_mismatch")
        if checkpoint.tenant_id != lane.definition.tenant_id:
            raise ValueError("parallel_objective_checkpoint_tenant_mismatch")
        if checkpoint.definition_fingerprint != lane.definition.fingerprint():
            raise ValueError("parallel_objective_checkpoint_definition_drift")
        if checkpoint.sequence < lane.checkpoint.sequence:
            raise ValueError("parallel_objective_checkpoint_sequence_regression")
        updated_lanes.append(lane.model_copy(update={"checkpoint": checkpoint}))

    return plan.model_copy(update={"lanes": tuple(updated_lanes)})


def _round_transition_count(result: ScheduledParallelExecutionRound) -> int:
    if result.execution is None:
        return 0
    return sum(
        item.summary.transitions_executed
        for item in result.execution.results
        if item.summary is not None
    )


def _round_blockers(result: ScheduledParallelExecutionRound) -> tuple[str, ...]:
    blockers: list[str] = []
    for lane_id, reasons in result.schedule.deferred.items():
        blockers.extend(f"{reason}:{lane_id}" for reason in reasons)
    if result.execution is not None:
        for item in result.execution.results:
            blockers.extend(f"{reason}:{item.lane_id}" for reason in item.blockers)
    return tuple(dict.fromkeys(blockers))


async def execute_parallel_objective_until_stable(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    policy: ParallelSchedulingPolicy,
    bindings: Mapping[str, ParallelLaneBindings],
    now: datetime,
    max_rounds: int = 16,
    max_transitions_per_lane: int = 100,
) -> ParallelObjectiveExecution:
    """Advance a parallel objective until terminal, blocked or round-bounded."""

    if max_rounds < 1:
        raise ValueError("parallel_objective_max_rounds_must_be_positive")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("parallel_objective_now_requires_timezone")

    current = plan
    rounds: list[ScheduledParallelExecutionRound] = []
    total_transitions = 0
    last_round_blockers: tuple[str, ...] = ()

    terminal = _terminal_status(current)
    if terminal is not None:
        return ParallelObjectiveExecution(
            objective_ref=current.objective_ref,
            tenant_id=current.tenant_id,
            status=terminal,
            final_plan=current,
            rounds=(),
            total_transitions_executed=0,
        )

    for _ in range(max_rounds):
        before_sequences = {
            lane.lane_id: lane.checkpoint.sequence for lane in current.lanes
        }
        round_result = await execute_scheduled_parallel_round(
            plan=current,
            profiles=profiles,
            policy=policy,
            bindings=bindings,
            now=now,
            max_transitions_per_lane=max_transitions_per_lane,
        )
        rounds.append(round_result)
        last_round_blockers = _round_blockers(round_result)
        transitions = _round_transition_count(round_result)
        total_transitions += transitions
        current = _apply_round_checkpoints(plan=current, result=round_result)

        terminal = _terminal_status(current)
        if terminal is not None:
            unresolved = () if terminal is ParallelObjectiveStatus.COMPLETED else last_round_blockers
            return ParallelObjectiveExecution(
                objective_ref=current.objective_ref,
                tenant_id=current.tenant_id,
                status=terminal,
                final_plan=current,
                rounds=tuple(rounds),
                total_transitions_executed=total_transitions,
                blockers=unresolved,
            )

        after_sequences = {
            lane.lane_id: lane.checkpoint.sequence for lane in current.lanes
        }
        sequence_progress = any(
            after_sequences[lane_id] > sequence
            for lane_id, sequence in before_sequences.items()
        )
        if transitions == 0 or not sequence_progress:
            return ParallelObjectiveExecution(
                objective_ref=current.objective_ref,
                tenant_id=current.tenant_id,
                status=ParallelObjectiveStatus.BLOCKED,
                final_plan=current,
                rounds=tuple(rounds),
                total_transitions_executed=total_transitions,
                blockers=tuple(
                    dict.fromkeys((*last_round_blockers, "parallel_objective_no_progress"))
                ),
            )

    return ParallelObjectiveExecution(
        objective_ref=current.objective_ref,
        tenant_id=current.tenant_id,
        status=ParallelObjectiveStatus.ROUND_BUDGET_EXHAUSTED,
        final_plan=current,
        rounds=tuple(rounds),
        total_transitions_executed=total_transitions,
        blockers=tuple(
            dict.fromkeys(
                (*last_round_blockers, "parallel_objective_round_budget_exhausted")
            )
        ),
    )
