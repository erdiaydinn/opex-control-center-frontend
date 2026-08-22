"""Budget- and load-aware scheduling in front of Jarvis parallel missions.

The pure scheduler decides which independent mission lanes are admitted to the
next parallel wave and never grants execution authority. A separate composition
function may execute that admitted wave, but it delegates every selected lane to
the existing parallel mission orchestrator rather than creating a second mission
runtime.

Resource/idempotency conflict rules are imported from the canonical parallel
orchestrator so deadline, cost or overload scheduling cannot silently diverge
from the base mission safety semantics.

Pending side-effect lanes may be deferred before they start, but they may never
be marked shedable or preemptible. This avoids turning load shedding into an
implicit cancellation mechanism for real-world effects with uncertain outcome.
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
    ParallelMissionRound,
    execute_parallel_mission_round,
    parallel_lane_conflict_blockers,
)

PARALLEL_MISSION_SCHEDULER_CONTRACT = "eay-parallel-mission-scheduler-v1"


class LaneSchedulingClass(str, Enum):
    EXECUTION = "execution"
    COMPANY_READ = "company_read"
    INTERACTIVE = "interactive"
    RESEARCH = "research"
    SIMULATION = "simulation"


class ParallelLaneSchedulingProfile(BaseModel):
    lane_id: str = Field(min_length=1)
    scheduling_class: LaneSchedulingClass = LaneSchedulingClass.INTERACTIVE
    deadline_at: datetime | None = None
    estimated_cost_units: int = Field(default=1, ge=1, le=100_000)
    concurrency_weight: int = Field(default=1, ge=1, le=16)
    shedable: bool = True
    preemptible: bool = True

    @model_validator(mode="after")
    def deadline_is_timezone_aware(self) -> "ParallelLaneSchedulingProfile":
        if self.deadline_at is not None and (
            self.deadline_at.tzinfo is None or self.deadline_at.utcoffset() is None
        ):
            raise ValueError("parallel_scheduler_deadline_requires_timezone")
        return self


class ParallelSchedulingPolicy(BaseModel):
    contract: str = PARALLEL_MISSION_SCHEDULER_CONTRACT
    max_concurrency_weight: int = Field(default=4, ge=1, le=64)
    max_round_cost_units: int = Field(default=100, ge=1, le=10_000_000)
    overload_mode: bool = False
    overload_shed_priority_below: int = Field(default=40, ge=0, le=100)


class ScheduledParallelWave(BaseModel):
    contract: str = PARALLEL_MISSION_SCHEDULER_CONTRACT
    objective_ref: str
    tenant_id: str
    selected_lane_ids: tuple[str, ...]
    deferred: dict[str, tuple[str, ...]]
    total_concurrency_weight: int = Field(ge=0)
    total_cost_units: int = Field(ge=0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def wave_is_non_authoritative(self) -> "ScheduledParallelWave":
        if self.execution_authority_granted:
            raise ValueError("parallel_scheduler_never_grants_execution_authority")
        if len(self.selected_lane_ids) != len(set(self.selected_lane_ids)):
            raise ValueError("parallel_scheduler_selected_lanes_must_be_unique")
        return self


class ScheduledParallelExecutionRound(BaseModel):
    contract: str = PARALLEL_MISSION_SCHEDULER_CONTRACT
    schedule: ScheduledParallelWave
    execution: ParallelMissionRound | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def composition_preserves_scheduler_boundary(self) -> "ScheduledParallelExecutionRound":
        if self.execution_authority_granted:
            raise ValueError("scheduled_parallel_execution_never_grants_shared_authority")
        if self.execution is None:
            if self.schedule.selected_lane_ids:
                raise ValueError("scheduled_parallel_execution_missing_for_selected_wave")
            return self
        if self.execution.objective_ref != self.schedule.objective_ref:
            raise ValueError("scheduled_parallel_execution_objective_mismatch")
        if self.execution.tenant_id != self.schedule.tenant_id:
            raise ValueError("scheduled_parallel_execution_tenant_mismatch")
        if set(self.execution.selected_lane_ids) != set(self.schedule.selected_lane_ids):
            raise ValueError("scheduled_parallel_execution_selection_drift")
        if self.execution.shared_execution_authority_granted:
            raise ValueError("scheduled_parallel_execution_shared_authority_forbidden")
        return self


def _terminal(lane: ParallelMissionLane) -> bool:
    return lane.checkpoint.status in {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.HALTED,
    }


def _validate_profile_against_lane(
    *,
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
) -> None:
    if profile.lane_id != lane.lane_id:
        raise ValueError("parallel_scheduler_profile_lane_mismatch")
    if lane.has_pending_side_effect() and profile.shedable:
        raise ValueError("parallel_scheduler_pending_side_effect_cannot_be_shedable")
    if lane.has_pending_side_effect() and profile.preemptible:
        raise ValueError("parallel_scheduler_pending_side_effect_cannot_be_preemptible")


def lane_preemption_allowed(
    *,
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
) -> bool:
    """Return whether a not-yet-completed lane may be safely preempted."""

    _validate_profile_against_lane(lane=lane, profile=profile)
    if lane.has_pending_side_effect():
        return False
    return profile.preemptible


def _ranking_key(
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
) -> tuple[int, float, int, str]:
    # Any explicit deadline outranks undated background work. Among deadlines,
    # earlier is more urgent; priority and lane id keep ordering deterministic.
    if profile.deadline_at is None:
        return (1, float("inf"), -lane.priority, lane.lane_id)
    return (0, profile.deadline_at.timestamp(), -lane.priority, lane.lane_id)


def schedule_parallel_wave(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    policy: ParallelSchedulingPolicy,
    now: datetime,
) -> ScheduledParallelWave:
    """Select one deterministic, safe wave without executing any lane."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("parallel_scheduler_now_requires_timezone")

    lane_map = {lane.lane_id: lane for lane in plan.lanes}
    if set(profiles) != set(lane_map):
        raise ValueError("parallel_scheduler_profiles_must_cover_plan_exactly")
    for lane_id, lane in lane_map.items():
        _validate_profile_against_lane(lane=lane, profile=profiles[lane_id])

    ordered = sorted(
        plan.lanes,
        key=lambda lane: _ranking_key(lane, profiles[lane.lane_id]),
    )
    selected: list[ParallelMissionLane] = []
    deferred: dict[str, tuple[str, ...]] = {}
    total_weight = 0
    total_cost = 0

    for lane in ordered:
        profile = profiles[lane.lane_id]
        if _terminal(lane):
            deferred[lane.lane_id] = ("parallel_lane_terminal",)
            continue

        if (
            policy.overload_mode
            and profile.shedable
            and lane.priority < policy.overload_shed_priority_below
        ):
            deferred[lane.lane_id] = ("parallel_overload_shed",)
            continue

        if len(selected) >= plan.max_parallel_lanes:
            deferred[lane.lane_id] = ("parallel_capacity_deferred",)
            continue

        conflicts = parallel_lane_conflict_blockers(lane, tuple(selected))
        if conflicts:
            deferred[lane.lane_id] = conflicts
            continue

        if total_weight + profile.concurrency_weight > policy.max_concurrency_weight:
            deferred[lane.lane_id] = ("parallel_weight_capacity_deferred",)
            continue

        if total_cost + profile.estimated_cost_units > policy.max_round_cost_units:
            deferred[lane.lane_id] = (
                "parallel_cost_budget_shed" if profile.shedable else "parallel_cost_budget_deferred",
            )
            continue

        selected.append(lane)
        total_weight += profile.concurrency_weight
        total_cost += profile.estimated_cost_units

    return ScheduledParallelWave(
        objective_ref=plan.objective_ref,
        tenant_id=plan.tenant_id,
        selected_lane_ids=tuple(lane.lane_id for lane in selected),
        deferred=deferred,
        total_concurrency_weight=total_weight,
        total_cost_units=total_cost,
    )


