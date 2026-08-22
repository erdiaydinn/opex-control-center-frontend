from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.global_lane_lease_broker import GlobalLaneLeaseAdmission
from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.multi_objective_swarm_runtime import MultiObjectiveExecutionRound
from app.objective_decomposition_admission import (
    ObjectiveDecompositionPolicy,
    ObjectiveDecompositionProposal,
    ProposedObjectiveLane,
)
from app.parallel_mission_orchestration import (
    ParallelLaneDisposition,
    ParallelLaneResult,
    ParallelMissionLane,
    ParallelMissionRound,
)
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.situation_detection import SituationCandidate, detect_situations
from app.situation_lifecycle import (
    SituationLifecycleStatus,
    advance_situation_lifecycle,
    new_situation_lifecycle,
)
from app.situation_objective_admission import (
    SituationObjectiveRule,
    admit_situation_driven_objective,
)
from app.swarm_execution_telemetry import build_swarm_execution_telemetry
from app.swarm_telemetry_history import (
    PressureTrendDirection,
    append_swarm_telemetry,
    new_swarm_telemetry_history,
    swarm_pressure_trend,
)
from app.swarm_worker_registry import SwarmLaneRequirement, SwarmWorkerClass


NOW = datetime(2026, 8, 19, 10, 15, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECT = "store://fulya"
REVIEW_REF = "review://situation/orders-weather-otp/v1"


def _execution_round(*, pressured: bool) -> MultiObjectiveExecutionRound:
    if pressured:
        objective = ParallelMissionRound(
            objective_ref="objective://ops",
            tenant_id=TENANT,
            selected_lane_ids=("orders-read",),
            results=(
                ParallelLaneResult(
                    lane_id="orders-read",
                    disposition=ParallelLaneDisposition.DEFERRED,
                    blockers=("live_company_truth_receipt_missing:read-orders",),
                ),
            ),
        )
        deferred = {
            "objective://inventory::write": ("global_lane_resource_lease_conflict:store://fulya",),
            "objective://ops::orders-read": ("live_company_truth_receipt_missing:read-orders",),
        }
    else:
        objective = ParallelMissionRound(
            objective_ref="objective://ops",
            tenant_id=TENANT,
            selected_lane_ids=(),
            results=(),
        )
        deferred = {}
    return MultiObjectiveExecutionRound(
        admission=GlobalLaneLeaseAdmission(selected=(), deferred={}, issued_leases=()),
        objective_rounds=(objective,),
        deferred=deferred,
        active_leases_after_round=(),
    )


def _telemetry(at: datetime, *, pressured: bool):
    return build_swarm_execution_telemetry(
        execution_round=_execution_round(pressured=pressured),
        tenant_id=TENANT,
        observed_at=at,
    )


def _event(
    event_id: str,
    event_type: str,
    authority: TimelineAuthorityClass,
    at: datetime,
):
    kind = (
        TimelineEventKind.EXTERNAL_CONTEXT
        if authority is TimelineAuthorityClass.VERIFIED_EXTERNAL
        else TimelineEventKind.COMPANY_ASSERTION
    )
    return build_timeline_event(
        event_id=event_id,
        event_type=event_type,
        event_kind=kind,
        source_ref=f"source://{event_id}",
        tenant_id=TENANT,
        occurred_at=at - timedelta(seconds=1),
        observed_at=at,
        data_ref=f"data://{event_id}",
        authority_class=authority,
        confidence=0.96,
        object_relations=(
            TimelineObjectRelation(
                object_ref=OBJECT,
                object_kind=TimelineObjectKind.LOCATION,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=(f"evidence://{event_id}",),
    )


def _situation(at: datetime, suffix: str) -> SituationCandidate:
    events = (
        _event(
            f"orders-{suffix}",
            "eay.company.orders.spike",
            TimelineAuthorityClass.VERIFIED_COMPANY,
            at,
        ),
        _event(
            f"weather-{suffix}",
            "eay.external.weather.rain",
            TimelineAuthorityClass.VERIFIED_EXTERNAL,
            at,
        ),
        _event(
            f"otp-{suffix}",
            "eay.company.otp.degraded",
            TimelineAuthorityClass.GOVERNED_OPERATIONAL,
            at,
        ),
    )
    situations = detect_situations(
        events=events,
        telemetry=_telemetry(at, pressured=True),
        tenant_id=TENANT,
        now=at,
    )
    assert len(situations) == 1
    return situations[0]


def test_swarm_pressure_history_is_cutoff_safe_and_detects_rising_pressure():
    low = _telemetry(NOW, pressured=False)
    high_at = NOW + timedelta(minutes=5)
    high = _telemetry(high_at, pressured=True)

    history = new_swarm_telemetry_history(tenant_id=TENANT)
    history = append_swarm_telemetry(
        history=history,
        snapshot=low,
        recorded_at=NOW + timedelta(seconds=5),
    )
    history = append_swarm_telemetry(
        history=history,
        snapshot=high,
        recorded_at=high_at + timedelta(minutes=5),
    )

    historical = swarm_pressure_trend(
        history=history,
        as_of=high_at + timedelta(minutes=1),
    )
    assert historical.sample_count == 1
    assert historical.direction is PressureTrendDirection.INSUFFICIENT

    current = swarm_pressure_trend(
        history=history,
        as_of=high_at + timedelta(minutes=6),
    )
    assert current.sample_count == 2
    assert current.direction is PressureTrendDirection.RISING
    assert current.pressure_delta > 0
    assert current.deferred_lane_delta == 2
    assert current.execution_authority_granted is False


def test_swarm_pressure_history_rejects_cross_tenant_snapshot():
    history = new_swarm_telemetry_history(tenant_id="tenant:a")
    snapshot = _telemetry(NOW, pressured=True)
    with pytest.raises(ValueError, match="swarm_telemetry_history_cross_tenant_snapshot_forbidden"):
        append_swarm_telemetry(
            history=history,
            snapshot=snapshot,
            recorded_at=NOW + timedelta(seconds=1),
        )


def test_situation_lifecycle_tracks_new_ongoing_resolved_and_reopened_without_authority():
    first = _situation(NOW, "a")
    lifecycle = new_situation_lifecycle(tenant_id=TENANT, as_of=NOW)
    lifecycle = advance_situation_lifecycle(
        previous=lifecycle,
        candidates=(first,),
        as_of=NOW,
        resolve_after_seconds=300,
    )
    assert lifecycle.records[0].status is SituationLifecycleStatus.NEW

    second_at = NOW + timedelta(minutes=1)
    second = _situation(second_at, "b")
    lifecycle = advance_situation_lifecycle(
        previous=lifecycle,
        candidates=(second,),
        as_of=second_at,
        resolve_after_seconds=300,
    )
    record = lifecycle.records[0]
    assert record.status is SituationLifecycleStatus.ONGOING
    assert record.occurrence_count == 2

    resolved_at = second_at + timedelta(minutes=6)
    lifecycle = advance_situation_lifecycle(
        previous=lifecycle,
        candidates=(),
        as_of=resolved_at,
        resolve_after_seconds=300,
    )
    assert lifecycle.records[0].status is SituationLifecycleStatus.RESOLVED
    assert lifecycle.records[0].resolved_at == resolved_at

    reopened_at = resolved_at + timedelta(minutes=1)
    reopened = _situation(reopened_at, "c")
    lifecycle = advance_situation_lifecycle(
        previous=lifecycle,
        candidates=(reopened,),
        as_of=reopened_at,
        resolve_after_seconds=300,
    )
    record = lifecycle.records[0]
    assert record.status is SituationLifecycleStatus.REOPENED
    assert record.occurrence_count == 3
    assert record.truth_authority_granted is False
    assert record.replanning_authority_granted is False
    assert record.execution_authority_granted is False


def test_tampered_situation_lifecycle_snapshot_fails_before_advancement():
    first = _situation(NOW, "tamper")
    lifecycle = advance_situation_lifecycle(
        previous=new_situation_lifecycle(tenant_id=TENANT, as_of=NOW),
        candidates=(first,),
        as_of=NOW,
    )
    tampered = lifecycle.model_copy(update={"tenant_id": "tenant:other"})

    with pytest.raises(ValueError, match="situation_lifecycle_cross_tenant_record_forbidden"):
        advance_situation_lifecycle(
            previous=tampered,
            candidates=(),
            as_of=NOW + timedelta(minutes=1),
        )


def _read_only_proposal(candidate: SituationCandidate) -> ObjectiveDecompositionProposal:
    step = MissionStep(step_id="read-orders", description="Investigate verified Fulya situation")
    definition = MissionDefinition(
        mission_id="mission-situation-fulya-orders",
        objective="Investigate Fulya order/weather/OTP situation",
        tenant_id=TENANT,
        steps=(step,),
    )
    lane = ParallelMissionLane(
        lane_id="situation-company-read",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=candidate.detected_at),
        specs=(
            MissionExecutionSpec(
                step_id="read-orders",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="company.orders.read",
            ),
        ),
        priority=90,
    )
    proposed = ProposedObjectiveLane(
        lane=lane,
        profile=ParallelLaneSchedulingProfile(
            lane_id=lane.lane_id,
            scheduling_class=LaneSchedulingClass.COMPANY_READ,
            estimated_cost_units=5,
            concurrency_weight=1,
            shedable=True,
            preemptible=True,
        ),
        requirement=SwarmLaneRequirement(
            lane_id=lane.lane_id,
            required_worker_classes=(SwarmWorkerClass.COMPANY_READ,),
            required_capability_refs=("company.orders.read",),
        ),
        evidence_refs=(f"situation-candidate://{candidate.fingerprint}",),
    )
    return ObjectiveDecompositionProposal(
        objective_ref="objective://situation/fulya/orders",
        tenant_id=TENANT,
        lanes=(proposed,),
        decomposition_evidence_refs=(
            f"situation-candidate://{candidate.fingerprint}",
            REVIEW_REF,
        ),
        max_parallel_lanes=1,
    )


def _rule() -> SituationObjectiveRule:
    return SituationObjectiveRule(
        rule_ref="situation-rule://fulya/orders-weather-otp/v1",
        tenant_id=TENANT,
        objective_ref_prefix="objective://situation/",
        required_domains=("orders", "otp", "weather"),
        review_evidence_ref=REVIEW_REF,
    )


def test_verified_situation_can_wake_read_only_worker_objective_but_not_grant_execution():
    candidate = _situation(NOW, "objective")
    admission = admit_situation_driven_objective(
        candidate=candidate,
        proposal=_read_only_proposal(candidate),
        rule=_rule(),
        decomposition_policy=ObjectiveDecompositionPolicy(
            max_lanes=8,
            max_mutating_lanes=0,
            max_total_cost_units=100,
            max_total_concurrency_weight=16,
        ),
        now=NOW + timedelta(seconds=30),
    )

    assert admission.eligible_for_worker_scheduling is True
    assert admission.admitted.mutating_lane_count == 0
    assert admission.admitted.plan.lanes[0].lane_id == "situation-company-read"
    assert admission.truth_authority_granted is False
    assert admission.replanning_authority_granted is False
    assert admission.execution_authority_granted is False


def test_situation_objective_requires_exact_candidate_and_review_evidence():
    candidate = _situation(NOW, "evidence")
    proposal = _read_only_proposal(candidate).model_copy(
        update={"decomposition_evidence_refs": (REVIEW_REF,)}
    )

    with pytest.raises(ValueError, match="situation_objective_root_evidence_missing"):
        admit_situation_driven_objective(
            candidate=candidate,
            proposal=proposal,
            rule=_rule(),
            decomposition_policy=ObjectiveDecompositionPolicy(),
            now=NOW + timedelta(seconds=30),
        )


def test_situation_objective_v1_rejects_mutating_lane_before_swarm_admission():
    candidate = _situation(NOW, "mutation")
    step = MissionStep(
        step_id="write",
        description="forbidden automatic write",
        side_effect=True,
        idempotency_key="situation:forbidden:write",
        effect_verifier_ref="effect://verify",
    )
    definition = MissionDefinition(
        mission_id="mission-situation-forbidden-write",
        objective="must not auto-write from situation",
        tenant_id=TENANT,
        steps=(step,),
    )
    lane = ParallelMissionLane(
        lane_id="forbidden-write",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(
            MissionExecutionSpec(
                step_id="write",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="company.inventory.write",
            ),
        ),
        exclusive_resource_refs=(OBJECT,),
    )
    proposal = ObjectiveDecompositionProposal(
        objective_ref="objective://situation/fulya/write",
        tenant_id=TENANT,
        lanes=(
            ProposedObjectiveLane(
                lane=lane,
                profile=ParallelLaneSchedulingProfile(
                    lane_id=lane.lane_id,
                    scheduling_class=LaneSchedulingClass.EXECUTION,
                    shedable=False,
                    preemptible=False,
                ),
                requirement=SwarmLaneRequirement(
                    lane_id=lane.lane_id,
                    required_worker_classes=(SwarmWorkerClass.EXECUTION,),
                    required_capability_refs=("company.inventory.write",),
                ),
                evidence_refs=(f"situation-candidate://{candidate.fingerprint}",),
            ),
        ),
        decomposition_evidence_refs=(
            f"situation-candidate://{candidate.fingerprint}",
            REVIEW_REF,
        ),
        max_parallel_lanes=1,
    )

    with pytest.raises(ValueError, match="situation_objective_v1_forbids_mutating_lane"):
        admit_situation_driven_objective(
            candidate=candidate,
            proposal=proposal,
            rule=_rule(),
            decomposition_policy=ObjectiveDecompositionPolicy(),
            now=NOW + timedelta(seconds=30),
        )
