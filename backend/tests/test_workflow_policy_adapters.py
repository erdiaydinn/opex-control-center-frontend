from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.platform.workflow_policy.adapters import (
    RegisteredActionAdapter,
    prepare_adapter_handoff,
    resolve_registered_adapter,
)
from app.platform.workflow_policy.engine import WorkflowPolicyError
from app.platform.workflow_policy.models import (
    ActionApprovalDecision,
    ActionEffect,
    ActionIntent,
    ActionType,
    ApprovalDecisionType,
    ExecutionMode,
)


NOW = datetime(2026, 8, 16, 18, 0, tzinfo=UTC)


def intent(
    *,
    action_key: str = "notify.ops",
    action_type: ActionType = ActionType.NOTIFY,
    effect: ActionEffect = ActionEffect.INFORMATIONAL,
    execution_mode: ExecutionMode = ExecutionMode.AUTOMATIC,
    approval_required: bool = False,
    dry_run: bool = False,
) -> ActionIntent:
    return ActionIntent(
        tenant_id="tenant-a",
        intent_id="a" * 64,
        dedupe_key="b" * 64,
        workflow_id="workflow-1",
        workflow_version=2,
        event_id="event-1",
        rule_id="rule-1",
        action_key=action_key,
        action_type=action_type,
        effect=effect,
        execution_mode=execution_mode,
        parameters={"template_key": "late-order"},
        approval_required=approval_required,
        dry_run=dry_run,
    )


def adapter(
    *,
    adapter_id: str = "platform.notification",
    action_key: str = "notify.ops",
    action_type: ActionType = ActionType.NOTIFY,
    allowed_effects=frozenset({ActionEffect.INFORMATIONAL}),
    allowed_modes=frozenset({ExecutionMode.AUTOMATIC}),
    required_permission: str | None = None,
    target_module: str = "shared_services",
) -> RegisteredActionAdapter:
    return RegisteredActionAdapter(
        adapter_id=adapter_id,
        action_key=action_key,
        action_type=action_type,
        target_module=target_module,
        capability="notification.dispatch",
        allowed_effects=allowed_effects,
        allowed_execution_modes=allowed_modes,
        required_permission=required_permission,
        domain_guard_id="shared.notification.authority",
    )


def approved_decision(intent_id: str = "a" * 64, tenant_id: str = "tenant-a") -> ActionApprovalDecision:
    return ActionApprovalDecision(
        tenant_id=tenant_id,
        decision_id="decision-1",
        intent_id=intent_id,
        decision=ApprovalDecisionType.APPROVED,
        decided_by="manager-1",
        decided_at=NOW,
    )


def test_registered_adapter_resolves_exactly_once() -> None:
    item = intent()
    registration = adapter()
    assert resolve_registered_adapter(item, (registration,)) == registration


def test_unknown_or_ambiguous_adapter_fails_closed() -> None:
    item = intent()
    with pytest.raises(WorkflowPolicyError, match="no registered adapter"):
        resolve_registered_adapter(item, ())

    with pytest.raises(WorkflowPolicyError, match="ambiguous"):
        resolve_registered_adapter(
            item,
            (
                adapter(adapter_id="platform.notification.one"),
                adapter(adapter_id="platform.notification.two"),
            ),
        )


def test_disabled_or_effect_mismatched_adapter_does_not_match() -> None:
    item = intent()
    disabled = adapter().model_copy(update={"enabled": False})
    wrong_effect = adapter().model_copy(update={"allowed_effects": frozenset({ActionEffect.OPERATIONAL})})
    with pytest.raises(WorkflowPolicyError, match="no registered adapter"):
        resolve_registered_adapter(item, (disabled, wrong_effect))


def test_adapter_registration_cannot_enable_automatic_high_risk_execution() -> None:
    with pytest.raises(ValidationError, match="automatic high-risk"):
        adapter(
            allowed_effects=frozenset({ActionEffect.FINANCIAL}),
            allowed_modes=frozenset({ExecutionMode.AUTOMATIC}),
        )


def test_domain_action_adapter_cannot_enable_automatic_mutation() -> None:
    with pytest.raises(ValidationError, match="domain-action adapter"):
        adapter(
            action_type=ActionType.PROPOSE_DOMAIN_ACTION,
            allowed_effects=frozenset({ActionEffect.OPERATIONAL}),
            allowed_modes=frozenset({ExecutionMode.AUTOMATIC}),
        )


