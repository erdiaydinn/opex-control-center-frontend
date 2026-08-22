from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_parallel_runtime import SwarmExecutionPolicy, schedule_swarm_wave
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    SwarmWorkerState,
)
from app.worker_task_routing import WorkerTaskOutcomeEvidence, rank_workers_for_lane

NOW = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)
CAPABILITY = "company.orders.read"


def _lane() -> ParallelMissionLane:
    step = MissionStep(step_id="read", description="read orders")
    definition = MissionDefinition(
        mission_id="mission-orders-routing",
        objective="route governed orders read",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="read",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref=CAPABILITY,
    )
    return ParallelMissionLane(
        lane_id="orders-read",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
    )


def _profile() -> ParallelLaneSchedulingProfile:
    return ParallelLaneSchedulingProfile(
        lane_id="orders-read",
        scheduling_class=LaneSchedulingClass.COMPANY_READ,
    )


def _requirement() -> SwarmLaneRequirement:
    return SwarmLaneRequirement(
        lane_id="orders-read",
        required_worker_classes=(SwarmWorkerClass.COMPANY_READ,),
    )


def _worker(worker_id: str, state: SwarmWorkerState = SwarmWorkerState.READY):
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id="YS_TR",
        worker_class=SwarmWorkerClass.COMPANY_READ,
        supported_scheduling_classes=(LaneSchedulingClass.COMPANY_READ,),
        capability_refs=(CAPABILITY,),
        state=state,
    )


def _outcomes() -> tuple[WorkerTaskOutcomeEvidence, ...]:
    evidence = []
    for index in range(5):
        evidence.append(
            WorkerTaskOutcomeEvidence(
                worker_id="worker-a",
                tenant_id="YS_TR",
                scheduling_class=LaneSchedulingClass.COMPANY_READ,
                capability_ref=CAPABILITY,
                succeeded=index == 0,
                observed_at=NOW - timedelta(minutes=index + 1),
                evidence_refs=(f"evidence://a/{index}",),
            )
        )
        evidence.append(
            WorkerTaskOutcomeEvidence(
                worker_id="worker-b",
                tenant_id="YS_TR",
                scheduling_class=LaneSchedulingClass.COMPANY_READ,
                capability_ref=CAPABILITY,
                succeeded=True,
                observed_at=NOW - timedelta(minutes=index + 10),
                evidence_refs=(f"evidence://b/{index}",),
            )
        )
    return tuple(evidence)


def _plan(lane: ParallelMissionLane) -> ParallelMissionPlan:
    return ParallelMissionPlan(
        objective_ref="objective://routing",
        tenant_id="YS_TR",
        lanes=(lane,),
    )


def test_task_outcome_preference_changes_actual_swarm_worker_assignment():
    lane = _lane()
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=lane,
        profile=_profile(),
        requirement=_requirement(),
        outcomes=_outcomes(),
        now=NOW,
    )
    assert preference.ordered_worker_ids[0] == "worker-b"

    wave = schedule_swarm_wave(
        plan=_plan(lane),
        profiles={lane.lane_id: _profile()},
        requirements={lane.lane_id: _requirement()},
        registry=registry,
        policy=SwarmExecutionPolicy(),
        now=NOW,
        routing_preferences={lane.lane_id: preference},
    )
    assert wave.assignments[0].worker_id == "worker-b"
    assert wave.execution_authority_granted is False


def test_suspended_preferred_worker_is_ignored_by_canonical_eligibility():
    lane = _lane()
    healthy_registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    preference = rank_workers_for_lane(
        registry=healthy_registry,
        lane=lane,
        profile=_profile(),
        requirement=_requirement(),
        outcomes=_outcomes(),
        now=NOW,
    )
    assert preference.ordered_worker_ids[0] == "worker-b"

    degraded_registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(
            _worker("worker-a"),
            _worker("worker-b", state=SwarmWorkerState.SUSPENDED),
        ),
    )
    wave = schedule_swarm_wave(
        plan=_plan(lane),
        profiles={lane.lane_id: _profile()},
        requirements={lane.lane_id: _requirement()},
        registry=degraded_registry,
        policy=SwarmExecutionPolicy(),
        now=NOW,
        routing_preferences={lane.lane_id: preference},
    )
    assert wave.assignments[0].worker_id == "worker-a"


def test_cross_tenant_routing_preference_is_rejected_before_assignment():
    lane = _lane()
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=lane,
        profile=_profile(),
        requirement=_requirement(),
        outcomes=_outcomes(),
        now=NOW,
    ).model_copy(update={"tenant_id": "DE_DE"})

    with pytest.raises(ValueError, match="swarm_routing_preference_tenant_mismatch"):
        schedule_swarm_wave(
            plan=_plan(lane),
            profiles={lane.lane_id: _profile()},
            requirements={lane.lane_id: _requirement()},
            registry=registry,
            policy=SwarmExecutionPolicy(),
            now=NOW,
            routing_preferences={lane.lane_id: preference},
        )
