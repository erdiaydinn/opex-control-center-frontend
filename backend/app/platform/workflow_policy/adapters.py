from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable

from pydantic import Field, model_validator

from .engine import WorkflowPolicyError, authorize_action_execution
from .models import (
    ActionEffect,
    ActionIntent,
    ActionType,
    ApprovalDecisionType,
    ExecutionMode,
    StrictFrozenModel,
    ActionApprovalDecision,
)


class RegisteredActionAdapter(StrictFrozenModel):
    """Platform-registered handoff contract, not an arbitrary endpoint descriptor.

    Provider URLs, credentials and executable code are intentionally absent.
    The adapter points to a named internal capability that must re-apply its
    owning domain's authorization and validation before any mutation occurs.
    """

    adapter_id: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.-]+$")
    action_key: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.-]+$")
    action_type: ActionType
    target_module: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_.-]+$")
    capability: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")
    allowed_effects: frozenset[ActionEffect] = Field(min_length=1, max_length=5)
    allowed_execution_modes: frozenset[ExecutionMode] = Field(min_length=1, max_length=3)
    required_permission: str | None = Field(default=None, max_length=220)
    domain_guard_id: str = Field(min_length=1, max_length=180, pattern=r"^[a-zA-Z0-9_.:-]+$")
    idempotency_required: bool = True
    enabled: bool = True

    @model_validator(mode="after")
    def validate_registration(self) -> "RegisteredActionAdapter":
        if ExecutionMode.AUTOMATIC in self.allowed_execution_modes and any(
            effect in {ActionEffect.FINANCIAL, ActionEffect.EMPLOYMENT, ActionEffect.SECURITY}
            for effect in self.allowed_effects
        ):
            raise ValueError("registered adapter cannot authorize automatic high-risk execution")
        if self.action_type is ActionType.PROPOSE_DOMAIN_ACTION and ExecutionMode.AUTOMATIC in self.allowed_execution_modes:
            raise ValueError("domain-action adapter cannot authorize automatic mutation")
        if self.required_permission is not None and not self.required_permission.strip():
            raise ValueError("required permission cannot be blank")
        return self


class AdapterHandoff(StrictFrozenModel):
    tenant_id: str
    handoff_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    intent_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    dedupe_key: str = Field(pattern=r"^[a-f0-9]{64}$")
    adapter_id: str
    target_module: str
    capability: str
    domain_guard_id: str
    action_key: str
    action_type: ActionType
    effect: ActionEffect
    execution_mode: ExecutionMode
    parameters: dict[str, str | int | float | bool | None]
    permission_evidence: str | None = None
    decision_id: str | None = None


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _matching_adapters(
    intent: ActionIntent,
    registrations: Iterable[RegisteredActionAdapter],
) -> tuple[RegisteredActionAdapter, ...]:
    return tuple(
        adapter
        for adapter in registrations
        if adapter.enabled
        and adapter.action_key == intent.action_key
        and adapter.action_type is intent.action_type
        and intent.effect in adapter.allowed_effects
        and intent.execution_mode in adapter.allowed_execution_modes
    )


def resolve_registered_adapter(
    intent: ActionIntent,
    registrations: Iterable[RegisteredActionAdapter],
) -> RegisteredActionAdapter:
    """Resolve exactly one registered adapter or fail closed."""
    matches = _matching_adapters(intent, registrations)
    if not matches:
        raise WorkflowPolicyError("no registered adapter matches workflow action intent")
    if len(matches) > 1:
        raise WorkflowPolicyError("ambiguous registered adapter matches workflow action intent")
    return matches[0]


def prepare_adapter_handoff(
    intent: ActionIntent,
    registrations: Iterable[RegisteredActionAdapter],
    *,
    granted_permissions: frozenset[str] = frozenset(),
    decision: ActionApprovalDecision | None = None,
) -> AdapterHandoff:
    """Create a deterministic internal handoff after generic policy safety checks.

    This function does not call a provider or mutate a target module. The target
    adapter still has to enforce `domain_guard_id` using the authoritative module.
    """
    authorize_action_execution(intent, decision)
    adapter = resolve_registered_adapter(intent, registrations)

    if adapter.required_permission is not None and adapter.required_permission not in granted_permissions:
        raise WorkflowPolicyError("required adapter permission is missing")
    if not adapter.domain_guard_id:
        raise WorkflowPolicyError("registered adapter is missing authoritative domain guard")
    if adapter.idempotency_required and not intent.dedupe_key:
        raise WorkflowPolicyError("registered adapter requires an idempotency key")

    permission_evidence = (
        _fingerprint(sorted(granted_permissions)) if adapter.required_permission is not None else None
    )
    payload = {
        "tenant_id": intent.tenant_id,
        "intent_id": intent.intent_id,
        "dedupe_key": intent.dedupe_key,
        "adapter_id": adapter.adapter_id,
        "target_module": adapter.target_module,
        "capability": adapter.capability,
        "domain_guard_id": adapter.domain_guard_id,
        "action_key": intent.action_key,
        "action_type": intent.action_type.value,
        "effect": intent.effect.value,
        "execution_mode": intent.execution_mode.value,
        "parameters": intent.parameters,
        "permission_evidence": permission_evidence,
        "decision_id": decision.decision_id if decision is not None else None,
    }
    return AdapterHandoff(
        tenant_id=intent.tenant_id,
        handoff_id=_fingerprint(payload),
        intent_id=intent.intent_id,
        dedupe_key=intent.dedupe_key,
        adapter_id=adapter.adapter_id,
        target_module=adapter.target_module,
        capability=adapter.capability,
        domain_guard_id=adapter.domain_guard_id,
        action_key=intent.action_key,
        action_type=intent.action_type,
        effect=intent.effect,
        execution_mode=intent.execution_mode,
        parameters=intent.parameters,
        permission_evidence=permission_evidence,
        decision_id=decision.decision_id if decision is not None else None,
    )