def test_adapter_handoff_requires_permission_when_registered() -> None:
    item = intent()
    registration = adapter(required_permission="action:shared_services:notify")
    with pytest.raises(WorkflowPolicyError, match="permission"):
        prepare_adapter_handoff(item, (registration,), granted_permissions=frozenset())

    handoff = prepare_adapter_handoff(
        item,
        (registration,),
        granted_permissions=frozenset({"action:shared_services:notify"}),
    )
    assert handoff.adapter_id == registration.adapter_id
    assert handoff.permission_evidence is not None
    assert handoff.handoff_id


def test_high_risk_handoff_requires_matching_approved_decision() -> None:
    item = intent(
        action_key="customer_promise.recovery.propose",
        action_type=ActionType.PROPOSE_DOMAIN_ACTION,
        effect=ActionEffect.FINANCIAL,
        execution_mode=ExecutionMode.REQUIRES_APPROVAL,
        approval_required=True,
    )
    registration = adapter(
        adapter_id="customer-promise.recovery-proposal",
        action_key="customer_promise.recovery.propose",
        action_type=ActionType.PROPOSE_DOMAIN_ACTION,
        allowed_effects=frozenset({ActionEffect.FINANCIAL}),
        allowed_modes=frozenset({ExecutionMode.REQUIRES_APPROVAL}),
        target_module="customer_promise",
    ).model_copy(update={"capability": "recovery.propose", "domain_guard_id": "customer_promise.recovery.authority"})

    with pytest.raises(WorkflowPolicyError, match="requires approval"):
        prepare_adapter_handoff(item, (registration,))

    handoff = prepare_adapter_handoff(item, (registration,), decision=approved_decision())
    assert handoff.target_module == "customer_promise"
    assert handoff.decision_id == "decision-1"


def test_cross_tenant_or_wrong_intent_decision_is_rejected() -> None:
    item = intent(
        action_key="customer_promise.recovery.propose",
        action_type=ActionType.PROPOSE_DOMAIN_ACTION,
        effect=ActionEffect.FINANCIAL,
        execution_mode=ExecutionMode.REQUIRES_APPROVAL,
        approval_required=True,
    )
    registration = RegisteredActionAdapter(
        adapter_id="customer-promise.recovery-proposal",
        action_key="customer_promise.recovery.propose",
        action_type=ActionType.PROPOSE_DOMAIN_ACTION,
        target_module="customer_promise",
        capability="recovery.propose",
        allowed_effects=frozenset({ActionEffect.FINANCIAL}),
        allowed_execution_modes=frozenset({ExecutionMode.REQUIRES_APPROVAL}),
        domain_guard_id="customer_promise.recovery.authority",
    )
    with pytest.raises(WorkflowPolicyError, match="tenant"):
        prepare_adapter_handoff(item, (registration,), decision=approved_decision(tenant_id="tenant-b"))
    with pytest.raises(WorkflowPolicyError, match="another action intent"):
        prepare_adapter_handoff(item, (registration,), decision=approved_decision(intent_id="c" * 64))


def test_dry_run_and_proposal_only_intents_never_handoff() -> None:
    registration = adapter()
    with pytest.raises(WorkflowPolicyError, match="dry-run"):
        prepare_adapter_handoff(intent(dry_run=True), (registration,))

    proposal = intent(execution_mode=ExecutionMode.PROPOSAL_ONLY)
    proposal_adapter = adapter(allowed_modes=frozenset({ExecutionMode.PROPOSAL_ONLY}))
    with pytest.raises(WorkflowPolicyError, match="proposal-only"):
        prepare_adapter_handoff(proposal, (proposal_adapter,))


def test_handoff_is_deterministic_and_contains_no_provider_endpoint() -> None:
    item = intent()
    registration = adapter()
    first = prepare_adapter_handoff(item, (registration,))
    second = prepare_adapter_handoff(item, (registration,))
    assert first == second
    serialized = first.model_dump(mode="json")
    assert "url" not in serialized
    assert "endpoint" not in serialized
    assert "secret" not in serialized
    assert "token" not in serialized
