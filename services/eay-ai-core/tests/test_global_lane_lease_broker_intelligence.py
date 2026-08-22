from datetime import datetime, timedelta, timezone

import pytest

from app.global_lane_lease_broker import (
    GlobalLaneLeasePolicy,
    LaneLeaseReleaseDisposition,
    admit_global_lane_leases,
    admitted_plans_from_lane_leases,
    release_global_lane_lease,
)
from app.global_objective_arbiter import GlobalObjectiveCandidate
from app.intelligence_router import IntelligenceTask, PrivacyLevel, TaskComplexity, TaskRisk
from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan


NOW = datetime(2026, 8, 19, 9, 0, tzinfo=timezone.utc)


def _lane(
    lane_id: str,
    *,
    tenant_id: str = "YS_TR",
    resource_ref: str | None = None,
    idempotency_key: str | None = None,
    priority: int = 50,
) -> ParallelMissionLane:
    mutating = resource_ref is not None
    step = MissionStep(
        step_id="step",
        description=lane_id,
        side_effect=mutating,
        idempotency_key=idempotency_key if mutating else None,
        effect_verifier_ref="effect://verify" if mutating else None,
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective-{lane_id}",
        tenant_id=tenant_id,
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step",
        kind=(MissionExecutionKind.CAPABILITY if mutating else MissionExecutionKind.REASONING),
        intelligence_task=(
            None
            if mutating
            else IntelligenceTask(
                task_id=f"read-{lane_id}",
                complexity=TaskComplexity.STANDARD,
                risk=TaskRisk.LOW,
                privacy=PrivacyLevel.INTERNAL,
            )
        ),
        capability_ref="capability://write" if mutating else None,
        prompt=None if mutating else "read",
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        priority=priority,
        exclusive_resource_refs=((resource_ref,) if resource_ref else ()),
    )


def _candidate(
    objective_ref: str,
    lanes: tuple[ParallelMissionLane, ...],
    *,
    tenant_id: str = "YS_TR",
    priority: int = 50,
) -> GlobalObjectiveCandidate:
    return GlobalObjectiveCandidate(
        objective_ref=objective_ref,
        tenant_id=tenant_id,
        priority=priority,
        plan=ParallelMissionPlan(
            objective_ref=objective_ref,
            tenant_id=tenant_id,
            lanes=lanes,
            max_parallel_lanes=min(16, len(lanes)),
        ),
    )


def test_conflicting_write_defers_only_the_write_lane_not_whole_objective() -> None:
    first = _candidate(
        "objective-a",
        (
            _lane("a-write", resource_ref="store:fulya:inventory", idempotency_key="idem-a"),
            _lane("a-read"),
        ),
        priority=90,
    )
    second = _candidate(
        "objective-b",
        (
            _lane("b-write", resource_ref="store:fulya:inventory", idempotency_key="idem-b"),
            _lane("b-read-1"),
            _lane("b-read-2"),
        ),
        priority=80,
    )
    admission = admit_global_lane_leases(
        candidates=(first, second),
        active_leases=(),
        now=NOW,
    )
    selected = {(item.objective_ref, item.lane_id) for item in admission.selected}

    assert ("objective-a", "a-write") in selected
    assert ("objective-a", "a-read") in selected
    assert ("objective-b", "b-write") not in selected
    assert ("objective-b", "b-read-1") in selected
    assert ("objective-b", "b-read-2") in selected
    assert admission.deferred["objective-b::b-write"] == (
        "global_lane_resource_lease_conflict",
    )

    plans = admitted_plans_from_lane_leases(candidates=(first, second), admission=admission)
    assert {lane.lane_id for lane in plans["objective-b"].lanes} == {"b-read-1", "b-read-2"}


def test_independent_write_lanes_from_different_objectives_can_run_together() -> None:
    candidates = (
        _candidate("objective-a", (_lane("a", resource_ref="store:fulya:inventory", idempotency_key="a"),)),
        _candidate("objective-b", (_lane("b", resource_ref="store:uskudar:inventory", idempotency_key="b"),)),
    )
    admission = admit_global_lane_leases(candidates=candidates, active_leases=(), now=NOW)

    assert len(admission.selected) == 2
    assert len(admission.issued_leases) == 2
    assert admission.deferred == {}


