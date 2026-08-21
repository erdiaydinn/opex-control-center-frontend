from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.platform.workflow_policy.engine import (
    WorkflowPolicyError,
    WorkflowPolicyResolutionError,
    authorize_action_execution,
    build_event_fingerprint,
    evaluate_workflow,
    resolve_effective_workflow,
    validate_next_workflow_version,
)
from app.platform.workflow_policy.models import (
    ActionApprovalDecision,
    ActionEffect,
    ActionTemplate,
    ActionType,
    ApprovalDecisionType,
    Condition,
    ConditionOperator,
    ExecutionMode,
    MatchMode,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowRule,
    WorkflowScope,
    WorkflowStatus,
)


BASE = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def event(*, facts=None, tenant_id="tenant-a", scope=None, event_type="customer_promise.deviation_detected") -> WorkflowEvent:
    payload = facts or {}
    return WorkflowEvent(
        tenant_id=tenant_id,
        event_id="evt-1",
        idempotency_key="workflow-event-0001",
        source_module="customer_promise",
        event_type=event_type,
        subject_ref="order-1",
        occurred_at=BASE + timedelta(minutes=10),
        scope=scope or WorkflowScope(country="TR", region="Marmara", location_id="store-1"),
        facts=payload,
        facts_fingerprint=build_event_fingerprint(payload),
    )


def definition(*, rules, **overrides) -> WorkflowDefinition:
    values = {
        "tenant_id": "tenant-a",
        "workflow_id": "late-order-recovery",
        "version": 1,
        "status": WorkflowStatus.EFFECTIVE,
        "source_module": "customer_promise",
        "event_type": "customer_promise.deviation_detected",
        "scope": WorkflowScope(country="TR"),
        "effective_from": BASE,
        "approved_by": "ops-owner",
        "approved_at": BASE - timedelta(minutes=5),
        "rules": tuple(rules),
    }
    values.update(overrides)
    return WorkflowDefinition(**values)


def notify_rule(*, rule_id="notify", priority=10, stop=False, group=None) -> WorkflowRule:
    return WorkflowRule(
        rule_id=rule_id,
        priority=priority,
        conditions=(Condition(fact_key="late_minutes", operator=ConditionOperator.GT, value=5),),
        actions=(
            ActionTemplate(
                action_key="notify.ops",
                action_type=ActionType.NOTIFY,
                effect=ActionEffect.INFORMATIONAL,
                execution_mode=ExecutionMode.AUTOMATIC,
                parameters={"template_id": "late-order"},
            ),
        ),
        exclusive_group=group,
        stop_processing=stop,
    )


def test_structural_security_events_can_name_token_or_authorization_without_payload_leak() -> None:
    evt = event(event_type="security.token_expired")
    assert evt.event_type == "security.token_expired"


def test_event_payload_rejects_raw_pii_secret_and_remote_execution_fields() -> None:
    for key in ("customer_email", "phone", "access_token", "command", "sql_query", "endpoint_url"):
        payload = {key: "forbidden"}
        with pytest.raises(ValidationError, match="not permitted"):
            WorkflowEvent(
                tenant_id="tenant-a",
                event_id="evt-forbidden",
                idempotency_key="forbidden-event-0001",
                source_module="inventory",
                event_type="inventory.exception",
                subject_ref="sku-1",
                occurred_at=BASE,
                facts=payload,
                facts_fingerprint=build_event_fingerprint(payload),
            )


def test_action_parameters_reject_arbitrary_endpoint_or_script_payloads() -> None:
    with pytest.raises(ValidationError, match="not permitted"):
        ActionTemplate(
            action_key="notify.ops",
            action_type=ActionType.NOTIFY,
            effect=ActionEffect.INFORMATIONAL,
            execution_mode=ExecutionMode.AUTOMATIC,
            parameters={"endpoint_url": "https://example.invalid"},
        )


def test_high_risk_or_domain_mutating_actions_cannot_be_automatic() -> None:
    with pytest.raises(ValidationError, match="high-risk"):
        ActionTemplate(
            action_key="refund.customer",
            action_type=ActionType.PROPOSE_DOMAIN_ACTION,
            effect=ActionEffect.FINANCIAL,
            execution_mode=ExecutionMode.AUTOMATIC,
        )
    with pytest.raises(ValidationError, match="domain mutation"):
        ActionTemplate(
            action_key="inventory.adjust",
            action_type=ActionType.PROPOSE_DOMAIN_ACTION,
            effect=ActionEffect.OPERATIONAL,
            execution_mode=ExecutionMode.AUTOMATIC,
        )


