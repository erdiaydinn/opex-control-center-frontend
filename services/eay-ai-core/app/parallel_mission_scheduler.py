"""Budget- and load-aware scheduling in front of Jarvis parallel missions.

The scheduler decides which independent mission lanes are admitted to the next
parallel wave. It does not execute missions and never grants execution authority.
Resource/idempotency conflict rules remain aligned with the parallel mission
orchestrator, while deadline, concurrency-weight, cost-budget and overload
shedding decisions stay explicit and deterministic.

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
from .parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan

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


def _conflict_blockers(
    lane: ParallelMissionLane,
    selected: tuple[ParallelMissionLane, ...],
) -> tuple[str, ...]:
    lane_resources = set(lane.exclusive_resource_refs)
    lane_keys = set(lane.pending_idempotency_keys())
    blockers: list[str] = []
    for other in selected:
        shared_resources = lane_resources & set(other.exclusive_resource_refs)
        if shared_resources and (lane.has_pending_side_effect() or other.has_pending_side_effect()):
            blockers.append("parallel_resource_conflict")
        if lane_keys & set(other.pending_idempotency_keys()):
            blockers.append("parallel_idempotency_conflict")
    return tuple(dict.fromkeys(blockers))


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

        conflicts = _conflict_blockers(lane, tuple(selected))
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
