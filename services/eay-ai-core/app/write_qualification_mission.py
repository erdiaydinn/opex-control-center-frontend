"""Bridge completed durable missions into controlled write demonstrations.

A procedure-learning record must come from the same governed execution trace
that actually authorized and verified the write. This adapter refuses to learn
from a raw handler result or UI success signal. It requires a completed mission,
exact capability spec, exact permission/idempotency/effect-verifier binding,
the command authorization evidence in the step checkpoint, and the independent
transaction reference in that same checkpoint.
"""

from __future__ import annotations

from datetime import datetime

from .command_authorization import CommandAuthorizationEnvelope
from .mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
    MissionExecutionSummary,
)
from .mission_runtime import MissionDefinition, MissionStatus, StepStatus
from .write_capability_qualification import (
    WriteCapabilityCandidate,
    WriteQualificationDemonstration,
    create_controlled_write_demonstration,
)

WRITE_QUALIFICATION_MISSION_CONTRACT = "eay-write-qualification-mission-v1"


def create_write_demonstration_from_completed_mission(
    *,
    candidate: WriteCapabilityCandidate,
    definition: MissionDefinition,
    summary: MissionExecutionSummary,
    spec: MissionExecutionSpec,
    authorization: CommandAuthorizationEnvelope,
    observed_at: datetime,
    observed_environment_fingerprint: str,
    transaction_ref: str,
    demonstration_id: str,
) -> WriteQualificationDemonstration:
    if summary.checkpoint.status is not MissionStatus.COMPLETED:
        raise ValueError("write_qualification_mission_must_be_completed")
    if spec.kind is not MissionExecutionKind.CAPABILITY:
        raise ValueError("write_qualification_requires_capability_execution_spec")
    if spec.capability_ref != candidate.execution_capability_ref:
        raise ValueError("write_qualification_mission_capability_mismatch")

    steps = {item.step_id: item for item in definition.steps}
    step = steps.get(spec.step_id)
    if step is None:
        raise ValueError("write_qualification_mission_step_missing")
    if not step.side_effect:
        raise ValueError("write_qualification_mission_step_must_be_side_effect")
    if step.required_permission != candidate.required_permission:
        raise ValueError("write_qualification_mission_permission_mismatch")
    if step.idempotency_key != authorization.idempotency_key:
        raise ValueError("write_qualification_mission_idempotency_mismatch")

    accepted_verifiers = {
        item.effect_verifier_ref
        for item in candidate.procedure_steps
        if item.side_effect and item.effect_verifier_ref is not None
    }
    if step.effect_verifier_ref not in accepted_verifiers:
        raise ValueError("write_qualification_mission_effect_verifier_mismatch")

    states = {item.step_id: item for item in summary.checkpoint.steps}
    state = states.get(spec.step_id)
    if state is None:
        raise ValueError("write_qualification_mission_step_checkpoint_missing")
    # Mission-level completion and step-level success intentionally use
    # different enums. A write demonstration is valid only when its exact
    # side-effect step reached SUCCEEDED; mission COMPLETED alone is not enough.
    if state.status is not StepStatus.SUCCEEDED:
        raise ValueError("write_qualification_mission_step_not_completed")
    if state.last_error is not None:
        raise ValueError("write_qualification_mission_step_has_error")
    if state.ambiguous_outcome:
        raise ValueError("write_qualification_mission_step_ambiguous")

    evidence = tuple(state.evidence_refs)
    if not authorization.authorization_evidence_ref:
        raise ValueError("write_qualification_mission_authorization_evidence_missing")
    if authorization.authorization_evidence_ref not in evidence:
        raise ValueError("write_qualification_mission_authorization_not_in_checkpoint")
    if not transaction_ref.strip() or transaction_ref not in evidence:
        raise ValueError("write_qualification_mission_transaction_not_in_checkpoint")

    # MissionExecution records a side-effect step as SUCCEEDED only after the
    # governed capability path reports success and effect verification passes.
    # Rebuild the minimal controlled-write outcome from the checkpoint evidence,
    # never from UI text or a model's self-attestation.
    outcome = CapabilityExecutionOutcome(
        succeeded=True,
        effect_verified=True,
        ambiguous_outcome=False,
        evidence_refs=evidence,
        transaction_ref=transaction_ref,
    )
    return create_controlled_write_demonstration(
        candidate=candidate,
        demonstration_id=demonstration_id,
        observed_at=observed_at,
        observed_environment_fingerprint=observed_environment_fingerprint,
        authorization=authorization,
        idempotency_key=step.idempotency_key or "",
        outcome=outcome,
    )
