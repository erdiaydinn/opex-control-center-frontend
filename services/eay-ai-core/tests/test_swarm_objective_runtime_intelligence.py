from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelLaneBindings, ParallelMissionLane, ParallelMissionPlan
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_objective_runtime import SwarmObjectiveStatus, execute_swarm_objective_until_stable
from app.swarm_parallel_runtime import SwarmExecutionPolicy, SwarmWorkerRuntimeBinding
from app.swarm_worker_health import WorkerHealthPolicy
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    SwarmWorkerState,
)

NOW = datetime(2026, 8, 19, 7, 45, tzinfo=timezone.utc)
CAPABILITY = "capability://swarm.work"


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
        capability_ref=CAPABILITY,
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
        scheduling_class=(LaneSchedulingClass.EXECUTION if write else LaneSchedulingClass.RESEARCH),
        estimated_cost_units=1,
        concurrency_weight=1,
        shedable=not write,
        preemptible=not write,
    )


def _requirements(lanes: tuple[ParallelMissionLane, ...]):
    return {lane.lane_id: SwarmLaneRequirement(lane_id=lane.lane_id) for lane in lanes}


def _registry(count: int, *, state: SwarmWorkerState = SwarmWorkerState.READY):
    return SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=tuple(
            SwarmWorkerDescriptor(
                worker_id=f"worker-{index:03d}",
                tenant_id="YS_TR",
                worker_class=SwarmWorkerClass.GENERAL,
                supported_scheduling_classes=(
                    LaneSchedulingClass.RESEARCH,
                    LaneSchedulingClass.EXECUTION,
                ),
                capability_refs=(CAPABILITY,),
                max_concurrent_assignments=8,
                state=state,
            )
            for index in range(count)
        ),
    )


def _success_worker_binding(worker_id: str, calls: list[str]) -> SwarmWorkerRuntimeBinding:
    def resolver(lane: ParallelMissionLane) -> ParallelLaneBindings:
        async def handler(_definition, step, _state, _idempotency_key):
            calls.append(f"{worker_id}:{lane.lane_id}")
            return CapabilityExecutionOutcome(
                succeeded=True,
                effect_verified=step.side_effect,
                evidence_refs=(f"evidence://{worker_id}/{lane.lane_id}",),
                transaction_ref=(
                    f"transaction://{worker_id}/{lane.lane_id}" if step.side_effect else None
                ),
            )

        return ParallelLaneBindings(
            gateway=_UnusedGateway(),  # type: ignore[arg-type]
            reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
            capability_handlers={CAPABILITY: handler},
        )

    return SwarmWorkerRuntimeBinding(worker_id=worker_id, resolve_lane_binding=resolver)


@pytest.mark.asyncio
async def test_fifty_reads_and_two_conflicting_writes_complete_across_swarm_rounds_without_replay():
    reads = tuple(_lane(f"read-{index:03d}") for index in range(50))
    write_a = _lane(
        "write-a",
        side_effect=True,
        resource_ref="store://fulya/inventory",
        priority=100,
    )
    write_b = _lane(
        "write-b",
        side_effect=True,
        resource_ref="store://fulya/inventory",
        priority=99,
    )
    lanes = (*reads, write_a, write_b)
    plan = ParallelMissionPlan(
        objective_ref="objective://large-swarm-inventory",
        tenant_id="YS_TR",
        lanes=lanes,
        max_parallel_lanes=4,
    )
    registry = _registry(16)
    calls: list[str] = []
    worker_bindings = {
        worker.worker_id: _success_worker_binding(worker.worker_id, calls)
        for worker in registry.workers
    }
    result = await execute_swarm_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane) for lane in lanes},
        requirements=_requirements(lanes),
        registry=registry,
        policy=SwarmExecutionPolicy(
            max_active_workers=52,
            max_total_concurrency_weight=52,
            shard_size=16,
        ),
        worker_bindings=worker_bindings,
        now=NOW,
    )

    assert result.status is SwarmObjectiveStatus.COMPLETED
    assert len(result.rounds) == 2
    assert len(result.rounds[0].wave.selected_lane_ids) == 51
    assert result.rounds[0].wave.deferred["write-b"] == ("parallel_resource_conflict",)
    assert result.rounds[1].wave.selected_lane_ids == ("write-b",)
    assert result.total_transitions_executed == 52
    assert result.blockers == ()
    assert sum(call.endswith(":write-a") for call in calls) == 1
    assert sum(call.endswith(":write-b") for call in calls) == 1
    assert all(lane.checkpoint.status is MissionStatus.COMPLETED for lane in result.final_plan.lanes)


