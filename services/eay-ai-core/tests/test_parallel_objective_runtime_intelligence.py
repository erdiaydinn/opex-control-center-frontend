from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelMissionLane,
    ParallelMissionPlan,
)
from app.parallel_mission_scheduler import (
    LaneSchedulingClass,
    ParallelLaneSchedulingProfile,
    ParallelSchedulingPolicy,
)
from app.parallel_objective_runtime import (
    ParallelObjectiveStatus,
    execute_parallel_objective_until_stable,
)

NOW = datetime(2026, 8, 19, 6, 0, tzinfo=timezone.utc)


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
    truth_requirement: str | None = None,
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
        decision_truth_requirement_id=truth_requirement,
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        priority=priority,
        exclusive_resource_refs=(() if resource_ref is None else (resource_ref,)),
    )


def _profile(lane: ParallelMissionLane) -> ParallelLaneSchedulingProfile:
    write = lane.has_pending_side_effect()
    return ParallelLaneSchedulingProfile(
        lane_id=lane.lane_id,
        scheduling_class=(
            LaneSchedulingClass.EXECUTION if write else LaneSchedulingClass.COMPANY_READ
        ),
        shedable=not write,
        preemptible=not write,
    )


def _success_binding(lane: ParallelMissionLane, calls: list[str]) -> ParallelLaneBindings:
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
async def test_conflicting_writes_complete_across_two_durable_rounds_without_replay():
    first = _lane(
        lane_id="inventory-write",
        priority=90,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    second = _lane(
        lane_id="replenishment-write",
        priority=80,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://fulya-inventory",
        tenant_id="YS_TR",
        lanes=(first, second),
        max_parallel_lanes=2,
    )
    calls: list[str] = []
    result = await execute_parallel_objective_until_stable(
        plan=plan,
        profiles={first.lane_id: _profile(first), second.lane_id: _profile(second)},
        policy=ParallelSchedulingPolicy(max_concurrency_weight=4),
        bindings={
            first.lane_id: _success_binding(first, calls),
            second.lane_id: _success_binding(second, calls),
        },
        now=NOW,
    )

    assert result.status is ParallelObjectiveStatus.COMPLETED
    assert len(result.rounds) == 2
    assert result.total_transitions_executed == 2
    assert calls == ["inventory-write", "replenishment-write"]
    assert result.blockers == ()
    assert all(
        lane.checkpoint.status is MissionStatus.COMPLETED
        for lane in result.final_plan.lanes
    )
    assert [lane.checkpoint.sequence for lane in result.final_plan.lanes] == [1, 1]


@pytest.mark.asyncio
async def test_missing_live_truth_stops_objective_after_one_no_progress_round():
    lane = _lane(
        lane_id="company-read",
        priority=90,
        truth_requirement="truth.orders.v2",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://truth-gated",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    calls: list[str] = []
    result = await execute_parallel_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        policy=ParallelSchedulingPolicy(),
        bindings={lane.lane_id: _success_binding(lane, calls)},
        now=NOW,
    )

    assert result.status is ParallelObjectiveStatus.BLOCKED
    assert len(result.rounds) == 1
    assert result.total_transitions_executed == 0
    assert calls == []
    assert "live_company_truth_receipt_missing:step-1:company-read" in result.blockers
    assert "parallel_objective_no_progress" in result.blockers
    assert result.final_plan.lanes[0].checkpoint.sequence == 0


@pytest.mark.asyncio
async def test_ambiguous_side_effect_halts_objective_and_is_not_replayed():
    lane = _lane(
        lane_id="inventory-write",
        priority=90,
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    capability_ref = lane.specs[0].capability_ref or ""
    calls: list[str] = []

    async def ambiguous_handler(_definition, _step, _state, _idempotency_key):
        calls.append("inventory-write")
        return CapabilityExecutionOutcome(
            succeeded=False,
            ambiguous_outcome=True,
            evidence_refs=("evidence://ambiguous-write",),
            transaction_ref="transaction://uncertain-1",
        )

    binding = ParallelLaneBindings(
        gateway=_UnusedGateway(),  # type: ignore[arg-type]
        reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
        capability_handlers={capability_ref: ambiguous_handler},
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://ambiguous-write",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    result = await execute_parallel_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        policy=ParallelSchedulingPolicy(),
        bindings={lane.lane_id: binding},
        now=NOW,
        max_rounds=5,
    )

    assert result.status is ParallelObjectiveStatus.HALTED
    assert len(result.rounds) == 1
    assert calls == ["inventory-write"]
    assert result.final_plan.lanes[0].checkpoint.status is MissionStatus.HALTED
    assert result.final_plan.lanes[0].checkpoint.sequence == 1
    assert any("capability_outcome_ambiguous" in blocker for blocker in result.blockers)


@pytest.mark.asyncio
async def test_round_budget_exhaustion_is_explicit_after_real_progress():
    first = _lane(
        lane_id="write-a",
        priority=90,
        side_effect=True,
        resource_ref="resource://shared",
    )
    second = _lane(
        lane_id="write-b",
        priority=80,
        side_effect=True,
        resource_ref="resource://shared",
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://bounded",
        tenant_id="YS_TR",
        lanes=(first, second),
        max_parallel_lanes=2,
    )
    calls: list[str] = []
    result = await execute_parallel_objective_until_stable(
        plan=plan,
        profiles={first.lane_id: _profile(first), second.lane_id: _profile(second)},
        policy=ParallelSchedulingPolicy(),
        bindings={
            first.lane_id: _success_binding(first, calls),
            second.lane_id: _success_binding(second, calls),
        },
        now=NOW,
        max_rounds=1,
    )

    assert result.status is ParallelObjectiveStatus.ROUND_BUDGET_EXHAUSTED
    assert result.total_transitions_executed == 1
    assert calls == ["write-a"]
    assert "parallel_resource_conflict:write-b" in result.blockers
    assert "parallel_objective_round_budget_exhausted" in result.blockers
