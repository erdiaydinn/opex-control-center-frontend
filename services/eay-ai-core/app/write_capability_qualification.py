"""Controlled write-capability qualification for Jarvis computer use.

Read-only onboarding is the prerequisite for learning a mutating enterprise
workflow. A write procedure can become deterministic-replay eligible only
after a validated read foundation, exact environment binding, repeated
identity-authorized executions, unique idempotency keys and independently
verified business effects.

"Direct replay" means the healthy UI/API trajectory no longer needs model
exploration. It never means authorization-free or verification-free execution.
The executable capability reference and the policy permission are kept
separate, and every write is bound to the exact risk and idempotency key present
in its authorization envelope.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator

from .command_authorization import (
    ActionRisk,
    AuthorizationDisposition,
    CommandAuthorizationEnvelope,
)
from .mission_execution import CapabilityExecutionOutcome
from .procedural_memory import (
    ProcedureDemonstration,
    ProceduralCapability,
    ProcedureStatus,
    ProcedureStep,
    compile_procedure,
    procedure_step_fingerprint,
)

WRITE_CAPABILITY_QUALIFICATION_CONTRACT = "eay-write-capability-qualification-v1"


class WriteQualificationStatus(str, Enum):
    CANDIDATE = "candidate"
    QUALIFIED = "qualified"
    BLOCKED = "blocked"


class WriteCapabilityCandidate(BaseModel):
    contract: str = WRITE_CAPABILITY_QUALIFICATION_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    application_id: str = Field(min_length=1)
    tenant_scope_ref: str = Field(min_length=1)
    capability_name: str = Field(min_length=1)
    execution_capability_ref: str = Field(min_length=1)
    required_permission: str = Field(min_length=1)
    target_scope_ref: str = Field(min_length=1)
    risk: ActionRisk
    environment_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    read_foundation_capability_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    procedure_steps: tuple[ProcedureStep, ...] = Field(min_length=1)
    minimum_verified_writes: int = Field(default=2, ge=2, le=20)
    status: WriteQualificationStatus = WriteQualificationStatus.CANDIDATE
    deterministic_replay_allowed: bool = False
    authorization_required_every_execution: bool = True
    effect_verification_required_every_execution: bool = True

    @model_validator(mode="after")
    def candidate_preserves_write_boundaries(self) -> "WriteCapabilityCandidate":
        if not any(step.side_effect for step in self.procedure_steps):
            raise ValueError("write_capability_candidate_requires_side_effect_step")
        if self.deterministic_replay_allowed:
            raise ValueError("unqualified_write_candidate_cannot_allow_replay")
        if not self.authorization_required_every_execution:
            raise ValueError("write_capability_always_requires_authorization")
        if not self.effect_verification_required_every_execution:
            raise ValueError("write_capability_always_requires_effect_verification")
        return self


class WriteQualificationDemonstration(BaseModel):
    contract: str = WRITE_CAPABILITY_QUALIFICATION_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    demonstration: ProcedureDemonstration
    command_id: str = Field(min_length=1)
    authorization_evidence_ref: str = Field(min_length=1)
    target_scope_ref: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    transaction_ref: str | None = None


class QualifiedWriteCapability(BaseModel):
    contract: str = WRITE_CAPABILITY_QUALIFICATION_CONTRACT
    candidate_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    application_id: str
    tenant_scope_ref: str
    capability_name: str
    execution_capability_ref: str
    required_permission: str
    target_scope_ref: str
    risk: ActionRisk
    read_foundation_capability_id: str = Field(pattern=r"^[0-9a-f]{64}$")
    procedure: ProceduralCapability
    status: WriteQualificationStatus
    deterministic_replay_allowed: bool
    authorization_required_every_execution: bool = True
    effect_verification_required_every_execution: bool = True
    additional_approval_required_every_execution: bool = False
    execution_without_fresh_authorization_allowed: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def qualification_never_bypasses_controls(self) -> "QualifiedWriteCapability":
        if self.execution_without_fresh_authorization_allowed:
            raise ValueError("qualified_write_never_allows_authorization_free_execution")
        if not self.authorization_required_every_execution:
            raise ValueError("qualified_write_requires_fresh_authorization")
        if not self.effect_verification_required_every_execution:
            raise ValueError("qualified_write_requires_effect_verification")
        if self.deterministic_replay_allowed:
            if self.status is not WriteQualificationStatus.QUALIFIED:
                raise ValueError("write_replay_requires_qualified_status")
            if self.procedure.status is not ProcedureStatus.VALIDATED:
                raise ValueError("write_replay_requires_validated_procedure")
            if self.blockers:
                raise ValueError("write_replay_cannot_ignore_blockers")
        return self


class WriteReplayPreflight(BaseModel):
    contract: str = WRITE_CAPABILITY_QUALIFICATION_CONTRACT
    capability_name: str
    execution_capability_ref: str
    required_permission: str
    procedure_capability_id: str
    idempotency_key: str | None = None
    allowed: bool
    authorization_evidence_ref: str | None = None
    effect_verification_required: bool = True
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def allowed_preflight_requires_authorization(self) -> "WriteReplayPreflight":
        if self.allowed:
            if not self.authorization_evidence_ref:
                raise ValueError("write_replay_preflight_requires_authorization_evidence")
            if not self.idempotency_key:
                raise ValueError("write_replay_preflight_requires_idempotency_key")
            if self.blockers:
                raise ValueError("write_replay_preflight_cannot_ignore_blockers")
        if not self.effect_verification_required:
            raise ValueError("write_replay_preflight_always_requires_effect_verification")
        return self


def _candidate_id(
    *,
    application_id: str,
    tenant_scope_ref: str,
    capability_name: str,
    execution_capability_ref: str,
    required_permission: str,
    target_scope_ref: str,
    environment_fingerprint: str,
    read_foundation_capability_id: str,
    steps: tuple[ProcedureStep, ...],
) -> str:
    payload = {
        "contract": WRITE_CAPABILITY_QUALIFICATION_CONTRACT,
        "application_id": application_id,
        "tenant_scope_ref": tenant_scope_ref,
        "capability_name": capability_name,
        "execution_capability_ref": execution_capability_ref,
        "required_permission": required_permission,
        "target_scope_ref": target_scope_ref,
        "environment_fingerprint": environment_fingerprint,
        "read_foundation_capability_id": read_foundation_capability_id,
        "step_fingerprint": procedure_step_fingerprint(steps),
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def build_write_capability_candidate(
    *,
    application_id: str,
    read_foundation: ProceduralCapability,
    capability_name: str,
    execution_capability_ref: str,
    required_permission: str,
    target_scope_ref: str,
    risk: ActionRisk,
    procedure_steps: tuple[ProcedureStep, ...],
    minimum_verified_writes: int = 2,
) -> WriteCapabilityCandidate:
    if read_foundation.status is not ProcedureStatus.VALIDATED:
        raise ValueError("write_qualification_requires_validated_read_foundation")
    if not read_foundation.direct_execution_allowed or read_foundation.requires_revalidation:
        raise ValueError("write_qualification_read_foundation_not_reusable")
    if any(step.side_effect for step in read_foundation.steps):
        raise ValueError("write_qualification_foundation_must_be_read_only")
    if read_foundation.environment_fingerprint == "0" * 64:
        raise ValueError("write_qualification_foundation_environment_unverified")
    identity_fields = (
        capability_name,
        execution_capability_ref,
        required_permission,
        target_scope_ref,
    )
    if any(not item.strip() for item in identity_fields):
        raise ValueError("write_qualification_identity_fields_required")

    return WriteCapabilityCandidate(
        candidate_id=_candidate_id(
            application_id=application_id,
            tenant_scope_ref=read_foundation.tenant_id,
            capability_name=capability_name,
            execution_capability_ref=execution_capability_ref,
            required_permission=required_permission,
            target_scope_ref=target_scope_ref,
            environment_fingerprint=read_foundation.environment_fingerprint,
            read_foundation_capability_id=read_foundation.capability_id,
            steps=procedure_steps,
        ),
        application_id=application_id,
        tenant_scope_ref=read_foundation.tenant_id,
        capability_name=capability_name,
        execution_capability_ref=execution_capability_ref,
        required_permission=required_permission,
        target_scope_ref=target_scope_ref,
        risk=risk,
        environment_fingerprint=read_foundation.environment_fingerprint,
        read_foundation_capability_id=read_foundation.capability_id,
        procedure_steps=procedure_steps,
        minimum_verified_writes=minimum_verified_writes,
    )


def create_controlled_write_demonstration(
    *,
    candidate: WriteCapabilityCandidate,
    demonstration_id: str,
    observed_at: datetime,
    observed_environment_fingerprint: str,
    authorization: CommandAuthorizationEnvelope,
    idempotency_key: str,
    outcome: CapabilityExecutionOutcome,
    evidence_refs: tuple[str, ...] = (),
) -> WriteQualificationDemonstration:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("write_demonstration_requires_timezone")
    if observed_environment_fingerprint != candidate.environment_fingerprint:
        raise ValueError("write_demonstration_environment_mismatch")
    if authorization.disposition is not AuthorizationDisposition.ALLOW_FROM_COMMAND:
        raise ValueError("write_demonstration_requires_allowed_command_authorization")
    if not authorization.command_counts_as_approval or not authorization.authorization_evidence_ref:
        raise ValueError("write_demonstration_requires_authorization_evidence")
    if authorization.tenant_ref != candidate.tenant_scope_ref:
        raise ValueError("write_demonstration_tenant_mismatch")
    if authorization.capability_ref != candidate.execution_capability_ref:
        raise ValueError("write_demonstration_capability_mismatch")
    if authorization.target_scope_ref != candidate.target_scope_ref:
        raise ValueError("write_demonstration_target_scope_mismatch")
    if authorization.risk != candidate.risk:
        raise ValueError("write_demonstration_risk_authorization_mismatch")
    if not idempotency_key.strip():
        raise ValueError("write_demonstration_requires_idempotency_key")
    if authorization.idempotency_key != idempotency_key:
        raise ValueError("write_demonstration_idempotency_authorization_mismatch")

    combined_evidence = tuple(
        dict.fromkeys(
            (
                authorization.authorization_evidence_ref,
                *evidence_refs,
                *outcome.evidence_refs,
                *(() if outcome.transaction_ref is None else (outcome.transaction_ref,)),
            )
        )
    )
    demonstration = ProcedureDemonstration(
        demonstration_id=demonstration_id,
        tenant_id=candidate.tenant_scope_ref,
        capability_name=candidate.capability_name,
        observed_at=observed_at,
        step_fingerprint=procedure_step_fingerprint(candidate.procedure_steps),
        successful=outcome.succeeded,
        effect_verified=outcome.effect_verified,
        ambiguous_outcome=outcome.ambiguous_outcome,
        environment_fingerprint=observed_environment_fingerprint,
        evidence_refs=combined_evidence,
    )
    return WriteQualificationDemonstration(
        candidate_id=candidate.candidate_id,
        demonstration=demonstration,
        command_id=authorization.command_id,
        authorization_evidence_ref=authorization.authorization_evidence_ref,
        target_scope_ref=authorization.target_scope_ref,
        idempotency_key=idempotency_key,
        transaction_ref=outcome.transaction_ref,
    )


def compile_qualified_write_capability(
    *,
    candidate: WriteCapabilityCandidate,
    read_foundation: ProceduralCapability,
    demonstrations: list[WriteQualificationDemonstration],
    version: int = 1,
) -> QualifiedWriteCapability:
    blockers: list[str] = []
    if read_foundation.capability_id != candidate.read_foundation_capability_id:
        blockers.append("write_qualification_read_foundation_identity_mismatch")
    if read_foundation.tenant_id != candidate.tenant_scope_ref:
        blockers.append("write_qualification_read_foundation_tenant_mismatch")
    if read_foundation.environment_fingerprint != candidate.environment_fingerprint:
        blockers.append("write_qualification_read_foundation_environment_drift")
    if read_foundation.status is not ProcedureStatus.VALIDATED or not read_foundation.direct_execution_allowed:
        blockers.append("write_qualification_read_foundation_not_validated")

    relevant = [item for item in demonstrations if item.candidate_id == candidate.candidate_id]
    foreign = [item for item in demonstrations if item.candidate_id != candidate.candidate_id]
    if foreign:
        blockers.append("write_qualification_contains_foreign_demonstration")

    verified = [
        item
        for item in relevant
        if item.demonstration.successful
        and item.demonstration.effect_verified
        and not item.demonstration.ambiguous_outcome
    ]
    if len(verified) < candidate.minimum_verified_writes:
        blockers.append("write_qualification_verified_demonstrations_insufficient")

    verified_idempotency_keys = [item.idempotency_key for item in verified]
    if len(verified_idempotency_keys) != len(set(verified_idempotency_keys)):
        blockers.append("write_qualification_verified_idempotency_not_independent")
    verified_authorizations = [item.authorization_evidence_ref for item in verified]
    if len(verified_authorizations) != len(set(verified_authorizations)):
        blockers.append("write_qualification_verified_authorizations_not_independent")
    verified_transactions = [item.transaction_ref for item in verified]
    if any(item is None for item in verified_transactions):
        blockers.append("write_qualification_verified_transaction_ref_missing")
    elif len(verified_transactions) != len(set(verified_transactions)):
        blockers.append("write_qualification_verified_transactions_not_independent")
    if any(item.demonstration.ambiguous_outcome for item in relevant):
        blockers.append("write_qualification_contains_ambiguous_demonstration")

    procedure = compile_procedure(
        tenant_id=candidate.tenant_scope_ref,
        capability_name=candidate.capability_name,
        steps=candidate.procedure_steps,
        demonstrations=[item.demonstration for item in relevant],
        version=version,
        minimum_verified_demonstrations=candidate.minimum_verified_writes,
    )
    blockers.extend(procedure.blockers)
    blockers = list(dict.fromkeys(blockers))

    qualified = not blockers and procedure.status is ProcedureStatus.VALIDATED
    return QualifiedWriteCapability(
        candidate_id=candidate.candidate_id,
        application_id=candidate.application_id,
        tenant_scope_ref=candidate.tenant_scope_ref,
        capability_name=candidate.capability_name,
        execution_capability_ref=candidate.execution_capability_ref,
        required_permission=candidate.required_permission,
        target_scope_ref=candidate.target_scope_ref,
        risk=candidate.risk,
        read_foundation_capability_id=candidate.read_foundation_capability_id,
        procedure=procedure,
        status=(WriteQualificationStatus.QUALIFIED if qualified else WriteQualificationStatus.BLOCKED),
        deterministic_replay_allowed=qualified,
        additional_approval_required_every_execution=candidate.risk in {ActionRisk.HIGH, ActionRisk.CRITICAL},
        blockers=tuple(blockers),
    )


def preflight_qualified_write_replay(
    *,
    capability: QualifiedWriteCapability,
    authorization: CommandAuthorizationEnvelope,
    observed_environment_fingerprint: str,
    expected_idempotency_key: str,
) -> WriteReplayPreflight:
    blockers: list[str] = []
    if not expected_idempotency_key.strip():
        blockers.append("write_replay_expected_idempotency_missing")
    if not capability.deterministic_replay_allowed:
        blockers.append("write_replay_capability_not_qualified")
    if capability.procedure.status is not ProcedureStatus.VALIDATED:
        blockers.append("write_replay_procedure_not_validated")
    if observed_environment_fingerprint != capability.procedure.environment_fingerprint:
        blockers.append("write_replay_environment_drift")
    if capability.additional_approval_required_every_execution:
        blockers.append("write_replay_additional_approval_required")
    if authorization.disposition is not AuthorizationDisposition.ALLOW_FROM_COMMAND:
        blockers.append("write_replay_fresh_authorization_not_allowed")
    if not authorization.command_counts_as_approval or not authorization.authorization_evidence_ref:
        blockers.append("write_replay_fresh_authorization_evidence_missing")
    if authorization.tenant_ref != capability.tenant_scope_ref:
        blockers.append("write_replay_tenant_mismatch")
    if authorization.capability_ref != capability.execution_capability_ref:
        blockers.append("write_replay_capability_mismatch")
    if authorization.target_scope_ref != capability.target_scope_ref:
        blockers.append("write_replay_target_scope_mismatch")
    if authorization.risk != capability.risk:
        blockers.append("write_replay_risk_authorization_mismatch")
    if authorization.idempotency_key != expected_idempotency_key:
        blockers.append("write_replay_idempotency_authorization_mismatch")

    blockers = list(dict.fromkeys(blockers))
    return WriteReplayPreflight(
        capability_name=capability.capability_name,
        execution_capability_ref=capability.execution_capability_ref,
        required_permission=capability.required_permission,
        procedure_capability_id=capability.procedure.capability_id,
        idempotency_key=(expected_idempotency_key if not blockers else None),
        allowed=not blockers,
        authorization_evidence_ref=(authorization.authorization_evidence_ref if not blockers else None),
        blockers=tuple(blockers),
    )
