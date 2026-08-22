from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelMissionLane,
    ParallelMissionPlan,
)
from app.parallel_mission_scheduler import (
    LaneSchedulingClass,
    ParallelLaneSchedulingProfile,
    ParallelSchedulingPolicy,
    execute_scheduled_parallel_round,
)

NOW = datetime(2026, 8, 19, 5, 30, tzinfo=timezone.utc)


class _UnusedGateway:
    pass


def _writer(_receipt: object) -> str:
    return "evidence://reasoning"


def _lane(
    *,
    lane_id: str,
    priority: int,
    side_effect: bool = False,
    resource_ref: str | None = None,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description=f"advance {lane_id}",
        side_effect=side_effect,
        idempotency_key=(f"idem-{lane_id}-0123456789" if side_effect else None),
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
        exclusive_resource_refs=(() if resource_ref is None else (resource_ref,)),
    )


def _binding(lane: ParallelMissionLane, calls: list[str]) -> ParallelLaneBindings:
    capability_ref = lane.specs[0].capability_ref or ""

    async def handler(_definition, step, _state, _idempotency_key):
        calls.append(lane.lane_id)
        return CapabilityExecutionOutcome(
            succeeded=True,
            effect_verified=step.side_effect,
            evidence_refs=(f"evidence://{lane.lane_id}",),
            transaction_ref=(f"transaction://{lane.lane_id}" if step.side_effect else None),
        )

    return ParallelLaneBindings(
        gateway=_UnusedGateway(),  # type: ignore[arg-type]
        reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
        capability_handlers={capability_ref: handler},
    )


@pytest.mark.asyncio
async def test_scheduler_executes_only_admitted_lane_without_requiring_deferred_binding():
    background = _lane(lane_id="background", priority=95)
    urgent = _lane(lane_id="urgent", priority=40)
    plan = ParallelMissionPlan(
        objective_ref="objective://scheduled-execution",
        tenant_id="YS_TR",
        lanes=(background, urgent),
        max_parallel_lanes=2,
    )
    calls: list[str] = []
    result = await execute_scheduled_parallel_round(
        plan=plan,
        profiles={
            "background": ParallelLaneSchedulingProfile(
                lane_id="background",
                scheduling_class=LaneSchedulingClass.RESEARCH,
            ),
            "urgent": ParallelLaneSchedulingProfile(
                lane_id="urgent",
                scheduling_class=LaneSchedulingClass.COMPANY_READ,
                deadline_at=NOW + timedelta(seconds=10),
            ),
        },
        policy=ParallelSchedulingPolicy(max_concurrency_weight=1),
        bindings={"urgent": _binding(urgent, calls)},
        now=NOW,
    )
    assert result.schedule.selected_lane_ids == ("urgent",)
    assert result.schedule.deferred["background"] == ("parallel_weight_capacity_deferred",)
    assert result.execution is not None
    assert result.execution.selected_lane_ids == ("urgent",)
    assert calls == ["urgent"]
    assert result.execution_authority_granted is False


@pytest.mark.asyncio
async def test_overload_can_produce_empty_wave_without_touching_any_runtime_binding():
    first = _lane(lane_id="research-a", priority=10)
    second = _lane(lane_id="research-b", priority=20)
    plan = ParallelMissionPlan(
        objective_ref="objective://shed-all-background",
        tenant_id="YS_TR",
        lanes=(first, second),
    )
    result = await execute_scheduled_parallel_round(
        plan=plan,
        profiles={
            first.lane_id: ParallelLaneSchedulingProfile(
                lane_id=first.lane_id,
                scheduling_class=LaneSchedulingClass.RESEARCH,
            ),
            second.lane_id: ParallelLaneSchedulingProfile(
                lane_id=second.lane_id,
                scheduling_class=LaneSchedulingClass.RESEARCH,
            ),
        },
        policy=ParallelSchedulingPolicy(
            overload_mode=True,
            overload_shed_priority_below=40,
        ),
        bindings={},
        now=NOW,
    )
    assert result.schedule.selected_lane_ids == ()
    assert result.execution is None
    assert set(result.schedule.deferred) == {"research-a", "research-b"}


@pytest.mark.asyncio
async def test_non_shedable_side_effect_lane_executes_through_existing_effect_verifier_path():
    write = _lane(
        lane_id="inventory-write",
        priority=90,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://inventory-write",
        tenant_id="YS_TR",
        lanes=(write,),
    )
    calls: list[str] = []
    result = await execute_scheduled_parallel_round(
        plan=plan,
        profiles={
            write.lane_id: ParallelLaneSchedulingProfile(
                lane_id=write.lane_id,
                scheduling_class=LaneSchedulingClass.EXECUTION,
                shedable=False,
                preemptible=False,
            )
        },
        policy=ParallelSchedulingPolicy(),
        bindings={write.lane_id: _binding(write, calls)},
        now=NOW,
    )
    assert result.execution is not None
    assert result.execution.selected_lane_ids == (write.lane_id,)
    lane_result = result.execution.results[0]
    assert lane_result.summary is not None
    assert lane_result.summary.transitions_executed == 1
    assert calls == [write.lane_id]
