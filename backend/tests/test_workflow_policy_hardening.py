from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.platform.workflow_policy.engine import (
    WorkflowPolicyError,
    authorize_action_execution,
    build_event_fingerprint,
    evaluate_workflow,
)
from app.platform.workflow_policy.models import (
    ActionEffect,
    ActionTemplate,
    ActionType,
    Condition,
    ConditionOperator,
    ExecutionMode,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowRule,
    WorkflowScope,
    WorkflowStatus,
)


BASE = datetime(2026, 8, 16, 9, 0, tzinfo=UTC)


def _rule(fact_key: str = "token_age_seconds") -> WorkflowRule:
    return WorkflowRule(
        rule_id="derived-signal-rule",
        conditions=(Condition(fact_key=fact_key, operator=ConditionOperator.GTE, value=300),),
        actions=(
            ActionTemplate(
                action_key="notify.ops",
                action_type=ActionType.NOTIFY,
                effect=ActionEffect.INFORMATIONAL,
                execution_mode=ExecutionMode.AUTOMATIC,
                parameters={"template_id": "derived-signal-alert"},
            ),
        ),
    )


def _definition(status: WorkflowStatus = WorkflowStatus.EFFECTIVE) -> WorkflowDefinition:
    approval = status in {WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE, WorkflowStatus.SUPERSEDED}
    return WorkflowDefinition(
        tenant_id="tenant-a",
        workflow_id="security-derived-signal",
        version=1,
        status=status,
        source_module="security",
        event_type="security.token_expired",
        scope=WorkflowScope(country="TR"),
        effective_from=BASE,
        approved_by="security-owner" if approval else None,
        approved_at=BASE - timedelta(minutes=1) if approval else None,
        rules=(_rule(),),
    )


def _event(facts: dict[str, object]) -> WorkflowEvent:
    return WorkflowEvent(
        tenant_id="tenant-a",
        event_id="security-event-1",
        idempotency_key="security-derived-0001",
        source_module="security",
        event_type="security.token_expired",
        subject_ref="session-fingerprint-1",
        occurred_at=BASE + timedelta(minutes=5),
        scope=WorkflowScope(country="TR"),
        facts=facts,
        facts_fingerprint=build_event_fingerprint(facts),
    )


def test_safe_derived_operational_signals_are_allowed_without_raw_secrets() -> None:
    facts = {
        "token_age_seconds": 420,
        "endpoint_health": "degraded",
        "sql_latency_ms": 850,
    }
    event = _event(facts)
    assert event.facts == facts
    result = evaluate_workflow(_definition(), event, evaluated_at=BASE + timedelta(minutes=6))
    assert result.matched_rule_ids == ("derived-signal-rule",)


def test_raw_credentials_and_remote_execution_payload_names_remain_blocked() -> None:
    for key in (
        "access_token",
        "refresh_token",
        "authorization_header",
        "customer_email",
        "webhook_url",
        "raw_sql",
        "shell_command",
    ):
        facts = {key: "forbidden"}
        with pytest.raises(ValidationError, match="not permitted"):
            _event(facts)


def test_draft_policy_can_be_simulated_but_not_used_for_live_evaluation() -> None:
    workflow = _definition(WorkflowStatus.DRAFT)
    event = _event({"token_age_seconds": 420})

    dry_run = evaluate_workflow(
        workflow,
        event,
        evaluated_at=BASE + timedelta(minutes=6),
        dry_run=True,
    )
    assert dry_run.dry_run is True
    assert dry_run.matched_rule_ids == ("derived-signal-rule",)
    with pytest.raises(WorkflowPolicyError, match="dry-run"):
        authorize_action_execution(dry_run.action_intents[0])

    with pytest.raises(WorkflowPolicyError, match="only effective"):
        evaluate_workflow(
            workflow,
            event,
            evaluated_at=BASE + timedelta(minutes=6),
            dry_run=False,
        )


def test_dry_run_and_live_action_intents_have_distinct_dedupe_identity() -> None:
    workflow = _definition()
    event = _event({"token_age_seconds": 420})
    live = evaluate_workflow(
        workflow,
        event,
        evaluated_at=BASE + timedelta(minutes=6),
        dry_run=False,
    )
    simulation = evaluate_workflow(
        workflow,
        event,
        evaluated_at=BASE + timedelta(minutes=6),
        dry_run=True,
    )
    assert live.action_intents[0].intent_id != simulation.action_intents[0].intent_id
    assert live.action_intents[0].dedupe_key != simulation.action_intents[0].dedupe_key
    assert live.decision_fingerprint != simulation.decision_fingerprint


def test_superseded_policy_cannot_even_be_simulated_as_current_policy() -> None:
    workflow = _definition(WorkflowStatus.SUPERSEDED)
    event = _event({"token_age_seconds": 420})
    with pytest.raises(WorkflowPolicyError, match="cannot be simulated"):
        evaluate_workflow(
            workflow,
            event,
            evaluated_at=BASE + timedelta(minutes=6),
            dry_run=True,
        )
