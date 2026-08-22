from datetime import datetime, timedelta, timezone

import pytest

from app.decision_worker_outcome_learning import (
    build_decision_worker_ownership_proof,
    decision_routing_capability_ref,
    learn_worker_from_decision_outcome,
)
from app.intelligence_router import IntelligenceTask, PrivacyLevel, TaskComplexity, TaskRisk
from app.mission_execution import (
    MissionExecutionKind,
    MissionExecutionSpec,
    MissionExecutionSummary,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.outcome_learning import (
    DecisionLearningRecord,
    ExpectedMetricOutcome,
    GovernedActionReceipt,
    ObservedMetricOutcome,
)
from app.parallel_mission_orchestration import (
    ParallelLaneDisposition,
    ParallelLaneResult,
    ParallelMissionLane,
    ParallelMissionRound,
)
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_parallel_runtime import (
    SwarmAssignment,
    SwarmExecutionRound,
    SwarmShard,
    SwarmWave,
)
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
)
from app.worker_task_routing import WorkerTaskRoutingPolicy, rank_workers_for_lane
from app.world_model import TruthClass, WorldAssertion


NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
DECISION_EVIDENCE = "evidence://decision/demand-forecast/001"


def _decision() -> DecisionLearningRecord:
    return DecisionLearningRecord(
        decision_id="decision-demand-001",
        tenant_id="YS_TR",
        decided_at=NOW + timedelta(seconds=30),
        decision_type="demand_forecast",
        recommendation_ref="decision://demand/001",
        expected_outcomes=(
            ExpectedMetricOutcome(
                metric_key="orders",
                baseline_value=100.0,
                expected_value=120.0,
                unit="orders",
                confidence=0.92,
                evidence_refs=("evidence://forecast/model/001",),
            ),
        ),
        decision_evidence_refs=(DECISION_EVIDENCE,),
    )


def _lane_bundle(*, decision_evidence_ref: str = DECISION_EVIDENCE, explicit_scope: bool = True):
    step = MissionStep(
        step_id="forecast",
        description="Produce evidence-bound demand forecast",
    )
    definition = MissionDefinition(
        mission_id="mission-demand-001",
        objective="Forecast demand",
        tenant_id="YS_TR",
        steps=(step,),
    )
    initial = new_checkpoint(definition, now=NOW)
    completed = record_step_result(
        definition,
        initial,
        step_id="forecast",
        succeeded=True,
        evidence_refs=(decision_evidence_ref,),
        now=NOW + timedelta(minutes=1),
    )
    spec = MissionExecutionSpec(
        step_id="forecast",
        kind=MissionExecutionKind.REASONING,
        intelligence_task=IntelligenceTask(
            task_id="forecasting",
            complexity=TaskComplexity.STANDARD,
            risk=TaskRisk.LOW,
            privacy=PrivacyLevel.INTERNAL,
        ),
        prompt="forecast demand",
    )
    lane = ParallelMissionLane(
        lane_id="lane-demand-001",
        definition=definition,
        checkpoint=initial,
        specs=(spec,),
    )
    profile = ParallelLaneSchedulingProfile(
        lane_id=lane.lane_id,
        scheduling_class=LaneSchedulingClass.INTERACTIVE,
    )
    scope = decision_routing_capability_ref("demand_forecast")
    requirement = SwarmLaneRequirement(
        lane_id=lane.lane_id,
        required_worker_classes=(SwarmWorkerClass.REASONING,),
        required_capability_refs=((scope,) if explicit_scope else ()),
    )
    worker = SwarmWorkerDescriptor(
        worker_id="worker-reasoning-07",
        tenant_id="YS_TR",
        worker_class=SwarmWorkerClass.REASONING,
        supported_scheduling_classes=(LaneSchedulingClass.INTERACTIVE,),
        capability_refs=(scope,),
    )
    registry = SwarmWorkerRegistry(tenant_id="YS_TR", workers=(worker,))
    result = ParallelLaneResult(
        lane_id=lane.lane_id,
        disposition=ParallelLaneDisposition.EXECUTED,
        summary=MissionExecutionSummary(
            checkpoint=completed,
            transitions_executed=1,
            reasoning_engine_ids=("local-qwen",),
        ),
    )
    assignment = SwarmAssignment(lane_id=lane.lane_id, worker_id=worker.worker_id)
    wave = SwarmWave(
        objective_ref="objective://forecast/fulya",
        tenant_id="YS_TR",
        selected_lane_ids=(lane.lane_id,),
        assignments=(assignment,),
        shards=(SwarmShard(shard_id="swarm-shard-001", assignments=(assignment,)),),
        deferred={},
        total_concurrency_weight=1,
        total_cost_units=1,
    )
    parallel_round = ParallelMissionRound(
        objective_ref=wave.objective_ref,
        tenant_id="YS_TR",
        selected_lane_ids=(lane.lane_id,),
        results=(result,),
    )
    execution = SwarmExecutionRound(
        wave=wave,
        shard_rounds=(parallel_round,),
        results=(result,),
    )
    return lane, profile, requirement, registry, execution