def test_missing_fact_fails_closed_instead_of_matching_not_equal_or_ordered_rules() -> None:
    wf = definition(rules=(notify_rule(),))
    result = evaluate_workflow(wf, event(facts={}), evaluated_at=BASE + timedelta(minutes=11))
    assert result.matched_rule_ids == ()
    assert result.action_intents == ()
    assert result.traces[0].condition_results[0].matched is False


def test_deterministic_priority_and_stop_processing() -> None:
    high = notify_rule(rule_id="high", priority=100, stop=True)
    low = notify_rule(rule_id="low", priority=10)
    wf = definition(rules=(low, high))
    result = evaluate_workflow(
        wf,
        event(facts={"late_minutes": 12}),
        evaluated_at=BASE + timedelta(minutes=11),
    )
    assert result.matched_rule_ids == ("high",)
    assert len(result.action_intents) == 1
    assert result.action_intents[0].rule_id == "high"


def test_any_match_mode_is_explicit_and_deterministic() -> None:
    rule = WorkflowRule(
        rule_id="any-risk",
        match_mode=MatchMode.ANY,
        conditions=(
            Condition(fact_key="late_minutes", operator=ConditionOperator.GTE, value=10),
            Condition(fact_key="delivery_failed", operator=ConditionOperator.EQ, value=True),
        ),
        actions=(
            ActionTemplate(
                action_key="create.ops.task",
                action_type=ActionType.CREATE_TASK,
                effect=ActionEffect.OPERATIONAL,
                execution_mode=ExecutionMode.AUTOMATIC,
                parameters={"queue_id": "customer-experience"},
            ),
        ),
    )
    result = evaluate_workflow(
        definition(rules=(rule,)),
        event(facts={"late_minutes": 2, "delivery_failed": True}),
        evaluated_at=BASE + timedelta(minutes=11),
    )
    assert result.matched_rule_ids == ("any-risk",)


def test_exclusive_group_ambiguity_fails_closed() -> None:
    first = notify_rule(rule_id="first", group="recovery-path")
    second = notify_rule(rule_id="second", group="recovery-path")
    with pytest.raises(WorkflowPolicyError, match="ambiguous"):
        evaluate_workflow(
            definition(rules=(first, second)),
            event(facts={"late_minutes": 20}),
            evaluated_at=BASE + timedelta(minutes=11),
        )


def test_event_fingerprint_tampering_is_rejected() -> None:
    evt = event(facts={"late_minutes": 20}).model_copy(update={"facts_fingerprint": "a" * 64})
    with pytest.raises(WorkflowPolicyError, match="fingerprint"):
        evaluate_workflow(definition(rules=(notify_rule(),)), evt, evaluated_at=BASE + timedelta(minutes=11))


def test_non_effective_and_cross_tenant_workflows_fail_closed() -> None:
    draft = definition(rules=(notify_rule(),), status=WorkflowStatus.DRAFT, approved_by=None, approved_at=None)
    with pytest.raises(WorkflowPolicyError, match="effective"):
        evaluate_workflow(draft, event(facts={"late_minutes": 10}), evaluated_at=BASE + timedelta(minutes=11))

    with pytest.raises(WorkflowPolicyError, match="tenant"):
        evaluate_workflow(
            definition(rules=(notify_rule(),)),
            event(facts={"late_minutes": 10}, tenant_id="tenant-b"),
            evaluated_at=BASE + timedelta(minutes=11),
        )


def test_workflow_versioning_is_linear_and_tenant_safe() -> None:
    first = definition(rules=(notify_rule(),))
    second = definition(
        rules=(notify_rule(),),
        version=2,
        supersedes_version=1,
        effective_from=BASE + timedelta(days=1),
    )
    assert validate_next_workflow_version(first, second) == second

    skipped = definition(
        rules=(notify_rule(),),
        version=3,
        supersedes_version=2,
        effective_from=BASE + timedelta(days=2),
    )
    with pytest.raises(WorkflowPolicyError, match="advance exactly one"):
        validate_next_workflow_version(first, skipped)

    with pytest.raises(WorkflowPolicyError, match="tenant"):
        validate_next_workflow_version(first, second.model_copy(update={"tenant_id": "tenant-b"}))


def test_resolver_prefers_more_specific_effective_scope_then_version() -> None:
    global_v1 = definition(rules=(notify_rule(),), scope=WorkflowScope(country="TR"))
    marmara_v2 = definition(
        rules=(notify_rule(),),
        version=2,
        supersedes_version=1,
        scope=WorkflowScope(country="TR", region="Marmara"),
    )
    resolved = resolve_effective_workflow(
        (global_v1, marmara_v2),
        tenant_id="tenant-a",
        workflow_id="late-order-recovery",
        event=event(facts={"late_minutes": 9}),
        at=BASE + timedelta(minutes=11),
    )
    assert resolved.version == 2
    assert resolved.scope.region == "Marmara"


