from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from .models import (
    ActionApprovalDecision,
    ActionEffect,
    ActionIntent,
    ApprovalDecisionType,
    Condition,
    ConditionOperator,
    ConditionTrace,
    EvaluationResult,
    ExecutionMode,
    HIGH_RISK_EFFECTS,
    MatchMode,
    RuleTrace,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowScope,
    WorkflowStatus,
)


class WorkflowPolicyError(ValueError):
    pass


class WorkflowPolicyResolutionError(LookupError):
    pass


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_event_fingerprint(facts: dict[str, object]) -> str:
    """Stable fingerprint helper for event facts; raw facts need not be persisted."""
    return _fingerprint(facts)


def validate_next_workflow_version(
    previous: WorkflowDefinition,
    current: WorkflowDefinition,
) -> WorkflowDefinition:
    if previous.tenant_id != current.tenant_id:
        raise WorkflowPolicyError("workflow revision cannot cross tenant boundary")
    if previous.workflow_id != current.workflow_id:
        raise WorkflowPolicyError("workflow revision must preserve workflow identity")
    if current.version != previous.version + 1 or current.supersedes_version != previous.version:
        raise WorkflowPolicyError("workflow revision must advance exactly one immutable version")
    if current.effective_from < previous.effective_from:
        raise WorkflowPolicyError("workflow effective_from cannot move backwards")
    return current


def _scope_matches(expected: WorkflowScope, actual: WorkflowScope) -> bool:
    return all(
        wanted is None or wanted == observed
        for wanted, observed in (
            (expected.country, actual.country),
            (expected.region, actual.region),
            (expected.business_unit, actual.business_unit),
            (expected.location_id, actual.location_id),
        )
    )


def resolve_effective_workflow(
    definitions: tuple[WorkflowDefinition, ...],
    *,
    tenant_id: str,
    workflow_id: str,
    event: WorkflowEvent,
    at: datetime | None = None,
) -> WorkflowDefinition:
    """Resolve one named workflow version with scope specificity and ambiguity rejection."""
    evaluation_time = at or event.occurred_at
    candidates = [
        definition
        for definition in definitions
        if definition.tenant_id == tenant_id
        and definition.workflow_id == workflow_id
        and definition.status is WorkflowStatus.EFFECTIVE
        and definition.source_module == event.source_module
        and definition.event_type == event.event_type
        and definition.effective_from <= evaluation_time
        and (definition.effective_to is None or definition.effective_to > evaluation_time)
        and _scope_matches(definition.scope, event.scope)
    ]
    if not candidates:
        raise WorkflowPolicyResolutionError("no effective workflow for tenant/event scope")
    candidates.sort(key=lambda item: (item.scope.specificity, item.version), reverse=True)
    top_rank = (candidates[0].scope.specificity, candidates[0].version)
    top = [item for item in candidates if (item.scope.specificity, item.version) == top_rank]
    if len(top) > 1:
        raise WorkflowPolicyResolutionError("ambiguous equally authoritative workflow versions")
    return candidates[0]


def _ordered_pair(actual: object, expected: object) -> tuple[object, object] | None:
    numeric = (int, float)
    if isinstance(actual, bool) or isinstance(expected, bool):
        return None
    if isinstance(actual, numeric) and isinstance(expected, numeric):
        return actual, expected
    if isinstance(actual, str) and isinstance(expected, str):
        return actual, expected
    return None


def _match_condition(condition: Condition, event: WorkflowEvent) -> bool:
    exists = condition.fact_key in event.facts
    if condition.operator is ConditionOperator.EXISTS:
        return exists
    if not exists:
        return False

    actual = event.facts[condition.fact_key]
    if condition.operator is ConditionOperator.EQ:
        return actual == condition.value
    if condition.operator is ConditionOperator.NE:
        return actual != condition.value
    if condition.operator is ConditionOperator.IN:
        return actual in condition.values
    if condition.operator is ConditionOperator.NOT_IN:
        return actual not in condition.values

    pair = _ordered_pair(actual, condition.value)
    if pair is None:
        return False
    left, right = pair
    if condition.operator is ConditionOperator.GT:
        return left > right
    if condition.operator is ConditionOperator.GTE:
        return left >= right
    if condition.operator is ConditionOperator.LT:
        return left < right
    if condition.operator is ConditionOperator.LTE:
        return left <= right
    raise WorkflowPolicyError(f"unsupported condition operator: {condition.operator}")


def _rule_match(rule, event: WorkflowEvent) -> tuple[bool, tuple[ConditionTrace, ...]]:
    traces = tuple(
        ConditionTrace(
            fact_key=condition.fact_key,
            operator=condition.operator,
            matched=_match_condition(condition, event),
        )
        for condition in rule.conditions
    )
    if not traces:
        return True, traces
    if rule.match_mode is MatchMode.ALL:
        return all(trace.matched for trace in traces), traces
    return any(trace.matched for trace in traces), traces