async def execute_scheduled_parallel_round(
    *,
    plan: ParallelMissionPlan,
    profiles: Mapping[str, ParallelLaneSchedulingProfile],
    policy: ParallelSchedulingPolicy,
    bindings: Mapping[str, ParallelLaneBindings],
    now: datetime,
    max_transitions_per_lane: int = 100,
) -> ScheduledParallelExecutionRound:
    """Schedule first, then execute only admitted lanes via the canonical runtime."""

    schedule = schedule_parallel_wave(
        plan=plan,
        profiles=profiles,
        policy=policy,
        now=now,
    )
    if not schedule.selected_lane_ids:
        return ScheduledParallelExecutionRound(schedule=schedule)

    lane_map = {lane.lane_id: lane for lane in plan.lanes}
    selected_lanes = tuple(lane_map[lane_id] for lane_id in schedule.selected_lane_ids)
    selected_plan = ParallelMissionPlan(
        objective_ref=plan.objective_ref,
        tenant_id=plan.tenant_id,
        lanes=selected_lanes,
        max_parallel_lanes=len(selected_lanes),
    )
    selected_bindings = {
        lane_id: bindings[lane_id]
        for lane_id in schedule.selected_lane_ids
        if lane_id in bindings
    }
    execution = await execute_parallel_mission_round(
        plan=selected_plan,
        bindings=selected_bindings,
        max_transitions_per_lane=max_transitions_per_lane,
    )
    return ScheduledParallelExecutionRound(
        schedule=schedule,
        execution=execution,
    )
