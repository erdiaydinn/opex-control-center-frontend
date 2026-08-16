from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.platform.workflow_policy.engine import build_event_fingerprint
from app.platform.workflow_policy.governance import (
    WorkflowActivationEvidence,
    WorkflowGovernanceError,
    validate_effective_promotion,
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
from app.platform.workflow_policy.simulation import compare_policy_versions


NOW = datetime(2026, 8, 16, 17, 0, tzinfo=UTC)


def workflow(version: int, status: WorkflowStatus, *, financial: bool = False) -> WorkflowDefinition:
    actions = [
        ActionTemplate(
            action_key="notify_manager",
            action_type=ActionType.NOTIFY,
            effect=ActionEffect.INFORMATIONAL,
            execution_mode=ExecutionMode.AUTOMATIC,
            parameters={"template_key": "pressure"},
        )
    ]
    if financial:
        actions.append(
            ActionTemplate(
                action_key="propose_credit",
                action_type=ActionType.PROPOSE_DOMAIN_ACTION,
                effect=ActionEffect.FINANCIAL,
                execution_mode=ExecutionMode.REQUIRES_APPROVAL,
                parameters={"reason_code": "promise_breach"},
            )
        )
    approved = status in {WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE}
    return WorkflowDefinition(
        tenant_id="tenant-a",
        workflow_id="promise_recovery",
        version=version,
        supersedes_version=None if version == 1 else version - 1,
        status=status,
        source_module="customer_promise",
        event_type="promise_breached",
        scope=WorkflowScope(country="TR"),
        effective_from=NOW,
        approved_by="policy-approver" if approved else None,
        approved_at=NOW if approved else None,
        rules=(
            WorkflowRule(
                rule_id="late_order",
                conditions=(
                    Condition(
                        fact_key="late_minutes",
                        operator=ConditionOperator.GTE,
                        value=10,
                    ),
                ),
                actions=tuple(actions),
            ),
        ),
    )


def sample_event() -> WorkflowEvent:
    facts = {"late_minutes": 25}
    return WorkflowEvent(
        tenant_id="tenant-a",
        event_id="event-1",
        idempotency_key="promise-event-1",
        source_module="customer_promise",
        event_type="promise_breached",
        subject_ref="order-opaque-1",
        occurred_at=NOW + timedelta(minutes=1),
        scope=WorkflowScope(country="TR"),
        facts=facts,
        facts_fingerprint=build_event_fingerprint(facts),
    )


def evidence_for(impact, *, acknowledge: bool) -> WorkflowActivationEvidence:
    return WorkflowActivationEvidence(
        tenant_id=impact.tenant_id,
        workflow_id=impact.workflow_id,
        workflow_version=impact.candidate_version,
        impact_fingerprint=impact.impact_fingerprint,
        simulated_event_count=impact.total_events,
        changed_event_count=impact.changed_events,
        high_risk_changed_events=impact.high_risk_changed_events,
        reviewed_by="release-reviewer",
        reviewed_at=NOW + timedelta(minutes=5),
        high_risk_acknowledged=acknowledge,
    )


def test_approved_policy_can_activate_with_matching_simulation_evidence() -> None:
    baseline = workflow(1, WorkflowStatus.EFFECTIVE)
    candidate = workflow(2, WorkflowStatus.APPROVED)
    impact = compare_policy_versions(
        baseline,
        candidate,
        (sample_event(),),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    validate_effective_promotion(candidate, impact, evidence_for(impact, acknowledge=False))


def test_high_risk_change_requires_explicit_acknowledgment() -> None:
    baseline = workflow(1, WorkflowStatus.EFFECTIVE)
    candidate = workflow(2, WorkflowStatus.APPROVED, financial=True)
    impact = compare_policy_versions(
        baseline,
        candidate,
        (sample_event(),),
        evaluated_at=NOW + timedelta(minutes=2),
    )

    with pytest.raises(WorkflowGovernanceError, match="explicit acknowledgment"):
        evidence_for(impact, acknowledge=False)

    validate_effective_promotion(candidate, impact, evidence_for(impact, acknowledge=True))


def test_activation_rejects_wrong_simulation_fingerprint() -> None:
    baseline = workflow(1, WorkflowStatus.EFFECTIVE)
    candidate = workflow(2, WorkflowStatus.APPROVED)
    impact = compare_policy_versions(
        baseline,
        candidate,
        (sample_event(),),
        evaluated_at=NOW + timedelta(minutes=2),
    )
    evidence = replace(evidence_for(impact, acknowledge=False), impact_fingerprint="f" * 64)

    with pytest.raises(WorkflowGovernanceError, match="fingerprint mismatch"):
        validate_effective_promotion(candidate, impact, evidence)


def test_activation_requires_nonempty_simulation_sample() -> None:
    with pytest.raises(WorkflowGovernanceError, match="at least one simulated event"):
        WorkflowActivationEvidence(
            tenant_id="tenant-a",
            workflow_id="promise_recovery",
            workflow_version=2,
            impact_fingerprint="a" * 64,
            simulated_event_count=0,
            changed_event_count=0,
            high_risk_changed_events=0,
            reviewed_by="release-reviewer",
            reviewed_at=NOW,
        )