def _ensure_evaluable(
    definition: WorkflowDefinition,
    event: WorkflowEvent,
    at: datetime,
    *,
    dry_run: bool,
) -> None:
    if dry_run:
        if definition.status not in {WorkflowStatus.DRAFT, WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE}:
            raise WorkflowPolicyError("workflow status cannot be simulated")
    elif definition.status is not WorkflowStatus.EFFECTIVE:
        raise WorkflowPolicyError("only effective workflows may evaluate production events")
    if definition.tenant_id != event.tenant_id:
        raise WorkflowPolicyError("workflow evaluation cannot cross tenant boundary")
    if definition.source_module != event.source_module or definition.event_type != event.event_type:
        raise WorkflowPolicyError("workflow event contract mismatch")
    if not _scope_matches(definition.scope, event.scope):
        raise WorkflowPolicyError("workflow scope does not match event")
    if definition.effective_from > at or (definition.effective_to and definition.effective_to <= at):
        raise WorkflowPolicyError("workflow is not effective at evaluation time")


def evaluate_workflow(
    definition: WorkflowDefinition,
    event: WorkflowEvent,
    *,
    evaluated_at: datetime | None = None,
    dry_run: bool = False,
) -> EvaluationResult:
    """Evaluate fixed operators only; emit intents without executing module mutations."""
    evaluation_time = evaluated_at or datetime.now(UTC)
    _ensure_evaluable(definition, event, evaluation_time, dry_run=dry_run)
    if event.facts_fingerprint != build_event_fingerprint(event.facts):
        raise WorkflowPolicyError("event facts fingerprint mismatch")

    traces: list[RuleTrace] = []
    matched_rule_ids: list[str] = []
    action_intents: list[ActionIntent] = []
    matched_exclusive_groups: set[str] = set()

    for rule in sorted(definition.rules, key=lambda item: (-item.priority, item.rule_id)):
        matched, condition_traces = _rule_match(rule, event)
        traces.append(
            RuleTrace(
                rule_id=rule.rule_id,
                priority=rule.priority,
                matched=matched,
                condition_results=condition_traces,
            )
        )
        if not matched:
            continue
        if rule.exclusive_group:
            if rule.exclusive_group in matched_exclusive_groups:
                raise WorkflowPolicyError("ambiguous matched rules in exclusive group")
            matched_exclusive_groups.add(rule.exclusive_group)

        matched_rule_ids.append(rule.rule_id)
        for index, action in enumerate(rule.actions):
            seed = {
                "tenant_id": definition.tenant_id,
                "workflow_id": definition.workflow_id,
                "workflow_version": definition.version,
                "event_id": event.event_id,
                "rule_id": rule.rule_id,
                "action_index": index,
                "action_key": action.action_key,
                "dry_run": dry_run,
            }
            intent_id = _fingerprint(seed)
            action_intents.append(
                ActionIntent(
                    tenant_id=definition.tenant_id,
                    intent_id=intent_id,
                    dedupe_key=intent_id,
                    workflow_id=definition.workflow_id,
                    workflow_version=definition.version,
                    event_id=event.event_id,
                    rule_id=rule.rule_id,
                    action_key=action.action_key,
                    action_type=action.action_type,
                    effect=action.effect,
                    execution_mode=action.execution_mode,
                    parameters=dict(action.parameters),
                    approval_required=(
                        action.execution_mode is ExecutionMode.REQUIRES_APPROVAL
                        or action.effect in HIGH_RISK_EFFECTS
                    ),
                    dry_run=dry_run,
                )
            )
        if rule.stop_processing:
            break

    decision_payload = {
        "tenant_id": definition.tenant_id,
        "workflow_id": definition.workflow_id,
        "workflow_version": definition.version,
        "event_id": event.event_id,
        "event_facts_fingerprint": event.facts_fingerprint,
        "matched_rule_ids": matched_rule_ids,
        "intent_ids": [intent.intent_id for intent in action_intents],
        "dry_run": dry_run,
    }
    return EvaluationResult(
        tenant_id=definition.tenant_id,
        workflow_id=definition.workflow_id,
        workflow_version=definition.version,
        event_id=event.event_id,
        dry_run=dry_run,
        traces=tuple(traces),
        matched_rule_ids=tuple(matched_rule_ids),
        action_intents=tuple(action_intents),
        decision_fingerprint=_fingerprint(decision_payload),
        evaluated_at=evaluation_time,
    )


def authorize_action_execution(
    intent: ActionIntent,
    decision: ActionApprovalDecision | None = None,
) -> bool:
    """Final generic guard before a registered downstream action adapter is invoked."""
    if intent.dry_run:
        raise WorkflowPolicyError("dry-run workflow intent cannot execute")
    if intent.execution_mode is ExecutionMode.PROPOSAL_ONLY:
        raise WorkflowPolicyError("proposal-only workflow intent cannot execute directly")
    if intent.effect in HIGH_RISK_EFFECTS and intent.execution_mode is ExecutionMode.AUTOMATIC:
        raise WorkflowPolicyError("high-risk workflow intent cannot execute automatically")

    if intent.approval_required:
        if decision is None:
            raise WorkflowPolicyError("workflow action requires approval")
        if decision.tenant_id != intent.tenant_id:
            raise WorkflowPolicyError("workflow approval cannot cross tenant boundary")
        if decision.intent_id != intent.intent_id:
            raise WorkflowPolicyError("workflow approval references another action intent")
        if decision.decision is not ApprovalDecisionType.APPROVED:
            raise WorkflowPolicyError("rejected workflow action cannot execute")
    elif decision is not None:
        if decision.tenant_id != intent.tenant_id or decision.intent_id != intent.intent_id:
            raise WorkflowPolicyError("workflow decision scope mismatch")
        if decision.decision is ApprovalDecisionType.REJECTED:
            raise WorkflowPolicyError("rejected workflow action cannot execute")
    return True