def test_resolver_rejects_missing_or_equally_authoritative_candidates() -> None:
    wf = definition(rules=(notify_rule(),))
    with pytest.raises(WorkflowPolicyResolutionError, match="no effective"):
        resolve_effective_workflow(
            (wf,),
            tenant_id="tenant-b",
            workflow_id="late-order-recovery",
            event=event(facts={"late_minutes": 9}, tenant_id="tenant-b"),
            at=BASE + timedelta(minutes=11),
        )

    duplicate = wf.model_copy()
    with pytest.raises(WorkflowPolicyResolutionError, match="ambiguous"):
        resolve_effective_workflow(
            (wf, duplicate),
            tenant_id="tenant-a",
            workflow_id="late-order-recovery",
            event=event(facts={"late_minutes": 9}),
            at=BASE + timedelta(minutes=11),
        )


def test_financial_customer_recovery_intent_requires_matching_human_approval() -> None:
    rule = WorkflowRule(
        rule_id="late-financial-review",
        conditions=(Condition(fact_key="late_minutes", operator=ConditionOperator.GTE, value=15),),
        actions=(
            ActionTemplate(
                action_key="customer_promise.propose_recovery",
                action_type=ActionType.PROPOSE_DOMAIN_ACTION,
                effect=ActionEffect.FINANCIAL,
                execution_mode=ExecutionMode.REQUIRES_APPROVAL,
                parameters={"recovery_kind": "fee_refund"},
            ),
        ),
    )
    intent = evaluate_workflow(
        definition(rules=(rule,)),
        event(facts={"late_minutes": 20}),
        evaluated_at=BASE + timedelta(minutes=11),
    ).action_intents[0]
    assert intent.approval_required is True

    with pytest.raises(WorkflowPolicyError, match="requires approval"):
        authorize_action_execution(intent)

    rejected = ActionApprovalDecision(
        tenant_id="tenant-a",
        decision_id="decision-1",
        intent_id=intent.intent_id,
        decision=ApprovalDecisionType.REJECTED,
        decided_by="manager",
        decided_at=BASE + timedelta(minutes=20),
        reason="not eligible",
    )
    with pytest.raises(WorkflowPolicyError, match="rejected"):
        authorize_action_execution(intent, rejected)

    cross_tenant = rejected.model_copy(
        update={"tenant_id": "tenant-b", "decision": ApprovalDecisionType.APPROVED, "reason": None}
    )
    with pytest.raises(WorkflowPolicyError, match="tenant"):
        authorize_action_execution(intent, cross_tenant)

    approved = ActionApprovalDecision(
        tenant_id="tenant-a",
        decision_id="decision-2",
        intent_id=intent.intent_id,
        decision=ApprovalDecisionType.APPROVED,
        decided_by="manager",
        decided_at=BASE + timedelta(minutes=20),
    )
    assert authorize_action_execution(intent, approved) is True


def test_proposal_only_and_dry_run_intents_never_execute() -> None:
    proposal = WorkflowRule(
        rule_id="proposal",
        actions=(
            ActionTemplate(
                action_key="workforce.propose_replan",
                action_type=ActionType.PROPOSE_DOMAIN_ACTION,
                effect=ActionEffect.OPERATIONAL,
                execution_mode=ExecutionMode.PROPOSAL_ONLY,
            ),
        ),
    )
    result = evaluate_workflow(
        definition(rules=(proposal,)),
        event(facts={}),
        evaluated_at=BASE + timedelta(minutes=11),
    )
    with pytest.raises(WorkflowPolicyError, match="proposal-only"):
        authorize_action_execution(result.action_intents[0])

    dry = evaluate_workflow(
        definition(rules=(notify_rule(),)),
        event(facts={"late_minutes": 10}),
        evaluated_at=BASE + timedelta(minutes=11),
        dry_run=True,
    )
    with pytest.raises(WorkflowPolicyError, match="dry-run"):
        authorize_action_execution(dry.action_intents[0])


def test_low_risk_registered_intent_can_pass_generic_guard_without_approval() -> None:
    intent = evaluate_workflow(
        definition(rules=(notify_rule(),)),
        event(facts={"late_minutes": 10}),
        evaluated_at=BASE + timedelta(minutes=11),
    ).action_intents[0]
    assert intent.approval_required is False
    assert authorize_action_execution(intent) is True
