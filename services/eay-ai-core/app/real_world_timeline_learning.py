"""Evidence-bound learning/device adapters for the Jarvis real-world timeline.

The timeline remains an index, never a source of truth, execution authority, or
causal proof. In particular a boolean ``effect_verified=True`` receipt is not
sufficient for VERIFIED_ACTION: durable mission state, execution outcome and an
authoritative independent effect verification must all agree.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .device_world_model import DeviceTrust, DeviceWorldSnapshot
from .mission_execution import CapabilityExecutionOutcome, MissionExecutionKind, MissionExecutionSpec
from .mission_runtime import MissionCheckpoint, MissionDefinition, StepStatus
from .outcome_learning import DecisionLearningRecord, GovernedActionReceipt, ObservedMetricOutcome
from .playwright_mission_adapter import BrowserEffectVerification, EffectVerificationStatus
from .real_world_timeline import (
    RealWorldTimelineEvent,
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineEventLink,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    TimelineRelationKind,
    build_timeline_event,
    validate_timeline_event_integrity,
)
from .world_model import TruthClass, WorldAssertion

REAL_WORLD_TIMELINE_LEARNING_CONTRACT = "eay-real-world-timeline-learning-v1"

_AUTHORITATIVE_OUTCOME_TRUTH = frozenset({
    TruthClass.GOVERNED_OPERATIONAL,
    TruthClass.VERIFIED_COMPANY,
    TruthClass.VERIFIED_LEGAL,
    TruthClass.VERIFIED_EXTERNAL,
})
_DEVICE_CONFIDENCE = {
    DeviceTrust.UNTRUSTED: 0.30,
    DeviceTrust.REGISTERED: 0.60,
    DeviceTrust.MANAGED: 0.85,
    DeviceTrust.ATTESTED: 0.95,
}


def _aware(value: datetime, error: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(error)


def _hash(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class VerifiedMissionActionProof(BaseModel):
    """Integrity-sealed composition of already-governed action evidence."""

    contract: str = REAL_WORLD_TIMELINE_LEARNING_CONTRACT
    action_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    effect_verifier_ref: str = Field(min_length=1)
    definition_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    checkpoint_sequence: int = Field(ge=1)
    executed_at: datetime
    checkpointed_at: datetime
    idempotency_key_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approval_ref: str | None = None
    transaction_ref: str = Field(min_length=1)
    verification_evidence_refs: tuple[str, ...] = Field(min_length=1)
    execution_evidence_refs: tuple[str, ...] = Field(min_length=1)
    receipt_evidence_refs: tuple[str, ...] = Field(min_length=1)
    causal_claim_proven: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def integrity_boundary(self) -> "VerifiedMissionActionProof":
        _aware(self.executed_at, "timeline_verified_action_executed_at_requires_timezone")
        _aware(self.checkpointed_at, "timeline_verified_action_checkpoint_requires_timezone")
        if self.checkpointed_at < self.executed_at:
            raise ValueError("timeline_verified_action_checkpoint_precedes_execution")
        if self.causal_claim_proven or self.execution_authority_granted:
            raise ValueError("timeline_verified_action_proof_never_grants_authority_or_causality")
        for refs, error in (
            (self.verification_evidence_refs, "timeline_verified_action_duplicate_verification_evidence"),
            (self.execution_evidence_refs, "timeline_verified_action_duplicate_execution_evidence"),
            (self.receipt_evidence_refs, "timeline_verified_action_duplicate_receipt_evidence"),
        ):
            if len(set(refs)) != len(refs):
                raise ValueError(error)
        if self.fingerprint != _hash(_proof_payload(self)):
            raise ValueError("timeline_verified_action_proof_fingerprint_mismatch")
        return self


def _proof_payload(proof: VerifiedMissionActionProof) -> dict[str, object]:
    return {
        "contract": proof.contract,
        "action_id": proof.action_id,
        "decision_id": proof.decision_id,
        "tenant_id": proof.tenant_id,
        "mission_id": proof.mission_id,
        "step_id": proof.step_id,
        "capability_ref": proof.capability_ref,
        "effect_verifier_ref": proof.effect_verifier_ref,
        "definition_fingerprint": proof.definition_fingerprint,
        "checkpoint_sequence": proof.checkpoint_sequence,
        "executed_at": proof.executed_at.isoformat(),
        "checkpointed_at": proof.checkpointed_at.isoformat(),
        "idempotency_key_fingerprint": proof.idempotency_key_fingerprint,
        "approval_ref": proof.approval_ref,
        "transaction_ref": proof.transaction_ref,
        "verification_evidence_refs": sorted(proof.verification_evidence_refs),
        "execution_evidence_refs": sorted(proof.execution_evidence_refs),
        "receipt_evidence_refs": sorted(proof.receipt_evidence_refs),
        "causal_claim_proven": False,
        "execution_authority_granted": False,
    }


def build_verified_mission_action_proof(
    *,
    receipt: GovernedActionReceipt,
    definition: MissionDefinition,
    checkpoint: MissionCheckpoint,
    spec: MissionExecutionSpec,
    execution_outcome: CapabilityExecutionOutcome,
    verification: BrowserEffectVerification,
) -> VerifiedMissionActionProof:
    """Require mutually agreeing mission, execution and read-back evidence."""

    if checkpoint.mission_id != definition.mission_id or checkpoint.tenant_id != definition.tenant_id:
        raise ValueError("timeline_verified_action_checkpoint_identity_mismatch")
    if checkpoint.definition_fingerprint != definition.fingerprint():
        raise ValueError("timeline_verified_action_definition_fingerprint_mismatch")
    if checkpoint.sequence < 1:
        raise ValueError("timeline_verified_action_checkpoint_not_advanced")
    if receipt.tenant_id != definition.tenant_id:
        raise ValueError("timeline_verified_action_receipt_tenant_mismatch")
    if not receipt.effect_verified:
        raise ValueError("timeline_verified_action_weak_receipt_not_sufficient")
    if spec.kind is not MissionExecutionKind.CAPABILITY or not spec.capability_ref:
        raise ValueError("timeline_verified_action_requires_capability_spec")
    if receipt.capability_ref != spec.capability_ref:
        raise ValueError("timeline_verified_action_capability_mismatch")

    steps = {item.step_id: item for item in definition.steps}
    states = {item.step_id: item for item in checkpoint.steps}
    step = steps.get(spec.step_id)
    state = states.get(spec.step_id)
    if step is None or state is None:
        raise ValueError("timeline_verified_action_step_missing")
    if not step.side_effect:
        raise ValueError("timeline_verified_action_requires_side_effect_step")
    if not step.effect_verifier_ref:
        raise ValueError("timeline_verified_action_effect_verifier_missing")
    if state.status is not StepStatus.SUCCEEDED or state.ambiguous_outcome:
        raise ValueError("timeline_verified_action_checkpoint_not_successful")
    if not state.evidence_refs:
        raise ValueError("timeline_verified_action_checkpoint_evidence_missing")

    if not execution_outcome.succeeded or not execution_outcome.effect_verified:
        raise ValueError("timeline_verified_action_execution_not_effect_verified")
    if execution_outcome.ambiguous_outcome:
        raise ValueError("timeline_verified_action_execution_ambiguous")
    if verification.status is not EffectVerificationStatus.VERIFIED_APPLIED:
        raise ValueError("timeline_verified_action_requires_authoritative_applied_verification")
    if not verification.transaction_ref or not execution_outcome.transaction_ref:
        raise ValueError("timeline_verified_action_transaction_ref_required")
    if verification.transaction_ref != execution_outcome.transaction_ref:
        raise ValueError("timeline_verified_action_transaction_ref_mismatch")

    checkpoint_evidence = set(state.evidence_refs)
    verifier_evidence = set(verification.evidence_refs)
    execution_evidence = set(execution_outcome.evidence_refs)
    receipt_evidence = set(receipt.evidence_refs)
    if not verifier_evidence.issubset(execution_evidence):
        raise ValueError("timeline_verified_action_verifier_evidence_not_in_execution")
    if not execution_evidence.issubset(checkpoint_evidence):
        raise ValueError("timeline_verified_action_execution_evidence_not_checkpointed")
    if not receipt_evidence.issubset(checkpoint_evidence):
        raise ValueError("timeline_verified_action_receipt_evidence_not_checkpointed")
    if verification.transaction_ref not in checkpoint_evidence:
        raise ValueError("timeline_verified_action_transaction_not_checkpointed")

    if step.requires_human_approval:
        if not state.approval_ref or receipt.approval_ref != state.approval_ref:
            raise ValueError("timeline_verified_action_approval_evidence_mismatch")
    elif receipt.approval_ref is not None and receipt.approval_ref != state.approval_ref:
        raise ValueError("timeline_verified_action_unbound_approval_ref")

    _aware(receipt.executed_at, "timeline_verified_action_executed_at_requires_timezone")
    if receipt.executed_at > checkpoint.checkpointed_at:
        raise ValueError("timeline_verified_action_receipt_after_checkpoint")

    payload = dict(
        action_id=receipt.action_id,
        decision_id=receipt.decision_id,
        tenant_id=receipt.tenant_id,
        mission_id=definition.mission_id,
        step_id=step.step_id,
        capability_ref=receipt.capability_ref,
        effect_verifier_ref=step.effect_verifier_ref,
        definition_fingerprint=checkpoint.definition_fingerprint,
        checkpoint_sequence=checkpoint.sequence,
        executed_at=receipt.executed_at,
        checkpointed_at=checkpoint.checkpointed_at,
        idempotency_key_fingerprint=_hash(step.idempotency_key or ""),
        approval_ref=receipt.approval_ref,
        transaction_ref=verification.transaction_ref,
        verification_evidence_refs=tuple(dict.fromkeys(verification.evidence_refs)),
        execution_evidence_refs=tuple(dict.fromkeys(execution_outcome.evidence_refs)),
        receipt_evidence_refs=tuple(dict.fromkeys(receipt.evidence_refs)),
    )
    provisional = VerifiedMissionActionProof.model_construct(
        contract=REAL_WORLD_TIMELINE_LEARNING_CONTRACT,
        **payload,
        causal_claim_proven=False,
        execution_authority_granted=False,
        fingerprint="0" * 64,
    )
    return VerifiedMissionActionProof(**payload, fingerprint=_hash(_proof_payload(provisional)))


def decision_learning_event(record: DecisionLearningRecord) -> RealWorldTimelineEvent:
    """Index a decision without copying expected numeric outcomes."""

    return build_timeline_event(
        event_id=f"decision:{record.decision_id}",
        event_type="eay.decision.recorded",
        event_kind=TimelineEventKind.DECISION,
        source_ref="eay://decision-outcome-learning",
        tenant_id=record.tenant_id,
        occurred_at=record.decided_at,
        observed_at=record.decided_at,
        data_ref=record.recommendation_ref,
        authority_class=TimelineAuthorityClass.DECISION_RECORD,
        confidence=1.0,
        object_relations=(TimelineObjectRelation(
            object_ref=f"decision://{record.decision_id}",
            object_kind=TimelineObjectKind.DECISION,
            qualifier=TimelineObjectQualifier.SUBJECT,
        ),),
        evidence_refs=record.decision_evidence_refs,
        tags=(record.decision_type,),
    )


def verified_action_event(proof: VerifiedMissionActionProof) -> RealWorldTimelineEvent:
    """Index a strong action proof; model_copy tampering is revalidated."""

    proof = VerifiedMissionActionProof.model_validate(proof.model_dump(mode="json"))
    evidence = tuple(dict.fromkeys((
        *proof.verification_evidence_refs,
        *proof.execution_evidence_refs,
        *proof.receipt_evidence_refs,
        proof.transaction_ref,
    )))
    return build_timeline_event(
        event_id=f"action:{proof.action_id}",
        event_type="eay.action.verified",
        event_kind=TimelineEventKind.ACTION,
        source_ref="eay://mission-execution",
        tenant_id=proof.tenant_id,
        occurred_at=proof.executed_at,
        observed_at=proof.checkpointed_at,
        data_ref=f"verified-action-proof://{proof.fingerprint}",
        authority_class=TimelineAuthorityClass.VERIFIED_ACTION,
        confidence=1.0,
        object_relations=(
            TimelineObjectRelation(object_ref=f"action://{proof.action_id}", object_kind=TimelineObjectKind.ACTION, qualifier=TimelineObjectQualifier.SUBJECT),
            TimelineObjectRelation(object_ref=f"decision://{proof.decision_id}", object_kind=TimelineObjectKind.DECISION, qualifier=TimelineObjectQualifier.CONTEXT),
            TimelineObjectRelation(object_ref=f"mission://{proof.mission_id}", object_kind=TimelineObjectKind.MISSION, qualifier=TimelineObjectQualifier.CONTEXT),
        ),
        evidence_refs=evidence,
        tags=(proof.capability_ref,),
    )


def verified_metric_outcome_event(
    *,
    outcome: ObservedMetricOutcome,
    tenant_id: str,
    assertion: WorldAssertion,
    decision_id: str | None = None,
    action_id: str | None = None,
) -> RealWorldTimelineEvent:
    """Index measured outcome provenance while keeping its value canonical."""

    if assertion.tenant_id != tenant_id:
        raise ValueError("timeline_outcome_assertion_tenant_mismatch")
    if assertion.truth_class not in _AUTHORITATIVE_OUTCOME_TRUTH:
        raise ValueError("timeline_outcome_requires_authoritative_world_truth")
    if assertion.field_name != outcome.metric_key:
        raise ValueError("timeline_outcome_metric_truth_field_mismatch")
    if assertion.observed_at > outcome.observed_at:
        raise ValueError("timeline_outcome_truth_observed_after_outcome")
    if assertion.valid_from > outcome.observed_at or (assertion.valid_to is not None and outcome.observed_at >= assertion.valid_to):
        raise ValueError("timeline_outcome_truth_not_effective_at_observation")

    assertion_ref = f"world-assertion://{assertion.assertion_id}"
    if outcome.governed_truth_ref not in {assertion.evidence_ref, assertion_ref}:
        raise ValueError("timeline_outcome_governed_truth_ref_mismatch")
    if outcome.governed_truth_ref != assertion.evidence_ref and assertion.evidence_ref not in set(outcome.evidence_refs):
        raise ValueError("timeline_outcome_authoritative_evidence_missing")

    relations = [TimelineObjectRelation(
        object_ref=f"world-entity://{assertion.entity_id}",
        object_kind=TimelineObjectKind.WORLD_ENTITY,
        qualifier=TimelineObjectQualifier.SUBJECT,
    )]
    if decision_id:
        relations.append(TimelineObjectRelation(object_ref=f"decision://{decision_id}", object_kind=TimelineObjectKind.DECISION, qualifier=TimelineObjectQualifier.CONTEXT))
    if action_id:
        relations.append(TimelineObjectRelation(object_ref=f"action://{action_id}", object_kind=TimelineObjectKind.ACTION, qualifier=TimelineObjectQualifier.CONTEXT))

    return build_timeline_event(
        event_id=f"outcome:{assertion.assertion_id}:{outcome.metric_key}",
        event_type="eay.outcome.metric",
        event_kind=TimelineEventKind.OUTCOME,
        source_ref=assertion.source_ref,
        tenant_id=tenant_id,
        occurred_at=outcome.observed_at,
        observed_at=outcome.observed_at,
        effective_from=assertion.valid_from,
        effective_until=assertion.valid_to,
        data_ref=assertion_ref,
        authority_class=TimelineAuthorityClass.VERIFIED_OUTCOME,
        confidence=assertion.confidence,
        object_relations=tuple(relations),
        evidence_refs=tuple(dict.fromkeys((*outcome.evidence_refs, outcome.governed_truth_ref, assertion.evidence_ref))),
        tags=(outcome.metric_key, outcome.unit),
    )


def device_world_snapshot_events(snapshot: DeviceWorldSnapshot) -> tuple[RealWorldTimelineEvent, ...]:
    """Project devices as observations only; never copy transport material."""

    events = []
    for node in snapshot.devices:
        if node.observed_at > snapshot.observed_at:
            raise ValueError("timeline_device_observation_from_future_snapshot")
        relations = [TimelineObjectRelation(object_ref=f"device://{node.device_ref}", object_kind=TimelineObjectKind.DEVICE, qualifier=TimelineObjectQualifier.SUBJECT)]
        if node.room_ref:
            relations.append(TimelineObjectRelation(object_ref=f"location://{node.room_ref}", object_kind=TimelineObjectKind.LOCATION, qualifier=TimelineObjectQualifier.LOCATION))
        evidence = list(snapshot.source_evidence_refs)
        if node.identity_evidence_ref:
            evidence.append(node.identity_evidence_ref)
        tags = [node.device_class.value, node.trust.value, "online" if node.online else "offline"]
        confidence = _DEVICE_CONFIDENCE[node.trust]
        if node.attestation_expires_at is not None and snapshot.observed_at > node.attestation_expires_at:
            tags.append("attestation_expired")
            confidence = min(confidence, 0.50)
        events.append(build_timeline_event(
            event_id=f"device:{node.device_ref}:{node.observed_at.isoformat()}",
            event_type="eay.device.observation",
            event_kind=TimelineEventKind.DEVICE_OBSERVATION,
            source_ref="eay://device-world-model",
            tenant_id=snapshot.tenant_ref,
            occurred_at=node.observed_at,
            observed_at=snapshot.observed_at,
            data_ref=f"device-world://{snapshot.tenant_ref}/{node.device_ref}",
            authority_class=TimelineAuthorityClass.DEVICE_OBSERVATION,
            confidence=confidence,
            object_relations=tuple(relations),
            evidence_refs=tuple(dict.fromkeys(evidence)),
            tags=tuple(tags),
        ))
    return tuple(events)


def _objects(event: RealWorldTimelineEvent, kind: TimelineObjectKind) -> set[str]:
    return {item.object_ref for item in event.object_relations if item.object_kind is kind}


def action_executes_decision_link(*, action: RealWorldTimelineEvent, decision: RealWorldTimelineEvent) -> TimelineEventLink:
    action = validate_timeline_event_integrity(action)
    decision = validate_timeline_event_integrity(decision)
    if action.event_kind is not TimelineEventKind.ACTION or decision.event_kind is not TimelineEventKind.DECISION:
        raise ValueError("timeline_action_decision_link_kind_mismatch")
    if action.tenant_id != decision.tenant_id:
        raise ValueError("timeline_action_link_cross_tenant_forbidden")
    if action.occurred_at < decision.occurred_at:
        raise ValueError("timeline_action_cannot_precede_decision")
    if not (_objects(action, TimelineObjectKind.DECISION) & _objects(decision, TimelineObjectKind.DECISION)):
        raise ValueError("timeline_action_decision_object_identity_mismatch")
    return TimelineEventLink(
        tenant_id=action.tenant_id,
        source_event_id=action.event_id,
        relation=TimelineRelationKind.ACTION_EXECUTES_DECISION,
        target_event_id=decision.event_id,
        evidence_refs=tuple(dict.fromkeys((*decision.evidence_refs, *action.evidence_refs))),
        confidence=min(action.confidence, decision.confidence),
    )


def outcome_follows_action_link(*, outcome: RealWorldTimelineEvent, action: RealWorldTimelineEvent) -> TimelineEventLink:
    outcome = validate_timeline_event_integrity(outcome)
    action = validate_timeline_event_integrity(action)
    if outcome.event_kind is not TimelineEventKind.OUTCOME or action.event_kind is not TimelineEventKind.ACTION:
        raise ValueError("timeline_outcome_action_link_kind_mismatch")
    if outcome.tenant_id != action.tenant_id:
        raise ValueError("timeline_outcome_link_cross_tenant_forbidden")
    if outcome.occurred_at < action.occurred_at:
        raise ValueError("timeline_outcome_cannot_precede_action")
    if not (_objects(outcome, TimelineObjectKind.ACTION) & _objects(action, TimelineObjectKind.ACTION)):
        raise ValueError("timeline_outcome_action_object_identity_mismatch")
    return TimelineEventLink(
        tenant_id=outcome.tenant_id,
        source_event_id=outcome.event_id,
        relation=TimelineRelationKind.OUTCOME_FOLLOWS_ACTION,
        target_event_id=action.event_id,
        evidence_refs=tuple(dict.fromkeys((*action.evidence_refs, *outcome.evidence_refs))),
        confidence=min(outcome.confidence, action.confidence),
    )
