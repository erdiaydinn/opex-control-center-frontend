from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime

from pydantic import Field

from .engine import WorkflowPolicyError, evaluate_workflow, validate_next_workflow_version
from .models import (
    ActionEffect,
    ActionIntent,
    HIGH_RISK_EFFECTS,
    StrictFrozenModel,
    WorkflowDefinition,
    WorkflowEvent,
)

MAX_SIMULATION_EVENTS = 1000


class SemanticAction(StrictFrozenModel):
    rule_id: str
    action_key: str
    action_type: str
    effect: str
    execution_mode: str
    approval_required: bool
    parameters_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class EventPolicyImpact(StrictFrozenModel):
    event_id: str
    changed: bool
    baseline_matched_rules: tuple[str, ...]
    candidate_matched_rules: tuple[str, ...]
    added_actions: tuple[SemanticAction, ...]
    removed_actions: tuple[SemanticAction, ...]
    high_risk_change: bool
    baseline_decision_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    candidate_decision_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")


class PolicyImpactSummary(StrictFrozenModel):
    tenant_id: str
    workflow_id: str
    baseline_version: int = Field(ge=1)
    candidate_version: int = Field(ge=1)
    total_events: int = Field(ge=0)
    changed_events: int = Field(ge=0)
    unchanged_events: int = Field(ge=0)
    added_action_count: int = Field(ge=0)
    removed_action_count: int = Field(ge=0)
    high_risk_changed_events: int = Field(ge=0)
    requires_high_risk_review: bool
    impact_fingerprint: str = Field(pattern=r"^[a-f0-9]{64}$")
    events: tuple[EventPolicyImpact, ...]


def _fingerprint(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _semantic_action(intent: ActionIntent) -> SemanticAction:
    return SemanticAction(
        rule_id=intent.rule_id,
        action_key=intent.action_key,
        action_type=intent.action_type.value,
        effect=intent.effect.value,
        execution_mode=intent.execution_mode.value,
        approval_required=intent.approval_required,
        parameters_fingerprint=_fingerprint(intent.parameters),
    )


def _action_key(action: SemanticAction) -> tuple[object, ...]:
    return (
        action.rule_id,
        action.action_key,
        action.action_type,
        action.effect,
        action.execution_mode,
        action.approval_required,
        action.parameters_fingerprint,
    )


def _counter(actions: tuple[SemanticAction, ...]) -> Counter[tuple[object, ...]]:
    return Counter(_action_key(action) for action in actions)


def _counter_delta(
    left: tuple[SemanticAction, ...],
    right: tuple[SemanticAction, ...],
) -> tuple[SemanticAction, ...]:
    right_counter = _counter(right)
    remaining: list[SemanticAction] = []
    for action in left:
        key = _action_key(action)
        if right_counter[key] > 0:
            right_counter[key] -= 1
        else:
            remaining.append(action)
    return tuple(remaining)


def compare_policy_versions(
    baseline: WorkflowDefinition,
    candidate: WorkflowDefinition,
    events: tuple[WorkflowEvent, ...],
    *,
    evaluated_at: datetime | None = None,
) -> PolicyImpactSummary:
    """Dry-run a candidate policy against an effective baseline.

    Semantic action comparison deliberately excludes version-derived intent IDs.
    A pure version bump with identical rules is therefore reported as unchanged.
    No event facts or action executions are persisted by this function.
    """
    validate_next_workflow_version(baseline, candidate)
    if baseline.source_module != candidate.source_module or baseline.event_type != candidate.event_type:
        raise WorkflowPolicyError("candidate workflow must preserve source module and event type")
    if baseline.scope != candidate.scope:
        raise WorkflowPolicyError("candidate workflow scope changes require a separate scoped impact review")
    if len(events) > MAX_SIMULATION_EVENTS:
        raise WorkflowPolicyError(f"policy simulation is limited to {MAX_SIMULATION_EVENTS} events")

    event_impacts: list[EventPolicyImpact] = []
    added_total = 0
    removed_total = 0
    high_risk_total = 0

    for event in events:
        if event.tenant_id != baseline.tenant_id:
            raise WorkflowPolicyError("policy simulation cannot cross tenant boundary")
        baseline_result = evaluate_workflow(
            baseline,
            event,
            evaluated_at=evaluated_at,
            dry_run=True,
        )
        candidate_result = evaluate_workflow(
            candidate,
            event,
            evaluated_at=evaluated_at,
            dry_run=True,
        )

        baseline_actions = tuple(_semantic_action(intent) for intent in baseline_result.action_intents)
        candidate_actions = tuple(_semantic_action(intent) for intent in candidate_result.action_intents)
        added = _counter_delta(candidate_actions, baseline_actions)
        removed = _counter_delta(baseline_actions, candidate_actions)
        changed = bool(
            added
            or removed
            or baseline_result.matched_rule_ids != candidate_result.matched_rule_ids
        )
        high_risk_change = any(
            ActionEffect(action.effect) in HIGH_RISK_EFFECTS for action in added
        )
        if high_risk_change:
            high_risk_total += 1
        added_total += len(added)
        removed_total += len(removed)

        event_impacts.append(
            EventPolicyImpact(
                event_id=event.event_id,
                changed=changed,
                baseline_matched_rules=baseline_result.matched_rule_ids,
                candidate_matched_rules=candidate_result.matched_rule_ids,
                added_actions=added,
                removed_actions=removed,
                high_risk_change=high_risk_change,
                baseline_decision_fingerprint=baseline_result.decision_fingerprint,
                candidate_decision_fingerprint=candidate_result.decision_fingerprint,
            )
        )

    changed_count = sum(1 for impact in event_impacts if impact.changed)
    summary_payload = {
        "tenant_id": baseline.tenant_id,
        "workflow_id": baseline.workflow_id,
        "baseline_version": baseline.version,
        "candidate_version": candidate.version,
        "events": [
            {
                "event_id": impact.event_id,
                "changed": impact.changed,
                "added": [action.model_dump(mode="json") for action in impact.added_actions],
                "removed": [action.model_dump(mode="json") for action in impact.removed_actions],
                "high_risk_change": impact.high_risk_change,
            }
            for impact in event_impacts
        ],
    }
    return PolicyImpactSummary(
        tenant_id=baseline.tenant_id,
        workflow_id=baseline.workflow_id,
        baseline_version=baseline.version,
        candidate_version=candidate.version,
        total_events=len(event_impacts),
        changed_events=changed_count,
        unchanged_events=len(event_impacts) - changed_count,
        added_action_count=added_total,
        removed_action_count=removed_total,
        high_risk_changed_events=high_risk_total,
        requires_high_risk_review=high_risk_total > 0,
        impact_fingerprint=_fingerprint(summary_payload),
        events=tuple(event_impacts),
    )
