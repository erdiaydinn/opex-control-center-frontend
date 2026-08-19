from datetime import datetime, timezone

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import (
    ParallelMissionLane,
    ParallelMissionPlan,
    parallel_lane_conflict_blockers,
    select_parallel_wave,
)
from app.parallel_mission_scheduler import (
    LaneSchedulingClass,
    ParallelLaneSchedulingProfile,
    ParallelSchedulingPolicy,
    schedule_parallel_wave,
)

NOW = datetime(2026, 8, 19, 5, 45, tzinfo=timezone.utc)


def _lane(
    *,
    lane_id: str,
    priority: int,
    side_effect: bool,
    resource_ref: str,
    idempotency_key: str | None = None,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description=f"advance {lane_id}",
        side_effect=side_effect,
        idempotency_key=(
            idempotency_key
            if side_effect
            else None
        ),
        effect_verifier_ref=("effect://authoritative" if side_effect else None),
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step-1",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=f"capability://{lane_id}",
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        priority=priority,
        exclusive_resource_refs=(resource_ref,),
    )


def _profile(lane: ParallelMissionLane) -> ParallelLaneSchedulingProfile:
    has_write = lane.has_pending_side_effect()
    return ParallelLaneSchedulingProfile(
        lane_id=lane.lane_id,
        scheduling_class=(
            LaneSchedulingClass.EXECUTION
            if has_write
            else LaneSchedulingClass.COMPANY_READ
        ),
        shedable=not has_write,
        preemptible=not has_write,
    )


def _assert_same_deferral(
    *,
    first: ParallelMissionLane,
    second: ParallelMissionLane,
    expected: tuple[str, ...],
) -> None:
    plan = ParallelMissionPlan(
        objective_ref="objective://conflict-consistency",
        tenant_id="YS_TR",
        lanes=(first, second),
        max_parallel_lanes=2,
    )
    selected, orchestrator_deferred = select_parallel_wave(plan)
    scheduled = schedule_parallel_wave(
        plan=plan,
        profiles={first.lane_id: _profile(first), second.lane_id: _profile(second)},
        policy=ParallelSchedulingPolicy(max_concurrency_weight=4),
        now=NOW,
    )

    assert selected == (first.lane_id,)
    assert scheduled.selected_lane_ids == (first.lane_id,)
    assert parallel_lane_conflict_blockers(second, (first,)) == expected
    assert orchestrator_deferred[second.lane_id] == expected
    assert scheduled.deferred[second.lane_id] == expected


def test_scheduler_and_orchestrator_share_resource_conflict_semantics():
    first = _lane(
        lane_id="inventory-write",
        priority=90,
        side_effect=True,
        resource_ref="store://fulya/inventory",
        idempotency_key="idem-inventory-write-0123456789",
    )
    second = _lane(
        lane_id="replenishment-write",
        priority=80,
        side_effect=True,
        resource_ref="store://fulya/inventory",
        idempotency_key="idem-replenishment-write-0123456789",
    )
    _assert_same_deferral(
        first=first,
        second=second,
        expected=("parallel_resource_conflict",),
    )


def test_scheduler_and_orchestrator_share_idempotency_conflict_semantics():
    shared_key = "idem-shared-side-effect-0123456789"
    first = _lane(
        lane_id="write-a",
        priority=90,
        side_effect=True,
        resource_ref="resource://a",
        idempotency_key=shared_key,
    )
    second = _lane(
        lane_id="write-b",
        priority=80,
        side_effect=True,
        resource_ref="resource://b",
        idempotency_key=shared_key,
    )
    _assert_same_deferral(
        first=first,
        second=second,
        expected=("parallel_idempotency_conflict",),
    )


def test_shared_read_resource_has_no_false_conflict_in_either_path():
    first = _lane(
        lane_id="read-a",
        priority=90,
        side_effect=False,
        resource_ref="store://fulya/inventory",
    )
    second = _lane(
        lane_id="read-b",
        priority=80,
        side_effect=False,
        resource_ref="store://fulya/inventory",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://concurrent-reads",
        tenant_id="YS_TR",
        lanes=(first, second),
        max_parallel_lanes=2,
    )
    selected, deferred = select_parallel_wave(plan)
    scheduled = schedule_parallel_wave(
        plan=plan,
        profiles={first.lane_id: _profile(first), second.lane_id: _profile(second)},
        policy=ParallelSchedulingPolicy(max_concurrency_weight=4),
        now=NOW,
    )

    assert parallel_lane_conflict_blockers(second, (first,)) == ()
    assert selected == (first.lane_id, second.lane_id)
    assert deferred == {}
    assert scheduled.selected_lane_ids == (first.lane_id, second.lane_id)
    assert scheduled.deferred == {}
