from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.global_objective_arbiter import (
    GlobalObjectiveArbitrationPolicy,
    GlobalObjectiveCandidate,
    arbitrate_global_objectives,
)
from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan

NOW = datetime(2026, 8, 19, 8, 15, tzinfo=timezone.utc)


def _lane(
    lane_id: str,
    *,
    tenant_id: str,
    side_effect: bool = False,
    resource_ref: str | None = None,
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
        ) or (f"idem-{lane_id}-0000000001" if side_effect else None),
        effect_verifier_ref=("effect://authoritative" if side_effect else None),
    )
    definition = MissionDefinition(
        mission_id=f"mission-{tenant_id}-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id=tenant_id,
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step-1",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref="capability://work",
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        exclusive_resource_refs=(
            (resource_ref or f"resource://{lane_id}",) if side_effect else ()
        ),
    )


def _candidate(
    objective_ref: str,
    *,
    tenant_id: str = "YS_TR",
    lane: ParallelMissionLane | None = None,
    priority: int = 50,
    deadline_at=None,
) -> GlobalObjectiveCandidate:
    lane = lane or _lane(
        objective_ref.removeprefix("objective://"),
        tenant_id=tenant_id,
    )
    plan = ParallelMissionPlan(
        objective_ref=objective_ref,
        tenant_id=tenant_id,
        lanes=(lane,),
    )
    return GlobalObjectiveCandidate(
        objective_ref=objective_ref,
        tenant_id=tenant_id,
        plan=plan,
        priority=priority,
        deadline_at=deadline_at,
    )


def test_same_tenant_same_write_resource_serializes_lower_priority_objective():
    resource = "store://fulya/inventory"
    high = _candidate(
        "objective://high",
        lane=_lane("write-high", tenant_id="YS_TR", side_effect=True, resource_ref=resource),
        priority=90,
    )
    low = _candidate(
        "objective://low",
        lane=_lane("write-low", tenant_id="YS_TR", side_effect=True, resource_ref=resource),
        priority=20,
    )
    admission = arbitrate_global_objectives(
        candidates=(low, high),
        policy=GlobalObjectiveArbitrationPolicy(),
    )
    assert admission.selected_objective_refs == ("objective://high",)
    assert admission.deferred["objective://low"] == ("global_objective_resource_conflict",)
    assert admission.execution_authority_granted is False


def test_same_idempotency_key_conflicts_even_when_resource_refs_differ():
    shared_key = "idem-shared-cross-objective-0001"
    first = _candidate(
        "objective://first",
        lane=_lane(
            "write-first",
            tenant_id="YS_TR",
            side_effect=True,
            resource_ref="resource://a",
            idempotency_key=shared_key,
        ),
        priority=80,
    )
    second = _candidate(
        "objective://second",
        lane=_lane(
            "write-second",
            tenant_id="YS_TR",
            side_effect=True,
            resource_ref="resource://b",
            idempotency_key=shared_key,
        ),
        priority=70,
    )
    admission = arbitrate_global_objectives(
        candidates=(second, first),
        policy=GlobalObjectiveArbitrationPolicy(),
    )
    assert admission.selected_objective_refs == ("objective://first",)
    assert admission.deferred["objective://second"] == ("global_objective_idempotency_conflict",)


def test_same_resource_name_in_different_tenants_does_not_cross_contaminate():
    resource = "store://shared-name/inventory"
    tr = _candidate(
        "objective://tr",
        tenant_id="YS_TR",
        lane=_lane("write-tr", tenant_id="YS_TR", side_effect=True, resource_ref=resource),
    )
    de = _candidate(
        "objective://de",
        tenant_id="DE_DE",
        lane=_lane("write-de", tenant_id="DE_DE", side_effect=True, resource_ref=resource),
    )
    admission = arbitrate_global_objectives(
        candidates=(tr, de),
        policy=GlobalObjectiveArbitrationPolicy(),
    )
    assert set(admission.selected_objective_refs) == {"objective://tr", "objective://de"}
    assert admission.deferred == {}


def test_deadline_outranks_priority_when_two_objectives_need_same_write_resource():
    resource = "device://zebra-001"
    urgent = _candidate(
        "objective://urgent",
        lane=_lane("urgent-write", tenant_id="YS_TR", side_effect=True, resource_ref=resource),
        priority=10,
        deadline_at=NOW + timedelta(seconds=20),
    )
    background = _candidate(
        "objective://background",
        lane=_lane("background-write", tenant_id="YS_TR", side_effect=True, resource_ref=resource),
        priority=100,
    )
    admission = arbitrate_global_objectives(
        candidates=(background, urgent),
        policy=GlobalObjectiveArbitrationPolicy(),
    )
    assert admission.selected_objective_refs == ("objective://urgent",)
    assert admission.deferred["objective://background"] == ("global_objective_resource_conflict",)


def test_one_hundred_read_only_objectives_remain_parallel_under_global_arbiter():
    candidates = tuple(
        _candidate(f"objective://read-{index:03d}")
        for index in range(100)
    )
    admission = arbitrate_global_objectives(
        candidates=candidates,
        policy=GlobalObjectiveArbitrationPolicy(max_concurrent_objectives=128),
    )
    assert len(admission.selected_objective_refs) == 100
    assert admission.deferred == {}