def _outcome(value: float) -> tuple[ObservedMetricOutcome, WorldAssertion]:
    observed_at = NOW + timedelta(hours=1)
    evidence_ref = "evidence://company/orders/fulya/0900"
    outcome = ObservedMetricOutcome(
        metric_key="orders",
        observed_value=value,
        unit="orders",
        observed_at=observed_at,
        governed_truth_ref=evidence_ref,
        evidence_refs=(evidence_ref,),
    )
    assertion = WorldAssertion(
        assertion_id="assertion-orders-fulya-0900",
        tenant_id="YS_TR",
        entity_id="store:fulya",
        field_name="orders",
        value=value,
        truth_class=TruthClass.GOVERNED_OPERATIONAL,
        valid_from=observed_at - timedelta(minutes=1),
        observed_at=observed_at,
        source_ref="bq://curated/orders",
        evidence_ref=evidence_ref,
        confidence=0.99,
    )
    return outcome, assertion


def _ownership(*, explicit_scope: bool = True):
    lane, profile, requirement, registry, execution = _lane_bundle(
        explicit_scope=explicit_scope
    )
    proof = build_decision_worker_ownership_proof(
        decision=_decision(),
        lane=lane,
        profile=profile,
        requirement=requirement,
        registry=registry,
        execution=execution,
        decision_evidence_ref=DECISION_EVIDENCE,
    )
    return proof, lane, profile, requirement, registry


def test_worker_ownership_requires_decision_evidence_in_successful_reasoning_checkpoint() -> None:
    lane, profile, requirement, registry, execution = _lane_bundle(
        decision_evidence_ref="evidence://different/reasoning-output"
    )
    with pytest.raises(
        ValueError,
        match="decision_worker_ownership_requires_unique_reasoning_evidence",
    ):
        build_decision_worker_ownership_proof(
            decision=_decision(),
            lane=lane,
            profile=profile,
            requirement=requirement,
            registry=registry,
            execution=execution,
            decision_evidence_ref=DECISION_EVIDENCE,
        )


def test_ineligible_worker_assignment_cannot_become_decision_ownership() -> None:
    lane, profile, requirement, registry, execution = _lane_bundle()
    ineligible = registry.model_copy(
        update={
            "workers": (
                registry.workers[0].model_copy(update={"capability_refs": ()}),
            )
        }
    )
    with pytest.raises(ValueError, match="decision_worker_ownership_assignment_not_eligible"):
        build_decision_worker_ownership_proof(
            decision=_decision(),
            lane=lane,
            profile=profile,
            requirement=requirement,
            registry=ineligible,
            execution=execution,
            decision_evidence_ref=DECISION_EVIDENCE,
        )


def test_worker_ownership_is_exact_assignment_and_integrity_bound() -> None:
    proof, _, profile, _, _ = _ownership()

    assert proof.worker_id == "worker-reasoning-07"
    assert proof.reasoning_step_id == "forecast"
    assert proof.routing_capability_ref == decision_routing_capability_ref("demand_forecast")
    assert proof.execution_authority_granted is False
    assert proof.truth_authority_granted is False

    tampered = proof.model_copy(update={"worker_id": "worker-invented"})
    outcome, assertion = _outcome(118.0)
    with pytest.raises(ValueError, match="decision_worker_ownership_fingerprint_mismatch"):
        learn_worker_from_decision_outcome(
            ownership=tampered,
            decision=_decision(),
            outcomes=(outcome,),
            outcome_assertions=(assertion,),
            profile=profile,
        )


