from __future__ import annotations

from datetime import datetime, timezone

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
)
from app.swarm_parallel_runtime import (
    SwarmExecutionPolicy,
    execute_swarm_round,
    schedule_swarm_wave,
)
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    SwarmWorkerState,
)

NOW = datetime(2026, 8, 19, 6, 45, tzinfo=timezone.utc)


class _UnusedGateway:
    pass


def _writer(_receipt: object) -> str:
    return "evidence://reasoning"


def _lane(
    lane_id: str,
    *,
    side_effect: bool = False,
    resource_ref: str | None = None,
    priority: int = 50,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description=f"advance {lane_id}",
        side_effect=side_effect,
        idempotency_key=(f"idem-{lane_id}-0000000001" if side_effect else None),
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
        capability_ref="capability://swarm.read" if not side_effect else "capability://swarm.write",
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
            LaneSchedulingClass.EXECUTION if write else LaneSchedulingClass.RESEARCH
        ),
        estimated_cost_units=1,
        concurrency_weight=1,
        shedable=not write,
        preemptible=not write,
    )


def _requirement(lane: ParallelMissionLane) -> SwarmLaneRequirement:
    return SwarmLaneRequirement(
        lane_id=lane.lane_id,
        required_worker_classes=(
            (SwarmWorkerClass.EXECUTION,)
            if lane.has_pending_side_effect()
            else (SwarmWorkerClass.RESEARCH,)
        ),
    )


def _registry(*, count: int = 64) -> SwarmWorkerRegistry:
    workers = []
    for index in range(count):
        is_execution = index % 4 == 0
        workers.append(
            SwarmWorkerDescriptor(
                worker_id=f"worker-{index:03d}",
                tenant_id="YS_TR",
                worker_class=(
                    SwarmWorkerClass.EXECUTION
                    if is_execution
                    else SwarmWorkerClass.RESEARCH
                ),
                supported_scheduling_classes=(
                    (LaneSchedulingClass.EXECUTION,)
                    if is_execution
                    else (LaneSchedulingClass.RESEARCH,)
                ),
                capability_refs=(
                    ("capability://swarm.write",)
                    if is_execution
                    else ("capability://swarm.read",)
                ),
            )
        )
    return SwarmWorkerRegistry(tenant_id="YS_TR", workers=tuple(workers))


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
async def test_swarm_executes_forty_logical_workers_across_parallel_shards():
    lanes = tuple(_lane(f"research-{index:03d}") for index in range(40))
    plan = ParallelMissionPlan(
        objective_ref="objective://forty-worker-swarm",
        tenant_id="YS_TR",
        lanes=lanes,
        max_parallel_lanes=4,
    )
    calls: list[str] = []
    result = await execute_swarm_round(
        plan=plan,
        profiles={lane.lane_id: _profile(lane) for lane in lanes},
        requirements={lane.lane_id: _requirement(lane) for lane in lanes},
        registry=_registry(count=64),
        policy=SwarmExecutionPolicy(max_active_workers=40, shard_size=16),
        bindings={lane.lane_id: _binding(lane, calls) for lane in lanes},
        now=NOW,
    )

    assert len(result.wave.selected_lane_ids) == 40
    assert len(result.wave.shards) == 10
    assert all(len(shard.assignments) == 4 for shard in result.wave.shards)
    assert len(result.shard_rounds) == 10
    assert set(calls) == {lane.lane_id for lane in lanes}
    assert len(result.results) == 40
    assert result.execution_authority_granted is False


def test_global_swarm_admission_prevents_cross_shard_write_conflict():
    first = _lane(
        "write-a",
        side_effect=True,
        resource_ref="store://fulya/inventory",
        priority=90,
    )
    second = _lane(
        "write-b",
        side_effect=True,
        resource_ref="store://fulya/inventory",
        priority=80,
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://conflict",
        tenant_id="YS_TR",
        lanes=(first, second),
        max_parallel_lanes=1,
    )
    wave = schedule_swarm_wave(
        plan=plan,
        profiles={first.lane_id: _profile(first), second.lane_id: _profile(second)},
        requirements={
            first.lane_id: _requirement(first),
            second.lane_id: _requirement(second),
        },
        registry=_registry(count=8),
        policy=SwarmExecutionPolicy(max_active_workers=8),
        now=NOW,
    )
    assert wave.selected_lane_ids == ("write-a",)
    assert wave.deferred["write-b"] == ("parallel_resource_conflict",)


def test_swarm_admits_128_logical_workers_without_widening_shard_runtime():
    lanes = tuple(_lane(f"mass-research-{index:03d}") for index in range(128))
    workers = tuple(
        SwarmWorkerDescriptor(
            worker_id=f"mass-worker-{index:03d}",
            tenant_id="YS_TR",
            worker_class=SwarmWorkerClass.RESEARCH,
            supported_scheduling_classes=(LaneSchedulingClass.RESEARCH,),
            capability_refs=("capability://swarm.read",),
        )
        for index in range(128)
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://128-worker-swarm",
        tenant_id="YS_TR",
        lanes=lanes,
        max_parallel_lanes=4,
    )
    wave = schedule_swarm_wave(
        plan=plan,
        profiles={lane.lane_id: _profile(lane) for lane in lanes},
        requirements={lane.lane_id: _requirement(lane) for lane in lanes},
        registry=SwarmWorkerRegistry(tenant_id="YS_TR", workers=workers),
        policy=SwarmExecutionPolicy(
            max_active_workers=128,
            max_total_concurrency_weight=128,
            shard_size=16,
        ),
        now=NOW,
    )
    assert len(wave.selected_lane_ids) == 128
    assert len(wave.assignments) == 128
    assert len(wave.shards) == 32
    assert all(len(shard.assignments) == 4 for shard in wave.shards)
    assert wave.execution_authority_granted is False


def test_suspended_worker_is_never_routed():
    lane = _lane("research")
    worker = SwarmWorkerDescriptor(
        worker_id="worker-suspended",
        tenant_id="YS_TR",
        worker_class=SwarmWorkerClass.RESEARCH,
        supported_scheduling_classes=(LaneSchedulingClass.RESEARCH,),
        capability_refs=("capability://swarm.read",),
        state=SwarmWorkerState.SUSPENDED,
    )
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=(worker,))
    plan = ParallelMissionPlan(
        objective_ref="objective://suspended",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    wave = schedule_swarm_wave(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        requirements={lane.lane_id: _requirement(lane)},
        registry=registry,
        policy=SwarmExecutionPolicy(),
        now=NOW,
    )
    assert wave.selected_lane_ids == ()
    assert wave.deferred[lane.lane_id] == ("swarm_worker_unavailable",)


def test_worker_registry_caps_logical_swarm_at_512_and_rejects_authority():
    workers = tuple(
        SwarmWorkerDescriptor(
            worker_id=f"worker-{index:03d}",
            tenant_id="YS_TR",
            worker_class=SwarmWorkerClass.RESEARCH,
            supported_scheduling_classes=(LaneSchedulingClass.RESEARCH,),
            capability_refs=("capability://swarm.read",),
        )
        for index in range(512)
    )
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=workers)
    assert len(registry.workers) == 512

    with pytest.raises(ValueError, match="swarm_worker_never_grants_execution_authority"):
        SwarmWorkerDescriptor(
            worker_id="bad-worker",
            tenant_id="YS_TR",
            worker_class=SwarmWorkerClass.EXECUTION,
            supported_scheduling_classes=(LaneSchedulingClass.EXECUTION,),
            execution_authority_granted=True,
        )
