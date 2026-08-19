from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
    SwarmWorkerState,
)
from app.worker_task_routing import (
    WorkerTaskOutcomeEvidence,
    WorkerTaskRoutingPolicy,
    rank_workers_for_lane,
)

NOW = datetime(2026, 8, 19, 8, 45, tzinfo=timezone.utc)
CAPABILITY = "company.orders.read"


def _lane() -> ParallelMissionLane:
    step = MissionStep(step_id="read", description="read orders")
    definition = MissionDefinition(
        mission_id="mission-orders",
        objective="read orders",
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


def _worker(worker_id: str, *, state: SwarmWorkerState = SwarmWorkerState.READY):
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id="YS_TR",
        worker_class=SwarmWorkerClass.COMPANY_READ,
        supported_scheduling_classes=(LaneSchedulingClass.COMPANY_READ,),
        capability_refs=(CAPABILITY,),
        state=state,
    )


def _outcome(
    worker_id: str,
    *,
    succeeded: bool,
    index: int,
    confidence: float = 1.0,
    observed_at: datetime | None = None,
    tenant_id: str = "YS_TR",
) -> WorkerTaskOutcomeEvidence:
    return WorkerTaskOutcomeEvidence(
        worker_id=worker_id,
        tenant_id=tenant_id,
        scheduling_class=LaneSchedulingClass.COMPANY_READ,
        capability_ref=CAPABILITY,
        succeeded=succeeded,
        observed_at=observed_at or (NOW - timedelta(minutes=index)),
        evidence_refs=(f"evidence://worker/{worker_id}/{index}",),
        confidence=confidence,
    )


def test_sufficient_task_evidence_prefers_higher_calibrated_success_worker():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    outcomes = tuple(
        [
            *(_outcome("worker-a", succeeded=index < 2, index=index + 1) for index in range(5)),
            *(_outcome("worker-b", succeeded=True, index=index + 10) for index in range(5)),
        ]
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=_lane(),
        profile=_profile(),
        requirement=_requirement(),
        outcomes=outcomes,
        now=NOW,
    )
    assert preference.ordered_worker_ids == ("worker-b", "worker-a")
    by_worker = {item.worker_id: item for item in preference.scores}
    assert by_worker["worker-b"].preference_eligible is True
    assert by_worker["worker-b"].posterior_success_rate > by_worker["worker-a"].posterior_success_rate
    assert preference.execution_authority_granted is False


def test_insufficient_samples_remain_neutral_instead_of_inventing_expertise():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    outcomes = (
        _outcome("worker-b", succeeded=True, index=1),
        _outcome("worker-b", succeeded=True, index=2),
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=_lane(),
        profile=_profile(),
        requirement=_requirement(),
        outcomes=outcomes,
        now=NOW,
        policy=WorkerTaskRoutingPolicy(min_samples_for_preference=5),
    )
    assert preference.ordered_worker_ids == ("worker-a", "worker-b")
    assert all(item.posterior_success_rate == 0.5 for item in preference.scores)
    assert all(item.preference_eligible is False for item in preference.scores)


def test_suspended_worker_is_excluded_even_with_perfect_task_history():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(
            _worker("worker-a"),
            _worker("worker-b", state=SwarmWorkerState.SUSPENDED),
        ),
    )
    outcomes = tuple(
        _outcome("worker-b", succeeded=True, index=index + 1)
        for index in range(20)
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=_lane(),
        profile=_profile(),
        requirement=_requirement(),
        outcomes=outcomes,
        now=NOW,
    )
    assert preference.ordered_worker_ids == ("worker-a",)
    assert tuple(item.worker_id for item in preference.scores) == ("worker-a",)


def test_stale_low_confidence_and_cross_tenant_outcomes_do_not_create_preference():
    registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(_worker("worker-a"), _worker("worker-b")),
    )
    outcomes = tuple(
        [
            *(
                _outcome(
                    "worker-b",
                    succeeded=True,
                    index=index + 1,
                    confidence=0.2,
                )
                for index in range(5)
            ),
            *(
                _outcome(
                    "worker-b",
                    succeeded=True,
                    index=index + 10,
                    observed_at=NOW - timedelta(days=60),
                )
                for index in range(5)
            ),
            *(
                _outcome(
                    "worker-b",
                    succeeded=True,
                    index=index + 20,
                    tenant_id="DE_DE",
                )
                for index in range(5)
            ),
        ]
    )
    preference = rank_workers_for_lane(
        registry=registry,
        lane=_lane(),
        profile=_profile(),
        requirement=_requirement(),
        outcomes=outcomes,
        now=NOW,
        policy=WorkerTaskRoutingPolicy(
            min_samples_for_preference=5,
            max_evidence_age_seconds=30 * 86_400,
            min_evidence_confidence=0.8,
        ),
    )
    assert preference.ordered_worker_ids == ("worker-a", "worker-b")
    assert all(item.matching_samples == 0 for item in preference.scores)