def test_high_quality_authoritative_outcome_becomes_positive_worker_routing_evidence() -> None:
    proof, _, profile, _, _ = _ownership()
    outcome, assertion = _outcome(118.0)
    result = learn_worker_from_decision_outcome(
        ownership=proof,
        decision=_decision(),
        outcomes=(outcome,),
        outcome_assertions=(assertion,),
        profile=profile,
    )

    assert result.blockers == ()
    assert result.routing_evidence is not None
    assert result.routing_evidence.worker_id == "worker-reasoning-07"
    assert result.routing_evidence.succeeded is True
    assert result.routing_evidence.capability_ref == decision_routing_capability_ref("demand_forecast")
    assert result.routing_evidence.execution_authority_granted is False
    assert result.automatic_model_weight_update_allowed is False
    assert result.automatic_policy_update_allowed is False


def test_bad_forecast_becomes_negative_evidence_not_a_hidden_policy_mutation() -> None:
    proof, _, profile, _, _ = _ownership()
    outcome, assertion = _outcome(80.0)
    result = learn_worker_from_decision_outcome(
        ownership=proof,
        decision=_decision(),
        outcomes=(outcome,),
        outcome_assertions=(assertion,),
        profile=profile,
    )

    assert result.routing_evidence is not None
    assert result.routing_evidence.succeeded is False
    assert result.assessment.direction_accuracy == 0.0
    assert result.automatic_model_weight_update_allowed is False


def test_no_explicit_decision_scope_means_no_worker_routing_preference_evidence() -> None:
    proof, _, profile, _, _ = _ownership(explicit_scope=False)
    outcome, assertion = _outcome(118.0)
    result = learn_worker_from_decision_outcome(
        ownership=proof,
        decision=_decision(),
        outcomes=(outcome,),
        outcome_assertions=(assertion,),
        profile=profile,
    )

    assert result.routing_evidence is None
    assert "decision_worker_routing_scope_not_explicit" in result.blockers


def test_unverified_or_analytic_company_outcome_cannot_train_worker_routing() -> None:
    proof, _, profile, _, _ = _ownership()
    outcome, assertion = _outcome(118.0)
    assertion = assertion.model_copy(update={"truth_class": TruthClass.ANALYTIC_INFERENCE})

    with pytest.raises(ValueError, match="timeline_outcome_requires_authoritative_world_truth"):
        learn_worker_from_decision_outcome(
            ownership=proof,
            decision=_decision(),
            outcomes=(outcome,),
            outcome_assertions=(assertion,),
            profile=profile,
        )


def test_action_linked_decision_needs_strong_verified_action_proof_before_worker_routing() -> None:
    proof, _, profile, _, _ = _ownership()
    outcome, assertion = _outcome(118.0)
    action = GovernedActionReceipt(
        action_id="action-demand-001",
        decision_id="decision-demand-001",
        tenant_id="YS_TR",
        executed_at=NOW + timedelta(minutes=5),
        capability_ref="capability://capacity.adjust",
        effect_verified=True,
        evidence_refs=("evidence://weak-action-receipt",),
    )
    result = learn_worker_from_decision_outcome(
        ownership=proof,
        decision=_decision(),
        outcomes=(outcome,),
        outcome_assertions=(assertion,),
        profile=profile,
        action=action,
    )

    assert result.routing_evidence is None
    assert "decision_worker_verified_action_proof_required" in result.blockers


def test_verified_decision_scope_evidence_reaches_existing_worker_router() -> None:
    proof, lane, profile, requirement, registry = _ownership()
    outcome, assertion = _outcome(118.0)
    learning = learn_worker_from_decision_outcome(
        ownership=proof,
        decision=_decision(),
        outcomes=(outcome,),
        outcome_assertions=(assertion,),
        profile=profile,
    )
    assert learning.routing_evidence is not None

    second = registry.workers[0].model_copy(update={"worker_id": "worker-reasoning-08"})
    expanded_registry = SwarmWorkerRegistry(
        tenant_id="YS_TR",
        workers=(*registry.workers, second),
    )
    preference = rank_workers_for_lane(
        registry=expanded_registry,
        lane=lane,
        profile=profile,
        requirement=requirement,
        outcomes=(learning.routing_evidence,),
        now=NOW + timedelta(hours=2),
        policy=WorkerTaskRoutingPolicy(min_samples_for_preference=1),
    )

    assert preference.ordered_worker_ids[0] == "worker-reasoning-07"
    assert preference.scores[0].matching_samples == 1
    assert preference.scores[0].preference_eligible is True
    assert preference.execution_authority_granted is False