@pytest.mark.asyncio
async def test_failed_worker_is_drained_and_same_durable_lane_moves_to_different_runtime():
    lane = _lane("research-retry")
    plan = ParallelMissionPlan(
        objective_ref="objective://worker-failover",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    registry = _registry(2)
    calls: list[str] = []

    def failing_resolver(target: ParallelMissionLane) -> ParallelLaneBindings:
        async def handler(_definition, _step, _state, _idempotency_key):
            calls.append(f"worker-000:{target.lane_id}:failed")
            raise RuntimeError("worker runtime unavailable")

        return ParallelLaneBindings(
            gateway=_UnusedGateway(),  # type: ignore[arg-type]
            reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
            capability_handlers={CAPABILITY: handler},
        )

    worker_bindings = {
        "worker-000": SwarmWorkerRuntimeBinding(
            worker_id="worker-000",
            resolve_lane_binding=failing_resolver,
        ),
        "worker-001": _success_worker_binding("worker-001", calls),
    }
    result = await execute_swarm_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        requirements=_requirements((lane,)),
        registry=registry,
        policy=SwarmExecutionPolicy(max_active_workers=2),
        worker_bindings=worker_bindings,
        health_policy=WorkerHealthPolicy(
            drain_after_consecutive_failures=1,
            suspend_after_consecutive_failures=2,
        ),
        now=NOW,
        max_rounds=3,
    )

    assert result.status is SwarmObjectiveStatus.COMPLETED
    assert len(result.rounds) == 2
    assert result.rounds[0].wave.assignments[0].worker_id == "worker-000"
    assert result.rounds[1].wave.assignments[0].worker_id == "worker-001"
    assert calls == ["worker-000:research-retry:failed", "worker-001:research-retry"]
    states = {worker.worker_id: worker.state for worker in result.final_registry.workers}
    assert states["worker-000"] is SwarmWorkerState.DRAINING
    assert states["worker-001"] is SwarmWorkerState.READY
    assert result.final_plan.lanes[0].checkpoint.sequence == 2


@pytest.mark.asyncio
async def test_ambiguous_side_effect_halts_objective_and_suspends_assigned_worker_without_failover():
    lane = _lane(
        "inventory-write",
        side_effect=True,
        resource_ref="store://fulya/inventory",
        priority=100,
    )
    plan = ParallelMissionPlan(
        objective_ref="objective://ambiguous-swarm-write",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    registry = _registry(2)
    calls: list[str] = []

    def ambiguous_resolver(target: ParallelMissionLane) -> ParallelLaneBindings:
        async def handler(_definition, _step, _state, _idempotency_key):
            calls.append(f"worker-000:{target.lane_id}:ambiguous")
            return CapabilityExecutionOutcome(
                succeeded=False,
                ambiguous_outcome=True,
                evidence_refs=("evidence://ambiguous-write",),
                transaction_ref="transaction://unknown-write",
            )

        return ParallelLaneBindings(
            gateway=_UnusedGateway(),  # type: ignore[arg-type]
            reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
            capability_handlers={CAPABILITY: handler},
        )

    result = await execute_swarm_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        requirements=_requirements((lane,)),
        registry=registry,
        policy=SwarmExecutionPolicy(max_active_workers=2),
        worker_bindings={
            "worker-000": SwarmWorkerRuntimeBinding(
                worker_id="worker-000",
                resolve_lane_binding=ambiguous_resolver,
            ),
            "worker-001": _success_worker_binding("worker-001", calls),
        },
        now=NOW,
        max_rounds=4,
    )

    assert result.status is SwarmObjectiveStatus.HALTED
    assert len(result.rounds) == 1
    assert calls == ["worker-000:inventory-write:ambiguous"]
    states = {worker.worker_id: worker.state for worker in result.final_registry.workers}
    assert states["worker-000"] is SwarmWorkerState.SUSPENDED
    assert result.final_plan.lanes[0].checkpoint.status is MissionStatus.HALTED


@pytest.mark.asyncio
async def test_swarm_with_no_ready_worker_stops_blocked_without_busy_loop():
    lane = _lane("research")
    plan = ParallelMissionPlan(
        objective_ref="objective://no-workers",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    registry = _registry(2, state=SwarmWorkerState.SUSPENDED)
    result = await execute_swarm_objective_until_stable(
        plan=plan,
        profiles={lane.lane_id: _profile(lane)},
        requirements=_requirements((lane,)),
        registry=registry,
        policy=SwarmExecutionPolicy(max_active_workers=2),
        worker_bindings={
            worker.worker_id: _success_worker_binding(worker.worker_id, [])
            for worker in registry.workers
        },
        now=NOW,
        max_rounds=5,
    )

    assert result.status is SwarmObjectiveStatus.BLOCKED
    assert len(result.rounds) == 1
    assert result.total_transitions_executed == 0
    assert "swarm_worker_unavailable:research" in result.blockers
    assert "swarm_objective_no_progress" in result.blockers
