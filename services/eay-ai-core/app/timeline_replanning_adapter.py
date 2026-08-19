"""Convert eligible real-world timeline events into evidence-bound replan signals.

The Real-World Timeline is an index, not truth. Therefore timeline membership alone
can never invalidate company truth or mutate capabilities. A reviewed rule must map
an exact low-cardinality event type to explicit affected resources/truth/capability
scope, and the event authority class must be strong enough for that scope.

Verified external context may trigger resource-level replanning when explicitly mapped,
but it cannot invalidate verified company truth or declare company capability drift.
Ambient/device observations remain observational and cannot trigger these stronger
replanning scopes.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .objective_replanning import RealityChangeSeverity, RealityChangeSignal
from .real_world_timeline import RealWorldTimelineEvent, TimelineAuthorityClass

TIMELINE_REPLANNING_ADAPTER_CONTRACT = "eay-timeline-replanning-adapter-v1"

_COMPANY_CHANGE_AUTHORITIES = frozenset(
    {
        TimelineAuthorityClass.GOVERNED_OPERATIONAL,
        TimelineAuthorityClass.VERIFIED_COMPANY,
        TimelineAuthorityClass.VERIFIED_ACTION,
        TimelineAuthorityClass.VERIFIED_OUTCOME,
    }
)
_EXTERNAL_RESOURCE_AUTHORITIES = frozenset(
    {
        TimelineAuthorityClass.VERIFIED_EXTERNAL,
        TimelineAuthorityClass.VERIFIED_LEGAL,
    }
)
_OBSERVATIONAL_AUTHORITIES = frozenset(
    {
        TimelineAuthorityClass.AMBIENT_UNTRUSTED,
        TimelineAuthorityClass.DEVICE_OBSERVATION,
        TimelineAuthorityClass.CONTEXT_ONLY,
        TimelineAuthorityClass.ANALYTIC_INFERENCE,
    }
)


class TimelineReplanRule(BaseModel):
    contract: str = TIMELINE_REPLANNING_ADAPTER_CONTRACT
    event_type: str = Field(min_length=1)
    affected_resource_refs: tuple[str, ...] = ()
    invalidated_truth_requirement_ids: tuple[str, ...] = ()
    changed_capability_refs: tuple[str, ...] = ()
    severity: RealityChangeSeverity = RealityChangeSeverity.MEDIUM
    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    max_observation_age_seconds: int = Field(default=900, ge=1, le=86_400)
    allow_verified_external_resource_replan: bool = False

    @model_validator(mode="after")
    def rule_has_scope(self) -> "TimelineReplanRule":
        if not (
            self.affected_resource_refs
            or self.invalidated_truth_requirement_ids
            or self.changed_capability_refs
        ):
            raise ValueError("timeline_replan_rule_requires_scope")
        for values, label in (
            (self.affected_resource_refs, "resources"),
            (self.invalidated_truth_requirement_ids, "truth_requirements"),
            (self.changed_capability_refs, "capabilities"),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"timeline_replan_rule_{label}_must_be_unique")
        return self


class TimelineReplanDecision(BaseModel):
    contract: str = TIMELINE_REPLANNING_ADAPTER_CONTRACT
    event_id: str
    eligible: bool
    reason_codes: tuple[str, ...]
    signal: RealityChangeSignal | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_is_consistent(self) -> "TimelineReplanDecision":
        if self.execution_authority_granted:
            raise ValueError("timeline_replan_decision_never_grants_execution_authority")
        if self.eligible != (self.signal is not None):
            raise ValueError("timeline_replan_decision_signal_eligibility_mismatch")
        return self


def _validated_event(event: RealWorldTimelineEvent) -> RealWorldTimelineEvent:
    """Rehydrate so model_copy tampering cannot bypass event fingerprint validation."""

    return RealWorldTimelineEvent.model_validate(event.model_dump(mode="json"))


def _now_is_aware(now: datetime) -> None:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("timeline_replan_now_requires_timezone")


def evaluate_timeline_event_for_replan(
    *,
    event: RealWorldTimelineEvent,
    rule: TimelineReplanRule,
    now: datetime,
) -> TimelineReplanDecision:
    """Return one fail-closed decision; eligible decisions contain a replan signal."""

    _now_is_aware(now)
    event = _validated_event(event)
    if event.event_type != rule.event_type:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_event_type_not_mapped",),
        )
    if event.confidence < rule.min_confidence:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_event_confidence_below_threshold",),
        )
    if event.observed_at > now:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_event_observed_in_future",),
        )
    age_seconds = (now - event.observed_at).total_seconds()
    if age_seconds > rule.max_observation_age_seconds:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_event_stale",),
        )

    has_truth_or_capability_change = bool(
        rule.invalidated_truth_requirement_ids or rule.changed_capability_refs
    )
    authority = event.authority_class
    if has_truth_or_capability_change and authority not in _COMPANY_CHANGE_AUTHORITIES:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_company_change_requires_company_authority",),
        )

    if authority in _OBSERVATIONAL_AUTHORITIES:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_observational_event_not_actionable",),
        )

    if authority in _EXTERNAL_RESOURCE_AUTHORITIES:
        if not rule.affected_resource_refs or not rule.allow_verified_external_resource_replan:
            return TimelineReplanDecision(
                event_id=event.event_id,
                eligible=False,
                reason_codes=("timeline_replan_external_resource_mapping_not_allowed",),
            )
        if has_truth_or_capability_change:
            return TimelineReplanDecision(
                event_id=event.event_id,
                eligible=False,
                reason_codes=("timeline_replan_external_cannot_invalidate_company_state",),
            )

    if authority not in _COMPANY_CHANGE_AUTHORITIES | _EXTERNAL_RESOURCE_AUTHORITIES:
        return TimelineReplanDecision(
            event_id=event.event_id,
            eligible=False,
            reason_codes=("timeline_replan_authority_class_not_eligible",),
        )

    signal = RealityChangeSignal(
        signal_id=f"timeline:{event.event_id}",
        tenant_id=event.tenant_id,
        observed_at=event.observed_at,
        evidence_refs=tuple(
            dict.fromkeys(
                (
                    *event.evidence_refs,
                    f"timeline-event://{event.event_id}/{event.fingerprint}",
                )
            )
        ),
        affected_resource_refs=rule.affected_resource_refs,
        invalidated_truth_requirement_ids=rule.invalidated_truth_requirement_ids,
        changed_capability_refs=rule.changed_capability_refs,
        severity=rule.severity,
    )
    reason = (
        "timeline_replan_verified_external_resource_change"
        if authority in _EXTERNAL_RESOURCE_AUTHORITIES
        else "timeline_replan_governed_company_change"
    )
    return TimelineReplanDecision(
        event_id=event.event_id,
        eligible=True,
        reason_codes=(reason,),
        signal=signal,
    )


def timeline_events_to_replan_signals(
    *,
    events: tuple[RealWorldTimelineEvent, ...],
    rules: tuple[TimelineReplanRule, ...],
    tenant_id: str,
    now: datetime,
) -> tuple[RealityChangeSignal, ...]:
    """Convert only exact mapped events; no rule means no replan trigger."""

    _now_is_aware(now)
    rule_map = {item.event_type: item for item in rules}
    if len(rule_map) != len(rules):
        raise ValueError("timeline_replan_rule_event_types_must_be_unique")
    signals: list[RealityChangeSignal] = []
    for event in events:
        event = _validated_event(event)
        if event.tenant_id != tenant_id:
            raise ValueError("timeline_replan_cross_tenant_event_forbidden")
        rule = rule_map.get(event.event_type)
        if rule is None:
            continue
        decision = evaluate_timeline_event_for_replan(event=event, rule=rule, now=now)
        if decision.signal is not None:
            signals.append(decision.signal)
    return tuple(signals)