def test_same_idempotency_key_serializes_even_when_resource_refs_differ() -> None:
    candidates = (
        _candidate("objective-a", (_lane("a", resource_ref="store:fulya:inventory", idempotency_key="same-key"),)),
        _candidate("objective-b", (_lane("b", resource_ref="store:uskudar:inventory", idempotency_key="same-key"),)),
    )
    admission = admit_global_lane_leases(candidates=candidates, active_leases=(), now=NOW)

    assert len(admission.selected) == 1
    assert admission.deferred["objective-b::b"] == (
        "global_lane_idempotency_lease_conflict",
    )


def test_same_resource_in_different_tenants_remains_parallel() -> None:
    first = _candidate(
        "objective-tr",
        (_lane("tr", tenant_id="YS_TR", resource_ref="store:001:inventory", idempotency_key="tr"),),
        tenant_id="YS_TR",
    )
    second = _candidate(
        "objective-de",
        (_lane("de", tenant_id="DE", resource_ref="store:001:inventory", idempotency_key="de"),),
        tenant_id="DE",
    )
    admission = admit_global_lane_leases(candidates=(first, second), active_leases=(), now=NOW)

    assert len(admission.selected) == 2
    assert admission.deferred == {}


def test_expired_lease_still_blocks_until_explicit_reconciliation_release() -> None:
    owner = _candidate(
        "objective-owner",
        (_lane("owner", resource_ref="store:fulya:inventory", idempotency_key="owner"),),
    )
    initial = admit_global_lane_leases(
        candidates=(owner,),
        active_leases=(),
        now=NOW,
        policy=GlobalLaneLeasePolicy(lease_ttl_seconds=30),
    )
    lease = initial.issued_leases[0]
    contender = _candidate(
        "objective-contender",
        (_lane("contender", resource_ref="store:fulya:inventory", idempotency_key="contender"),),
    )
    stale_time = NOW + timedelta(minutes=2)
    blocked = admit_global_lane_leases(
        candidates=(contender,),
        active_leases=(lease,),
        now=stale_time,
    )

    assert blocked.selected == ()
    assert "global_lane_stale_lease_requires_reconciliation" in blocked.deferred[
        "objective-contender::contender"
    ]
    assert blocked.blocking_stale_lease_ids == (lease.lease_id,)

    released = release_global_lane_lease(
        lease=lease,
        released_at=stale_time,
        disposition=LaneLeaseReleaseDisposition.RECONCILED_NO_EFFECT,
        evidence_refs=("effect-reconciliation://owner/no-effect",),
    )
    unblocked = admit_global_lane_leases(
        candidates=(contender,),
        active_leases=(released,),
        now=stale_time + timedelta(seconds=1),
    )
    assert len(unblocked.selected) == 1
    assert unblocked.deferred == {}


def test_lease_release_requires_evidence_and_never_grants_execution() -> None:
    candidate = _candidate(
        "objective-a",
        (_lane("a", resource_ref="store:fulya:inventory", idempotency_key="a"),),
    )
    lease = admit_global_lane_leases(
        candidates=(candidate,), active_leases=(), now=NOW
    ).issued_leases[0]

    with pytest.raises(ValueError, match="global_lane_lease_release_requires_unique_evidence"):
        release_global_lane_lease(
            lease=lease,
            released_at=NOW + timedelta(minutes=1),
            disposition=LaneLeaseReleaseDisposition.NO_SIDE_EFFECT_ATTEMPTED,
            evidence_refs=(),
        )
    assert lease.execution_authority_granted is False


def test_hundreds_of_read_lanes_remain_parallel_without_leases() -> None:
    candidates = tuple(
        _candidate(f"objective-{index:03d}", (_lane(f"read-{index:03d}"),))
        for index in range(300)
    )
    admission = admit_global_lane_leases(
        candidates=candidates,
        active_leases=(),
        now=NOW,
        policy=GlobalLaneLeasePolicy(max_selected_lanes=512),
    )

    assert len(admission.selected) == 300
    assert admission.issued_leases == ()
    assert admission.deferred == {}
