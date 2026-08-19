from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.objective_replanning import LaneReplanDisposition, assess_objective_replan_scope
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.timeline_replanning_adapter import (
    TimelineReplanRule,
    evaluate_timeline_event_for_replan,
    timeline_events_to_replan_signals,
)

NOW = datetime(2026, 8, 19, 8, 30, tzinfo=timezone.utc)
RESOURCE = "store://fulya/inventory"


def _event(
    *,
    event_id: str = "event-1",
    event_type: str = "eay.company.inventory.changed",
    authority: TimelineAuthorityClass = TimelineAuthorityClass.VERIFIED_COMPANY,
    confidence: float = 0.99,
    observed_at: datetime = NOW,
):
    return build_timeline_event(
        event_id=event_id,
        event_type=event_type,
        event_kind=(
            TimelineEventKind.EXTERNAL_CONTEXT
            if authority is TimelineAuthorityClass.VERIFIED_EXTERNAL
            else TimelineEventKind.COMPANY_ASSERTION
        ),
        source_ref="source://timeline-test",
        tenant_id="YS_TR",
        occurred_at=observed_at - timedelta(seconds=1),
        observed_at=observed_at,
        data_ref="data://timeline-test/event",
        authority_class=authority,
        confidence=confidence,
        object_relations=(
            TimelineObjectRelation(
                object_ref=RESOURCE,
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=("evidence://timeline/event-1",),
    )


def _inventory_lane() -> ParallelMissionLane:
    step = MissionStep(step_id="read", description="read inventory")
    definition = MissionDefinition(
        mission_id="mission-inventory",
        objective="inspect inventory",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="read",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref="company.inventory.read",
        decision_truth_requirement_id="truth.inventory.v2",
    )
    return ParallelMissionLane(
        lane_id="inventory-read",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        exclusive_resource_refs=(RESOURCE,),
    )


def test_verified_company_timeline_change_generates_signal_and_replans_affected_lane():
    event = _event()
    rule = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
        invalidated_truth_requirement_ids=("truth.inventory.v2",),
        changed_capability_refs=("company.inventory.read",),
    )
    signals = timeline_events_to_replan_signals(
        events=(event,),
        rules=(rule,),
        tenant_id="YS_TR",
        now=NOW,
    )
    assert len(signals) == 1
    assert signals[0].signal_id == "timeline:event-1"
    assert signals[0].execution_authority_granted is False

    lane = _inventory_lane()
    plan = ParallelMissionPlan(
        objective_ref="objective://inventory",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    scope = assess_objective_replan_scope(plan=plan, signals=signals)
    assert scope.auto_replan_lane_ids == ("inventory-read",)
    assert scope.assessments[0].disposition is LaneReplanDisposition.REPLAN_SAFE


def test_verified_external_event_can_trigger_only_explicit_resource_replan():
    event = _event(
        event_type="eay.external.weather.alert",
        authority=TimelineAuthorityClass.VERIFIED_EXTERNAL,
    )
    allowed = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
        allow_verified_external_resource_replan=True,
    )
    decision = evaluate_timeline_event_for_replan(event=event, rule=allowed, now=NOW)
    assert decision.eligible is True
    assert decision.signal is not None
    assert decision.signal.affected_resource_refs == (RESOURCE,)
    assert decision.signal.invalidated_truth_requirement_ids == ()
    assert decision.signal.changed_capability_refs == ()

    forbidden = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
        invalidated_truth_requirement_ids=("truth.inventory.v2",),
        allow_verified_external_resource_replan=True,
    )
    denied = evaluate_timeline_event_for_replan(event=event, rule=forbidden, now=NOW)
    assert denied.eligible is False
    assert denied.signal is None
    assert denied.reason_codes == ("timeline_replan_company_change_requires_company_authority",)


def test_ambient_observation_never_becomes_replan_authority_even_with_mapping():
    event = _event(authority=TimelineAuthorityClass.AMBIENT_UNTRUSTED)
    rule = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
    )
    decision = evaluate_timeline_event_for_replan(event=event, rule=rule, now=NOW)
    assert decision.eligible is False
    assert decision.reason_codes == ("timeline_replan_observational_event_not_actionable",)


def test_stale_timeline_event_is_not_used_for_current_replanning():
    event = _event(observed_at=NOW - timedelta(hours=2))
    rule = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
        max_observation_age_seconds=300,
    )
    decision = evaluate_timeline_event_for_replan(event=event, rule=rule, now=NOW)
    assert decision.eligible is False
    assert decision.reason_codes == ("timeline_replan_event_stale",)


def test_tampered_timeline_event_fails_integrity_before_replan_decision():
    event = _event()
    tampered = event.model_copy(update={"confidence": 0.1})
    rule = TimelineReplanRule(
        event_type=event.event_type,
        affected_resource_refs=(RESOURCE,),
    )
    with pytest.raises(ValueError, match="timeline_event_fingerprint_mismatch"):
        evaluate_timeline_event_for_replan(event=tampered, rule=rule, now=NOW)
