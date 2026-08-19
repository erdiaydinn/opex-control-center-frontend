"""Evidence-bound decision/outcome learning for Jarvis swarm worker routing.

A good or bad business outcome must never be assigned to a worker by guesswork.
This module first proves that a specific worker produced decision evidence inside
its actually assigned swarm lane and that the assignment was eligible under the
canonical registry. It then requires authoritative outcome truth (and strong
action proof when an action is involved) before converting prediction quality
into the existing WorkerTaskOutcomeEvidence contract.

Learning can influence ordering only after canonical worker eligibility. It never
changes model weights, policies, permissions, worker health or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .mission_execution import MissionExecutionKind
from .mission_runtime import StepStatus
from .outcome_learning import (
    DecisionLearningRecord,
    DecisionOutcomeAssessment,
    GovernedActionReceipt,
    ObservedMetricOutcome,
    assess_decision_outcome,
)
from .parallel_mission_orchestration import ParallelMissionLane
from .parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from .real_world_timeline_learning import (
    VerifiedMissionActionProof,
    verified_metric_outcome_event,
)
from .swarm_parallel_runtime import SwarmExecutionRound
from .swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerRegistry,
    eligible_swarm_workers,
)
from .worker_task_routing import WorkerTaskOutcomeEvidence
from .world_model import WorldAssertion

DECISION_WORKER_OUTCOME_CONTRACT = "eay-decision-worker-outcome-learning-v1"


def _hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def decision_routing_capability_ref(decision_type: str) -> str:
    """Return a stable, non-semantic capability scope for one decision type."""

    normalized = " ".join(decision_type.casefold().split())
    return "decision-type://sha256/" + hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class DecisionWorkerOwnershipProof(BaseModel):
    contract: str = DECISION_WORKER_OUTCOME_CONTRACT
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    objective_ref: str = Field(min_length=1)
    lane_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    worker_id: str = Field(min_length=1)
    scheduling_class: LaneSchedulingClass
    reasoning_step_id: str = Field(min_length=1)
    decision_evidence_ref: str = Field(min_length=1)
    input_checkpoint_sequence: int = Field(ge=0)
    output_checkpoint_sequence: int = Field(ge=1)
    output_checkpointed_at: datetime
    routing_capability_ref: str | None = None
    assignment_ref: str = Field(min_length=1)
    truth_authority_granted: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def ownership_is_integrity_bound_and_non_authoritative(self) -> "DecisionWorkerOwnershipProof":
        if self.output_checkpointed_at.tzinfo is None or self.output_checkpointed_at.utcoffset() is None:
            raise ValueError("decision_worker_ownership_checkpoint_requires_timezone")
        if self.output_checkpoint_sequence <= self.input_checkpoint_sequence:
            raise ValueError("decision_worker_ownership_requires_checkpoint_progress")
        if self.truth_authority_granted or self.execution_authority_granted:
            raise ValueError("decision_worker_ownership_never_grants_authority")
        if self.fingerprint != _hash(_ownership_payload(self)):
            raise ValueError("decision_worker_ownership_fingerprint_mismatch")
        return self


def _ownership_payload(proof: DecisionWorkerOwnershipProof) -> dict[str, object]:
    return {
        "contract": proof.contract,
        "decision_id": proof.decision_id,
        "tenant_id": proof.tenant_id,
        "objective_ref": proof.objective_ref,
        "lane_id": proof.lane_id,
        "mission_id": proof.mission_id,
        "worker_id": proof.worker_id,
        "scheduling_class": proof.scheduling_class.value,
        "reasoning_step_id": proof.reasoning_step_id,
        "decision_evidence_ref": proof.decision_evidence_ref,
        "input_checkpoint_sequence": proof.input_checkpoint_sequence,
        "output_checkpoint_sequence": proof.output_checkpoint_sequence,
        "output_checkpointed_at": proof.output_checkpointed_at.isoformat(),
        "routing_capability_ref": proof.routing_capability_ref,
        "assignment_ref": proof.assignment_ref,
        "truth_authority_granted": False,
        "execution_authority_granted": False,
    }


def build_decision_worker_ownership_proof(
    *,
    decision: DecisionLearningRecord,
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
    requirement: SwarmLaneRequirement,
    registry: SwarmWorkerRegistry,
    execution: SwarmExecutionRound,
    decision_evidence_ref: str,
) -> DecisionWorkerOwnershipProof:
    """Prove that one actually assigned, eligible worker produced decision evidence."""

    decision = DecisionLearningRecord.model_validate(decision.model_dump(mode="json"))
    lane = ParallelMissionLane.model_validate(lane.model_dump(mode="json"))
    profile = ParallelLaneSchedulingProfile.model_validate(profile.model_dump(mode="json"))
    requirement = SwarmLaneRequirement.model_validate(requirement.model_dump(mode="json"))
    registry = SwarmWorkerRegistry.model_validate(registry.model_dump(mode="json"))
    execution = SwarmExecutionRound.model_validate(execution.model_dump(mode="json"))

    if profile.lane_id != lane.lane_id or requirement.lane_id != lane.lane_id:
        raise ValueError("decision_worker_ownership_lane_contract_mismatch")
    if (
        decision.tenant_id != lane.definition.tenant_id
        or execution.wave.tenant_id != decision.tenant_id
        or registry.tenant_id != decision.tenant_id
    ):
        raise ValueError("decision_worker_ownership_tenant_mismatch")
    if decision_evidence_ref not in set(decision.decision_evidence_refs):
        raise ValueError("decision_worker_ownership_evidence_not_in_decision")
    if decision.decided_at < lane.checkpoint.checkpointed_at:
        raise ValueError("decision_worker_ownership_decision_predates_lane")

    assignments = [item for item in execution.wave.assignments if item.lane_id == lane.lane_id]
    if len(assignments) != 1:
        raise ValueError("decision_worker_ownership_requires_exact_assignment")
    worker_id = assignments[0].worker_id
    eligible_ids = {
        item.worker_id
        for item in eligible_swarm_workers(
            registry=registry,
            lane=lane,
            profile=profile,
            requirement=requirement,
        )
    }
    if worker_id not in eligible_ids:
        raise ValueError("decision_worker_ownership_assignment_not_eligible")

    result_map = {item.lane_id: item for item in execution.results}
    result = result_map.get(lane.lane_id)
    if result is None or result.summary is None:
        raise ValueError("decision_worker_ownership_execution_summary_missing")
    checkpoint = result.summary.checkpoint
    if checkpoint.mission_id != lane.definition.mission_id or checkpoint.tenant_id != decision.tenant_id:
        raise ValueError("decision_worker_ownership_checkpoint_identity_mismatch")
    if checkpoint.definition_fingerprint != lane.definition.fingerprint():
        raise ValueError("decision_worker_ownership_definition_fingerprint_mismatch")
    if checkpoint.sequence <= lane.checkpoint.sequence:
        raise ValueError("decision_worker_ownership_requires_checkpoint_progress")

    reasoning_step_ids = {
        spec.step_id for spec in lane.specs if spec.kind is MissionExecutionKind.REASONING
    }
    matching_reasoning_steps = [
        state.step_id
        for state in checkpoint.steps
        if state.step_id in reasoning_step_ids
        and state.status is StepStatus.SUCCEEDED
        and decision_evidence_ref in set(state.evidence_refs)
    ]
    if len(matching_reasoning_steps) != 1:
        raise ValueError("decision_worker_ownership_requires_unique_reasoning_evidence")

    expected_scope = decision_routing_capability_ref(decision.decision_type)
    routing_scope = (
        expected_scope
        if expected_scope in set(requirement.required_capability_refs)
        else None
    )
    assignment_ref = (
        "swarm-assignment://"
        + decision.tenant_id
        + "/"
        + _hash(execution.wave.objective_ref)[:16]
        + "/"
        + lane.lane_id
        + "/"
        + worker_id
        + "/"
        + str(checkpoint.sequence)
    )
    payload = dict(
        decision_id=decision.decision_id,
        tenant_id=decision.tenant_id,
        objective_ref=execution.wave.objective_ref,
        lane_id=lane.lane_id,
        mission_id=lane.definition.mission_id,
        worker_id=worker_id,
        scheduling_class=profile.scheduling_class,
        reasoning_step_id=matching_reasoning_steps[0],
        decision_evidence_ref=decision_evidence_ref,
        input_checkpoint_sequence=lane.checkpoint.sequence,
        output_checkpoint_sequence=checkpoint.sequence,
        output_checkpointed_at=checkpoint.checkpointed_at,
        routing_capability_ref=routing_scope,
        assignment_ref=assignment_ref,
    )
    provisional = DecisionWorkerOwnershipProof.model_construct(
        contract=DECISION_WORKER_OUTCOME_CONTRACT,
        **payload,
        truth_authority_granted=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return DecisionWorkerOwnershipProof(
        **payload,
        fingerprint=_hash(_ownership_payload(provisional)),
    )


class DecisionWorkerQualityPolicy(BaseModel):
    contract: str = DECISION_WORKER_OUTCOME_CONTRACT
    min_direction_accuracy: float = Field(default=0.75, ge=0.0, le=1.0)
    max_mean_relative_error_pct: float = Field(default=25.0, ge=0.0, le=1_000.0)
    min_suggested_confidence_multiplier: float = Field(default=0.85, ge=0.25, le=1.25)
    min_original_confidence: float = Field(default=0.80, ge=0.0, le=1.0)


class DecisionWorkerLearningResult(BaseModel):
    contract: str = DECISION_WORKER_OUTCOME_CONTRACT
    decision_id: str
    tenant_id: str
    worker_id: str
    lane_id: str
    assessment: DecisionOutcomeAssessment
    mean_relative_error_pct: float | None = None
    routing_evidence: WorkerTaskOutcomeEvidence | None = None
    blockers: tuple[str, ...] = ()
    automatic_model_weight_update_allowed: bool = False
    automatic_policy_update_allowed: bool = False
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def learning_result_never_self_promotes(self) -> "DecisionWorkerLearningResult":
        if self.automatic_model_weight_update_allowed or self.automatic_policy_update_allowed:
            raise ValueError("decision_worker_learning_cannot_self_modify_production")
        if self.execution_authority_granted:
            raise ValueError("decision_worker_learning_never_grants_execution_authority")
        return self


def _validated_authoritative_outcomes(
    *,
    decision: DecisionLearningRecord,
    outcomes: tuple[ObservedMetricOutcome, ...],
    assertions: tuple[WorldAssertion, ...],
    action_id: str | None,
) -> None:
    assertion_map = {item.field_name: item for item in assertions}
    if len(assertion_map) != len(assertions):
        raise ValueError("decision_worker_learning_duplicate_outcome_assertion")
    if {item.metric_key for item in outcomes} != set(assertion_map):
        raise ValueError("decision_worker_learning_outcome_assertions_must_match_metrics")
    for outcome in outcomes:
        verified_metric_outcome_event(
            outcome=outcome,
            tenant_id=decision.tenant_id,
            assertion=assertion_map[outcome.metric_key],
            decision_id=decision.decision_id,
            action_id=action_id,
        )


def learn_worker_from_decision_outcome(
    *,
    ownership: DecisionWorkerOwnershipProof,
    decision: DecisionLearningRecord,
    outcomes: tuple[ObservedMetricOutcome, ...],
    outcome_assertions: tuple[WorldAssertion, ...],
    profile: ParallelLaneSchedulingProfile,
    action: GovernedActionReceipt | None = None,
    verified_action_proof: VerifiedMissionActionProof | None = None,
    counterfactual_evidence_ref: str | None = None,
    policy: DecisionWorkerQualityPolicy | None = None,
) -> DecisionWorkerLearningResult:
    """Convert strongly bound decision quality into existing worker-routing evidence."""

    ownership = DecisionWorkerOwnershipProof.model_validate(ownership.model_dump(mode="json"))
    decision = DecisionLearningRecord.model_validate(decision.model_dump(mode="json"))
    profile = ParallelLaneSchedulingProfile.model_validate(profile.model_dump(mode="json"))
    rules = policy or DecisionWorkerQualityPolicy()

    if ownership.decision_id != decision.decision_id or ownership.tenant_id != decision.tenant_id:
        raise ValueError("decision_worker_learning_ownership_identity_mismatch")
    if ownership.lane_id != profile.lane_id or ownership.scheduling_class is not profile.scheduling_class:
        raise ValueError("decision_worker_learning_profile_mismatch")
    if not outcomes:
        raise ValueError("decision_worker_learning_requires_outcomes")

    action_id = None
    blockers: list[str] = []
    if action is not None:
        action = GovernedActionReceipt.model_validate(action.model_dump(mode="json"))
        action_id = action.action_id
        if verified_action_proof is None:
            blockers.append("decision_worker_verified_action_proof_required")
        else:
            proof = VerifiedMissionActionProof.model_validate(
                verified_action_proof.model_dump(mode="json")
            )
            if (
                proof.action_id != action.action_id
                or proof.decision_id != decision.decision_id
                or proof.tenant_id != decision.tenant_id
            ):
                raise ValueError("decision_worker_verified_action_proof_identity_mismatch")
    elif verified_action_proof is not None:
        raise ValueError("decision_worker_action_proof_without_action")

    _validated_authoritative_outcomes(
        decision=decision,
        outcomes=outcomes,
        assertions=outcome_assertions,
        action_id=action_id,
    )
    assessment = assess_decision_outcome(
        decision=decision,
        outcomes=list(outcomes),
        action=action,
        counterfactual_evidence_ref=counterfactual_evidence_ref,
    )

    expected_keys = {item.metric_key for item in decision.expected_outcomes}
    observed_keys = {item.metric_key for item in outcomes}
    if expected_keys != observed_keys or len(assessment.metric_results) != len(decision.expected_outcomes):
        blockers.append("decision_worker_outcome_set_incomplete")

    relative_errors = [
        item.relative_error_pct
        for item in assessment.metric_results
        if item.relative_error_pct is not None
    ]
    mean_relative_error = (
        round(sum(relative_errors) / len(relative_errors), 6)
        if relative_errors
        else None
    )
    if mean_relative_error is None:
        blockers.append("decision_worker_relative_error_unavailable")

    original_confidence = (
        sum(item.original_confidence for item in assessment.metric_results)
        / len(assessment.metric_results)
        if assessment.metric_results
        else 0.0
    )
    if original_confidence < rules.min_original_confidence:
        blockers.append("decision_worker_original_confidence_too_low")
    if ownership.routing_capability_ref is None:
        blockers.append("decision_worker_routing_scope_not_explicit")

    unsafe_assessment_blockers = tuple(
        item
        for item in assessment.blockers
        if item != "outcome_learning_counterfactual_missing_for_attribution"
    )
    blockers.extend(unsafe_assessment_blockers)

    direction_ok = (
        assessment.direction_accuracy is not None
        and assessment.direction_accuracy >= rules.min_direction_accuracy
    )
    error_ok = (
        mean_relative_error is not None
        and mean_relative_error <= rules.max_mean_relative_error_pct
    )
    multiplier_ok = (
        assessment.suggested_confidence_multiplier
        >= rules.min_suggested_confidence_multiplier
    )
    succeeded = direction_ok and error_ok and multiplier_ok

    routing_evidence = None
    if not blockers:
        observed_at = max(item.observed_at for item in outcomes)
        routing_evidence = WorkerTaskOutcomeEvidence(
            worker_id=ownership.worker_id,
            tenant_id=ownership.tenant_id,
            scheduling_class=ownership.scheduling_class,
            capability_ref=ownership.routing_capability_ref,
            succeeded=succeeded,
            observed_at=observed_at,
            evidence_refs=tuple(
                dict.fromkeys(
                    (
                        ownership.assignment_ref,
                        ownership.decision_evidence_ref,
                        *assessment.learning_evidence_refs,
                    )
                )
            ),
            confidence=round(min(max(original_confidence, 0.0), 1.0), 6),
        )

    return DecisionWorkerLearningResult(
        decision_id=decision.decision_id,
        tenant_id=decision.tenant_id,
        worker_id=ownership.worker_id,
        lane_id=ownership.lane_id,
        assessment=assessment,
        mean_relative_error_pct=mean_relative_error,
        routing_evidence=routing_evidence,
        blockers=tuple(dict.fromkeys(blockers)),
    )
