from datetime import UTC, datetime, timedelta

import pytest

from app.platform.workflow_policy.engine import WorkflowPolicyError, build_event_fingerprint
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
from app.platform.workflow_policy.simulation import MAX_SIMULATION_EVENTS, compare_policy_versions


NOW = datetime(2026, 8, 16, 16, 0, tzinfo=UTC)


def notify_action() -> ActionTemplate:
    return ActionTemplate(
        action_key="notify_manager",
        action_type=ActionType.NOTIFY,
        effect=ActionEffect.INFORMATIONAL,
        execution_mode=ExecutionMode.AUTOMATIC,
        parameters={"template_key": "pressure_warning"},
    )


def financial_action() -> ActionTemplate:
    return ActionTemplate(
        action_key="propose_service_credit",
        action_type=ActionType.PROPOSE_DOMAIN_ACTION,
        effect=ActionEffect.FINANCIAL,
        execution_mode=ExecutionMode.REQUIRES_APPROVAL,
        parameters={"reason_code": "promise_breach"},
    )


def pressure_rule(*, threshold: float, include_financial: bool = False) -> WorkflowRule:
    actions = (notify_action(), financial_action()) if include_financial else (notify_action(),)
    return WorkflowRule(
        rule_id="pressure_rule",
        priority=100,
        conditions=(
            Condition(
                fact_key="backlog_pressure",
                operator=ConditionOperator.GTE,
                value=threshold,
            ),
        ),
        actions=actions,
    )


def definition(
    *,
    version: int,
    status: WorkflowStatus,
    threshold: float = 0.8,
    include_financial: bool = False,
    tenant_id: str = "tenant-a",
    scope: WorkflowScope | None = None,
) -> WorkflowDefinition:
    approved = status in {WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE}
    return WorkflowDefinition(
        tenant_id=tenant_id,
        workflow_id="depot_pressure_guard",
        version=version,
        supersedes_version=None if version == 1 else version - 1,
        status=status,
        source_module="workforce",
        event_type="depot_pressure_changed",
        scope=scope or WorkflowScope(country="TR", region="marmara"),
        effective_from=NOW,
        approved_by="manager-1" if approved else None,
        approved_at=NOW if approved else None,
        rules=(pressure_rule(threshold=threshold, include_financial=include_financial),),
    )


def event(event_id: str, pressure: float, *, tenant_id: str = "tenant-a") -> WorkflowEvent:
    facts = {"backlog_pressure": pressure, "coverage_gap_hours": 2.0}
    return WorkflowEvent(
        tenant_id=tenant_id,
        event_id=event_id,
        idempotency_key=f"idem-{event_id}",
        source_module="workforce",
        event_type="depot_pressure_changed",
        subject_ref="depot-42",
        occurred_at=NOW + timedelta(minutes=5),
        scope=WorkflowScope(country="TR", region="marmara"),
        facts=facts,
        facts_fingerprint=build_event_fingerprint(facts),
    )


def test_noop_version_bump_is_semantically_unchanged() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE)
    candidate = definition(version=2, status=WorkflowStatus.APPROVED)

    impact = compare_policy_versions(baseline, candidate, (event("evt-1", 0.9),), evaluated_at=NOW + timedelta(minutes=10))

    assert impact.changed_events == 0
    assert impact.unchanged_events == 1
    assert impact.added_action_count == 0
    assert impact.removed_action_count == 0
    assert impact.requires_high_risk_review is False
    assert impact.events[0].baseline_decision_fingerprint != impact.events[0].candidate_decision_fingerprint


def test_threshold_change_only_marks_impacted_events() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE, threshold=0.8)
    candidate = definition(version=2, status=WorkflowStatus.APPROVED, threshold=0.6)
    events = (event("low", 0.5), event("newly-matched", 0.7), event("already-matched", 0.9))

    impact = compare_policy_versions(baseline, candidate, events, evaluated_at=NOW + timedelta(minutes=10))

    changed = {item.event_id for item in impact.events if item.changed}
    assert changed == {"newly-matched"}
    assert impact.changed_events == 1
    assert impact.unchanged_events == 2
    assert impact.added_action_count == 1
    assert impact.removed_action_count == 0


def test_new_financial_action_requires_high_risk_review() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE)
    candidate = definition(
        version=2,
        status=WorkflowStatus.APPROVED,
        include_financial=True,
    )

    impact = compare_policy_versions(baseline, candidate, (event("evt-fin", 0.9),), evaluated_at=NOW + timedelta(minutes=10))

    assert impact.changed_events == 1
    assert impact.high_risk_changed_events == 1
    assert impact.requires_high_risk_review is True
    added = impact.events[0].added_actions
    assert len(added) == 1
    assert added[0].effect == ActionEffect.FINANCIAL.value
    assert added[0].approval_required is True


def test_simulation_fails_closed_on_cross_tenant_event() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE)
    candidate = definition(version=2, status=WorkflowStatus.APPROVED)

    with pytest.raises(WorkflowPolicyError, match="cross tenant"):
        compare_policy_versions(
            baseline,
            candidate,
            (event("evt-cross", 0.9, tenant_id="tenant-b"),),
            evaluated_at=NOW + timedelta(minutes=10),
        )


def test_scope_change_requires_separate_impact_review() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE)
    candidate = definition(
        version=2,
        status=WorkflowStatus.APPROVED,
        scope=WorkflowScope(country="TR", region="ege"),
    )

    with pytest.raises(WorkflowPolicyError, match="scope changes"):
        compare_policy_versions(baseline, candidate, (), evaluated_at=NOW + timedelta(minutes=10))


def test_simulation_batch_is_bounded() -> None:
    baseline = definition(version=1, status=WorkflowStatus.EFFECTIVE)
    candidate = definition(version=2, status=WorkflowStatus.APPROVED)
    seed = event("evt-0", 0.9)
    events = tuple(seed.model_copy(update={"event_id": f"evt-{index}", "idempotency_key": f"idem-evt-{index}"}) for index in range(MAX_SIMULATION_EVENTS + 1))

    with pytest.raises(WorkflowPolicyError, match="limited"):
        compare_policy_versions(baseline, candidate, events, evaluated_at=NOW + timedelta(minutes=10))
