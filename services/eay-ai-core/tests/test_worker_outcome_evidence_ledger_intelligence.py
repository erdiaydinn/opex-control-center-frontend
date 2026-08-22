from datetime import datetime, timedelta, timezone

import pytest

from app.intelligence_router import IntelligenceTask, PrivacyLevel, TaskComplexity, TaskRisk
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
from app.worker_outcome_evidence_ledger import (
    append_worker_outcome_evidence,
    new_worker_outcome_evidence_ledger,
    routing_preferences_from_worker_ledger,
    worker_outcomes_known_as_of,
)
from app.worker_task_routing import WorkerTaskOutcomeEvidence, WorkerTaskRoutingPolicy


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
SCOPE = "decision-type://sha256/" + "a" * 64


def _outcome(
    *,
    worker_id: str = "worker-a",
    observed_at: datetime = NOW,
    evidence_ref: str = "evidence://decision-outcome/001",
    succeeded: bool = True,
    confidence: float = 0.95,
) -> WorkerTaskOutcomeEvidence:
    return WorkerTaskOutcomeEvidence(
        worker_id=worker_id,
        tenant_id="YS_TR",
        scheduling_class=LaneSchedulingClass.INTERACTIVE,
        capability_ref=SCOPE,
        succeeded=succeeded,
        observed_at=observed_at,
        evidence_refs=(evidence_ref,),
        confidence=confidence,
    )


def _routing_bundle(*, worker_a_state: SwarmWorkerState = SwarmWorkerState.READY):
    definition = MissionDefinition(
        mission_id="mission-ledger-routing",
        objective="Route a learned decision task",
        tenant_id="YS_TR",
        steps=(MissionStep(step_id="reason", description="reason"),),
    )
    lane = ParallelMissionLane(
        lane_id="lane-ledger-routing",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(
            MissionExecutionSpec(
                step_id="reason",
                kind=MissionExecutionKind.REASONING,
                intelligence_task=IntelligenceTask(
                    task_id="reason",
                    complexity=TaskComplexity.STANDARD,
                    risk=TaskRisk.LOW,
                    privacy=PrivacyLevel.INTERNAL,
                ),
                prompt="reason",
            ),
        ),
    )
    profile = ParallelLaneSchedulingProfile(
        lane_id=lane.lane_id,
        scheduling_class=LaneSchedulingClass.INTERACTIVE,
    )
    requirement = SwarmLaneRequirement(
        lane_id=lane.lane_id,
        required_worker_classes=(SwarmWorkerClass.REASONING,),
        required_capability_refs=(SCOPE,),
    )
    workers = (
        SwarmWorkerDescriptor(
            worker_id="worker-a",
            tenant_id="YS_TR",
            worker_class=SwarmWorkerClass.REASONING,
            supported_scheduling_classes=(LaneSchedulingClass.INTERACTIVE,),
            capability_refs=(SCOPE,),
            state=worker_a_state,
        ),
        SwarmWorkerDescriptor(
            worker_id="worker-b",
            tenant_id="YS_TR",
            worker_class=SwarmWorkerClass.REASONING,
            supported_scheduling_classes=(LaneSchedulingClass.INTERACTIVE,),
            capability_refs=(SCOPE,),
        ),
    )
    return (
        lane,
        profile,
        requirement,
        SwarmWorkerRegistry(tenant_id="YS_TR", workers=workers),
    )


def test_append_is_idempotent_for_exact_same_evidence() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    outcome = _outcome()
    ledger = append_worker_outcome_evidence(
        ledger=ledger,
        outcome=outcome,
        recorded_at=NOW + timedelta(minutes=1),
    )
    retried = append_worker_outcome_evidence(
        ledger=ledger,
        outcome=outcome,
        recorded_at=NOW + timedelta(minutes=2),
    )

    assert retried.fingerprint == ledger.fingerprint
    assert len(retried.entries) == 1
    assert retried.entries[0].recorded_at == NOW + timedelta(minutes=1)


def test_same_evidence_identity_with_mutated_result_fails_closed() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    original = _outcome()
    ledger = append_worker_outcome_evidence(
        ledger=ledger,
        outcome=original,
        recorded_at=NOW + timedelta(minutes=1),
    )
    mutated = original.model_copy(update={"succeeded": False})

    with pytest.raises(ValueError, match="worker_outcome_ledger_evidence_identity_conflict"):
        append_worker_outcome_evidence(
            ledger=ledger,
            outcome=mutated,
            recorded_at=NOW + timedelta(minutes=2),
        )


