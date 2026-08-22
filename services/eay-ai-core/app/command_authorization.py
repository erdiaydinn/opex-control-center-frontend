"""Identity-bound single-command authorization for Jarvis enterprise actions.

A user should not be asked to confirm every routine action twice. This module
lets the user's authenticated command itself satisfy authorization when the
action is already inside a narrow pre-authorized envelope: exact principal,
tenant, capability, target scope, reason, quantity/value limits and validity
window.

The command is never blanket authority. High/critical, bulk, irreversible or
out-of-envelope actions require additional approval or fail closed. Side-effect
authorization is bound to the exact idempotency key used by the mission, and
the authorized risk class is retained as non-secret provenance so downstream
write qualification cannot learn a HIGH procedure from a LOW-risk artifact.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from enum import Enum
from typing import Iterable

from pydantic import BaseModel, Field, model_validator

from .mission_execution import AuthorizationDecision, AuthorizationChecker
from .mission_runtime import MissionDefinition, MissionStep

COMMAND_AUTHORIZATION_CONTRACT = "eay-command-authorization-v1"


class ActionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AuthorizationDisposition(str, Enum):
    ALLOW_FROM_COMMAND = "allow_from_command"
    REQUIRE_ADDITIONAL_APPROVAL = "require_additional_approval"
    DENY = "deny"


class CommandAuthorizationPolicy(BaseModel):
    policy_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    allowed_capabilities: frozenset[str] = Field(min_length=1)
    allowed_target_scopes: frozenset[str] = Field(min_length=1)
    allowed_reason_codes: frozenset[str] = frozenset()
    max_absolute_quantity: float | None = Field(default=None, gt=0.0)
    max_financial_value: float | None = Field(default=None, gt=0.0)
    valid_from: datetime
    valid_until: datetime
    command_authorization_max_risk: ActionRisk = ActionRisk.MEDIUM

    @model_validator(mode="after")
    def policy_window_and_identity_are_valid(self) -> "CommandAuthorizationPolicy":
        if self.valid_from.tzinfo is None or self.valid_from.utcoffset() is None:
            raise ValueError("command_authorization_policy_requires_timezone")
        if self.valid_until.tzinfo is None or self.valid_until.utcoffset() is None:
            raise ValueError("command_authorization_policy_requires_timezone")
        if self.valid_until <= self.valid_from:
            raise ValueError("command_authorization_policy_window_invalid")
        if self.command_authorization_max_risk in {ActionRisk.HIGH, ActionRisk.CRITICAL}:
            raise ValueError("command_authorization_cannot_preapprove_high_or_critical_risk")
        return self


class IdentityBoundCommand(BaseModel):
    command_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    principal_ref: str = Field(min_length=1)
    identity_evidence_ref: str = Field(min_length=1)
    tenant_ref: str = Field(min_length=1)
    capability_ref: str = Field(min_length=1)
    target_scope_ref: str = Field(min_length=1)
    issued_at: datetime
    risk: ActionRisk
    side_effect: bool = True
    idempotency_key: str | None = None
    reason_code: str | None = None
    absolute_quantity: float | None = Field(default=None, ge=0.0)
    financial_value: float | None = Field(default=None, ge=0.0)
    bulk: bool = False
    irreversible: bool = False

    @model_validator(mode="after")
    def command_requires_time_and_idempotency(self) -> "IdentityBoundCommand":
        if self.issued_at.tzinfo is None or self.issued_at.utcoffset() is None:
            raise ValueError("identity_bound_command_requires_timezone")
        if self.side_effect and not (self.idempotency_key or "").strip():
            raise ValueError("identity_bound_side_effect_requires_idempotency_key")
        return self


class CommandAuthorizationEnvelope(BaseModel):
    contract: str = COMMAND_AUTHORIZATION_CONTRACT
    command_id: str
    mission_id: str
    step_id: str
    principal_ref: str
    tenant_ref: str
    capability_ref: str
    target_scope_ref: str
    risk: ActionRisk | None = None
    idempotency_key: str | None = None
    disposition: AuthorizationDisposition
    authorization_evidence_ref: str | None = None
    command_counts_as_approval: bool = False
    blockers: tuple[str, ...] = ()

    @model_validator(mode="after")
    def allowed_envelope_requires_evidence_and_no_blockers(self) -> "CommandAuthorizationEnvelope":
        if self.disposition is AuthorizationDisposition.ALLOW_FROM_COMMAND:
            if not self.authorization_evidence_ref:
                raise ValueError("allowed_command_authorization_requires_evidence_ref")
            if self.blockers:
                raise ValueError("allowed_command_authorization_cannot_have_blockers")
            if not self.command_counts_as_approval:
                raise ValueError("allowed_command_must_count_as_approval")
        elif self.command_counts_as_approval:
            raise ValueError("blocked_command_cannot_count_as_approval")
        return self


def _risk_rank(risk: ActionRisk) -> int:
    return {
        ActionRisk.LOW: 0,
        ActionRisk.MEDIUM: 1,
        ActionRisk.HIGH: 2,
        ActionRisk.CRITICAL: 3,
    }[risk]


def _evidence_ref(
    policy: CommandAuthorizationPolicy,
    command: IdentityBoundCommand,
) -> str:
    payload = {
        "contract": COMMAND_AUTHORIZATION_CONTRACT,
        "policy_id": policy.policy_id,
        "command_id": command.command_id,
        "mission_id": command.mission_id,
        "step_id": command.step_id,
        "principal_ref": command.principal_ref,
        "identity_evidence_ref": command.identity_evidence_ref,
        "tenant_ref": command.tenant_ref,
        "capability_ref": command.capability_ref,
        "target_scope_ref": command.target_scope_ref,
        "issued_at": command.issued_at.isoformat(),
        "risk": command.risk.value,
        "idempotency_key": command.idempotency_key,
        "reason_code": command.reason_code,
        "absolute_quantity": command.absolute_quantity,
        "financial_value": command.financial_value,
        "bulk": command.bulk,
        "irreversible": command.irreversible,
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"command-authz://{digest}"


def authorize_identity_bound_command(
    *,
    policy: CommandAuthorizationPolicy,
    command: IdentityBoundCommand,
) -> CommandAuthorizationEnvelope:
    deny: list[str] = []
    approval: list[str] = []

    if command.principal_ref != policy.principal_ref:
        deny.append("principal_mismatch")
    if command.identity_evidence_ref != policy.identity_evidence_ref:
        deny.append("identity_evidence_mismatch")
    if command.tenant_ref != policy.tenant_ref:
        deny.append("tenant_mismatch")
    if command.capability_ref not in policy.allowed_capabilities:
        deny.append("capability_not_allowed")
    if command.target_scope_ref not in policy.allowed_target_scopes:
        deny.append("target_scope_not_allowed")
    if not policy.valid_from <= command.issued_at <= policy.valid_until:
        deny.append("command_outside_policy_validity_window")
    if policy.allowed_reason_codes and command.reason_code not in policy.allowed_reason_codes:
        deny.append("reason_code_not_allowed")

    if _risk_rank(command.risk) > _risk_rank(policy.command_authorization_max_risk):
        approval.append("risk_requires_additional_approval")
    if command.risk in {ActionRisk.HIGH, ActionRisk.CRITICAL}:
        approval.append("high_or_critical_risk_requires_additional_approval")
    if command.bulk:
        approval.append("bulk_action_requires_additional_approval")
    if command.irreversible:
        approval.append("irreversible_action_requires_additional_approval")

    if policy.max_absolute_quantity is not None:
        if command.absolute_quantity is None:
            approval.append("quantity_missing_for_bounded_policy")
        elif command.absolute_quantity > policy.max_absolute_quantity:
            approval.append("quantity_limit_exceeded")
    if policy.max_financial_value is not None:
        if command.financial_value is None:
            approval.append("financial_value_missing_for_bounded_policy")
        elif command.financial_value > policy.max_financial_value:
            approval.append("financial_value_limit_exceeded")

    if deny:
        disposition = AuthorizationDisposition.DENY
        blockers = tuple(dict.fromkeys(deny))
        evidence_ref = None
    elif approval:
        disposition = AuthorizationDisposition.REQUIRE_ADDITIONAL_APPROVAL
        blockers = tuple(dict.fromkeys(approval))
        evidence_ref = None
    else:
        disposition = AuthorizationDisposition.ALLOW_FROM_COMMAND
        blockers = ()
        evidence_ref = _evidence_ref(policy, command)

    return CommandAuthorizationEnvelope(
        command_id=command.command_id,
        mission_id=command.mission_id,
        step_id=command.step_id,
        principal_ref=command.principal_ref,
        tenant_ref=command.tenant_ref,
        capability_ref=command.capability_ref,
        target_scope_ref=command.target_scope_ref,
        risk=command.risk,
        idempotency_key=command.idempotency_key,
        disposition=disposition,
        authorization_evidence_ref=evidence_ref,
        command_counts_as_approval=disposition is AuthorizationDisposition.ALLOW_FROM_COMMAND,
        blockers=blockers,
    )


def build_mission_command_authorization_checker(
    envelopes: Iterable[CommandAuthorizationEnvelope],
) -> AuthorizationChecker:
    """Bind command authorization evidence to its exact mission step/capability."""

    materialized = tuple(envelopes)
    index = {(item.mission_id, item.step_id): item for item in materialized}
    if len(index) != len(materialized):
        raise ValueError("duplicate_command_authorization_for_mission_step")

    async def checker(
        definition: MissionDefinition,
        step: MissionStep,
        capability_ref: str,
    ) -> AuthorizationDecision:
        envelope = index.get((definition.mission_id, step.step_id))
        if envelope is None:
            return AuthorizationDecision(
                allowed=False,
                reason_code="command_authorization_evidence_missing",
            )
        if envelope.capability_ref != capability_ref:
            return AuthorizationDecision(
                allowed=False,
                reason_code="command_authorization_capability_mismatch",
            )
        if step.side_effect and envelope.idempotency_key != step.idempotency_key:
            return AuthorizationDecision(
                allowed=False,
                reason_code="command_authorization_idempotency_mismatch",
            )
        if envelope.disposition is not AuthorizationDisposition.ALLOW_FROM_COMMAND:
            return AuthorizationDecision(
                allowed=False,
                reason_code=(envelope.blockers[0] if envelope.blockers else "command_authorization_blocked"),
            )
        return AuthorizationDecision(
            allowed=True,
            evidence_ref=envelope.authorization_evidence_ref,
        )

    return checker
