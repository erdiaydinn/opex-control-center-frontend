from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.parallel_mission_scheduler import LaneSchedulingClass
from app.swarm_parallel_runtime import SwarmExecutionPolicy
from app.swarm_worker_health import (
    SwarmWorkerHealthRecord,
    WorkerHealthObservation,
    WorkerHealthPolicy,
    WorkerOutcomeKind,
    health_adjusted_swarm_policy,
    update_swarm_worker_health,
)
from app.swarm_worker_registry import (
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    SwarmWorkerState,
)

NOW = datetime(2026, 8, 19, 7, 30, tzinfo=timezone.utc)


def _worker(worker_id: str, *, state: SwarmWorkerState = SwarmWorkerState.READY):
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id="YS_TR",
        worker_class=SwarmWorkerClass.RESEARCH,
        supported_scheduling_classes=(LaneSchedulingClass.RESEARCH,),
        capability_refs=("capability://research",),
        max_concurrent_assignments=2,
        state=state,
    )


def _observation(
    worker_id: str,
    kind: WorkerOutcomeKind,
    *,
    index: int,
) -> WorkerHealthObservation:
    return WorkerHealthObservation(
        worker_id=worker_id,
        lane_id=f"lane-{index}",
        observed_at=NOW + timedelta(seconds=index),
        outcome_kind=kind,
        evidence_refs=(f"evidence://health/{worker_id}/{index}",),
        failure_code=(f"failure-{index}" if kind in {
            WorkerOutcomeKind.RUNTIME_FAILURE,
            WorkerOutcomeKind.AMBIGUOUS_SIDE_EFFECT,
        } else None),
    )


def test_consecutive_failures_degrade_ready_to_draining_then_suspended():
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=(_worker("worker-a"),))
    policy = WorkerHealthPolicy(
        drain_after_consecutive_failures=2,
        suspend_after_consecutive_failures=3,
    )
    first = update_swarm_worker_health(
        registry=registry,
        existing_records={},
        observations=(
            _observation("worker-a", WorkerOutcomeKind.RUNTIME_FAILURE, index=1),
            _observation("worker-a", WorkerOutcomeKind.RUNTIME_FAILURE, index=2),
        ),
        policy=policy,
    )
    assert first.registry.workers[0].state is SwarmWorkerState.DRAINING
    record = first.records[0]
    assert record.consecutive_failures == 2
    assert record.runtime_failures == 2

    second = update_swarm_worker_health(
        registry=first.registry,
        existing_records={record.worker_id: record},
        observations=(
            _observation("worker-a", WorkerOutcomeKind.RUNTIME_FAILURE, index=3),
        ),
        policy=policy,
    )
    assert second.registry.workers[0].state is SwarmWorkerState.SUSPENDED
    assert second.records[0].consecutive_failures == 3


def test_ambiguous_side_effect_suspends_worker_immediately():
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=(_worker("worker-a"),))
    update = update_swarm_worker_health(
        registry=registry,
        existing_records={},
        observations=(
            _observation("worker-a", WorkerOutcomeKind.AMBIGUOUS_SIDE_EFFECT, index=1),
        ),
        policy=WorkerHealthPolicy(),
    )
    assert update.registry.workers[0].state is SwarmWorkerState.SUSPENDED
    assert update.records[0].ambiguous_side_effects == 1


def test_success_never_silently_reenables_suspended_worker():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a", state=SwarmWorkerState.SUSPENDED),),
    )
    existing = SwarmWorkerHealthRecord(
        worker_id="worker-a",
        state=SwarmWorkerState.SUSPENDED,
        total_observations=3,
        successes=1,
        runtime_failures=2,
        consecutive_failures=2,
        last_observed_at=NOW,
    )
    update = update_swarm_worker_health(
        registry=registry,
        existing_records={"worker-a": existing},
        observations=(
            _observation("worker-a", WorkerOutcomeKind.SUCCESS, index=4),
        ),
        policy=WorkerHealthPolicy(),
    )
    assert update.registry.workers[0].state is SwarmWorkerState.SUSPENDED
    assert update.records[0].consecutive_failures == 0
    assert update.records[0].successes == 2


def test_truth_block_is_not_counted_as_worker_failure():
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=(_worker("worker-a"),))
    update = update_swarm_worker_health(
        registry=registry,
        existing_records={},
        observations=(
            _observation("worker-a", WorkerOutcomeKind.TRUTH_BLOCKED, index=1),
        ),
        policy=WorkerHealthPolicy(drain_after_consecutive_failures=1),
    )
    assert update.registry.workers[0].state is SwarmWorkerState.READY
    assert update.records[0].runtime_failures == 0
    assert update.records[0].consecutive_failures == 0


def test_health_backpressure_never_increases_configured_active_workers():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(
            _worker("worker-a"),
            _worker("worker-b", state=SwarmWorkerState.SUSPENDED),
            _worker("worker-c", state=SwarmWorkerState.DRAINING),
        ),
    )
    health = update_swarm_worker_health(
        registry=registry,
        existing_records={},
        observations=(),
        policy=WorkerHealthPolicy(),
    )
    base = SwarmExecutionPolicy(max_active_workers=64)
    adjusted = health_adjusted_swarm_policy(policy=base, health=health)
    assert health.ready_assignment_slots == 2
    assert adjusted.max_active_workers == 2
    assert adjusted.max_active_workers <= base.max_active_workers