def test_cross_tenant_and_secret_bearing_evidence_are_rejected() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    with pytest.raises(ValueError, match="worker_outcome_ledger_cross_tenant_append_forbidden"):
        append_worker_outcome_evidence(
            ledger=ledger,
            outcome=_outcome().model_copy(update={"tenant_id": "DE"}),
            recorded_at=NOW + timedelta(minutes=1),
        )

    with pytest.raises(ValueError, match="worker_outcome_ledger_reference_may_contain_secret"):
        append_worker_outcome_evidence(
            ledger=ledger,
            outcome=_outcome(evidence_ref="https://example.test/proof?token=do-not-store"),
            recorded_at=NOW + timedelta(minutes=1),
        )


def test_historical_snapshot_cannot_see_outcome_until_it_was_recorded() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    outcome = _outcome(observed_at=NOW + timedelta(minutes=10))
    ledger = append_worker_outcome_evidence(
        ledger=ledger,
        outcome=outcome,
        recorded_at=NOW + timedelta(hours=1),
    )

    assert worker_outcomes_known_as_of(
        ledger=ledger,
        as_of=NOW + timedelta(minutes=30),
    ) == ()
    assert worker_outcomes_known_as_of(
        ledger=ledger,
        as_of=NOW + timedelta(hours=1),
    ) == (outcome,)


def test_tampered_ledger_fingerprint_is_rejected_before_routing() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    tampered = ledger.model_copy(update={"fingerprint": "f" * 64})
    lane, profile, requirement, registry = _routing_bundle()

    with pytest.raises(ValueError, match="worker_outcome_ledger_fingerprint_mismatch"):
        routing_preferences_from_worker_ledger(
            ledger=tampered,
            registry=registry,
            lanes=(lane,),
            profiles={lane.lane_id: profile},
            requirements={lane.lane_id: requirement},
            as_of=NOW + timedelta(hours=1),
        )


def test_durable_evidence_refreshes_existing_router_after_sample_floor() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    for index in range(5):
        observed = NOW + timedelta(minutes=index + 1)
        ledger = append_worker_outcome_evidence(
            ledger=ledger,
            outcome=_outcome(
                observed_at=observed,
                evidence_ref=f"evidence://decision-outcome/{index}",
            ),
            recorded_at=observed + timedelta(seconds=5),
        )

    lane, profile, requirement, registry = _routing_bundle()
    preferences = routing_preferences_from_worker_ledger(
        ledger=ledger,
        registry=registry,
        lanes=(lane,),
        profiles={lane.lane_id: profile},
        requirements={lane.lane_id: requirement},
        as_of=NOW + timedelta(hours=1),
        policy=WorkerTaskRoutingPolicy(min_samples_for_preference=5),
    )
    preference = preferences[lane.lane_id]

    assert preference.ordered_worker_ids[0] == "worker-a"
    assert preference.scores[0].matching_samples == 5
    assert preference.scores[0].preference_eligible is True
    assert preference.execution_authority_granted is False


def test_suspended_worker_stays_excluded_even_with_strong_ledger_history() -> None:
    ledger = new_worker_outcome_evidence_ledger(tenant_id="YS_TR", created_at=NOW)
    for index in range(5):
        observed = NOW + timedelta(minutes=index + 1)
        ledger = append_worker_outcome_evidence(
            ledger=ledger,
            outcome=_outcome(
                observed_at=observed,
                evidence_ref=f"evidence://decision-outcome/suspended/{index}",
            ),
            recorded_at=observed + timedelta(seconds=5),
        )

    lane, profile, requirement, registry = _routing_bundle(
        worker_a_state=SwarmWorkerState.SUSPENDED
    )
    preference = routing_preferences_from_worker_ledger(
        ledger=ledger,
        registry=registry,
        lanes=(lane,),
        profiles={lane.lane_id: profile},
        requirements={lane.lane_id: requirement},
        as_of=NOW + timedelta(hours=1),
        policy=WorkerTaskRoutingPolicy(min_samples_for_preference=1),
    )[lane.lane_id]

    assert preference.ordered_worker_ids == ("worker-b",)
    assert all(item.worker_id != "worker-a" for item in preference.scores)
