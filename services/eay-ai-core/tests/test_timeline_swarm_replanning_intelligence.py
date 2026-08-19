from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from app.engine_gateway import EngineGateway
from app.global_objective_arbiter import GlobalObjectiveCandidate
from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.multi_objective_swarm_runtime import MultiObjectiveBindings
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelMissionLane,
    ParallelMissionPlan,
)
from app.real_world_timeline import (
    TimelineAuthorityClass,
    TimelineEventKind,
    TimelineObjectKind,
    TimelineObjectQualifier,
    TimelineObjectRelation,
    build_timeline_event,
)
from app.timeline_replanning_adapter import TimelineReplanRule
from app.timeline_swarm_replanning import (
    TimelineSwarmReplanDisposition,
    execute_timeline_replanned_multi_objective_round,
    prepare_timeline_replanned_candidates,
)

NOW = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)
TENANT = "YS_TR"
RESOURCE = "store://fulya/inventory"


async def _unused_reasoning_writer(_receipt) -> str:
    return "reasoning://unused"


def _event(*, authority=TimelineAuthorityClass.VERIFIED_COMPANY):
    return build_timeline_event(
        event_id="inventory-change-1",
        event_type="eay.company.inventory.changed",
        event_kind=TimelineEventKind.COMPANY_ASSERTION,
        source_ref="source://company-world",
        tenant_id=TENANT,
        occurred_at=NOW - timedelta(seconds=2),
        observed_at=NOW - timedelta(seconds=1),
        data_ref="world-assertion://inventory/1",
        authority_class=authority,
        confidence=0.99,
        object_relations=(
            TimelineObjectRelation(
                object_ref=RESOURCE,
                object_kind=TimelineObjectKind.WORLD_ENTITY,
                qualifier=TimelineObjectQualifier.AFFECTED,
            ),
        ),
        evidence_refs=("evidence://company/inventory/1",),
    )


def _rule() -> TimelineReplanRule:
    return TimelineReplanRule(
        event_type="eay.company.inventory.changed",
        affected_resource_refs=(RESOURCE,),
        invalidated_truth_requirement_ids=("truth.inventory.v2",),
        changed_capability_refs=("company.inventory.read",),
    )


def _resource_rule() -> TimelineReplanRule:
    return TimelineReplanRule(
        event_type="eay.company.inventory.changed",
        affected_resource_refs=(RESOURCE,),
    )


def _read_lane(
    *,
    mission_id: str = "mission-inventory-v1",
    requires_truth: bool = True,
) -> ParallelMissionLane:
    step = MissionStep(step_id="read", description="read current inventory")
    definition = MissionDefinition(
        mission_id=mission_id,
        objective="inspect inventory",
        tenant_id=TENANT,
        steps=(step,),
    )
    return ParallelMissionLane(
        lane_id="inventory-read",
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(
            MissionExecutionSpec(
                step_id="read",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="company.inventory.read",
                decision_truth_requirement_id=(
                    "truth.inventory.v2" if requires_truth else None
                ),
            ),
        ),
        exclusive_resource_refs=(RESOURCE,),
    )


def _attempted_write_lane() -> ParallelMissionLane:
    step = MissionStep(
        step_id="write",
        description="write inventory correction",
        side_effect=True,
        idempotency_key="inventory-write-1",
        effect_verifier_ref="effect://inventory/readback",
    )
    definition = MissionDefinition(
        mission_id="mission-inventory-write",
        objective="correct inventory",
        tenant_id=TENANT,
        steps=(step,),
    )
    checkpoint = new_checkpoint(definition, now=NOW - timedelta(minutes=1))
    checkpoint = record_step_result(
        definition,
        checkpoint,
        step_id="write",
        succeeded=False,
        evidence_refs=("attempt://inventory/write/1",),
        error="write_failed",
        now=NOW - timedelta(seconds=20),
    )
    return ParallelMissionLane(
        lane_id="inventory-write",
        definition=definition,
        checkpoint=checkpoint,
        specs=(
            MissionExecutionSpec(
                step_id="write",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="company.inventory.write",
            ),
        ),
        exclusive_resource_refs=(RESOURCE,),
    )


def _candidate(objective_ref: str, lane: ParallelMissionLane) -> GlobalObjectiveCandidate:
    return GlobalObjectiveCandidate(
        objective_ref=objective_ref,
        tenant_id=TENANT,
        plan=ParallelMissionPlan(
            objective_ref=objective_ref,
            tenant_id=TENANT,
            lanes=(lane,),
        ),
    )


def _bindings() -> dict[str, ParallelLaneBindings]:
    async def read_handler(_definition, _step, _state, _idempotency_key):
        return CapabilityExecutionOutcome(
            succeeded=True,
            evidence_refs=("company-read://inventory/fresh",),
        )

    return {
        "inventory-read": ParallelLaneBindings(
            gateway=cast(EngineGateway, object()),
            reasoning_evidence_writer=cast(object, _unused_reasoning_writer),
            capability_handlers={"company.inventory.read": read_handler},
        )
    }


@pytest.mark.asyncio
async def test_replanned_lane_still_requires_fresh_live_truth_receipt_before_execution():
    original = _candidate("objective://inventory", _read_lane())
    replacement = _read_lane(mission_id="mission-inventory-v2")

    result = await execute_timeline_replanned_multi_objective_round(
        candidates=(original,),
        events=(_event(),),
        rules=(_rule(),),
        replacements_by_objective={
            original.objective_ref: {replacement.lane_id: replacement}
        },
        bindings=MultiObjectiveBindings(
            by_objective={original.objective_ref: _bindings()}
        ),
        active_leases=(),
        now=NOW,
    )

    decision = result.preparation.decisions[0]
    assert decision.disposition is TimelineSwarmReplanDisposition.REPLANNED
    assert decision.auto_replan_lane_ids == ("inventory-read",)
    assert decision.execution_authority_granted is False
    assert result.execution is not None
    executed = result.execution.objective_rounds[0].results[0]
    assert executed.summary is not None
    assert executed.summary.checkpoint.mission_id == "mission-inventory-v2"
    assert executed.summary.checkpoint.sequence == 0
    assert executed.summary.blockers == ("live_company_truth_receipt_missing:read",)


@pytest.mark.asyncio
async def test_resource_only_replan_executes_fresh_replacement_through_canonical_runtime():
    original = _candidate(
        "objective://inventory-resource-read",
        _read_lane(mission_id="mission-resource-v1", requires_truth=False),
    )
    replacement = _read_lane(
        mission_id="mission-resource-v2",
        requires_truth=False,
    )

    result = await execute_timeline_replanned_multi_objective_round(
        candidates=(original,),
        events=(_event(),),
        rules=(_resource_rule(),),
        replacements_by_objective={
            original.objective_ref: {replacement.lane_id: replacement}
        },
        bindings=MultiObjectiveBindings(
            by_objective={original.objective_ref: _bindings()}
        ),
        active_leases=(),
        now=NOW,
    )

    assert result.preparation.decisions[0].disposition is TimelineSwarmReplanDisposition.REPLANNED
    assert result.execution is not None
    executed = result.execution.objective_rounds[0].results[0]
    assert executed.summary is not None
    assert executed.summary.checkpoint.mission_id == "mission-resource-v2"
    assert executed.summary.checkpoint.sequence > 0
    assert executed.summary.blockers == ()


@pytest.mark.asyncio
async def test_missing_fresh_replacement_holds_stale_objective_instead_of_executing_it():
    candidate = _candidate("objective://inventory", _read_lane())

    result = await execute_timeline_replanned_multi_objective_round(
        candidates=(candidate,),
        events=(_event(),),
        rules=(_rule(),),
        replacements_by_objective={},
        bindings=MultiObjectiveBindings(by_objective={}),
        active_leases=(),
        now=NOW,
    )

    decision = result.preparation.decisions[0]
    assert decision.disposition is TimelineSwarmReplanDisposition.REPLACEMENT_REQUIRED
    assert decision.auto_replan_lane_ids == ("inventory-read",)
    assert result.execution is None
    assert result.active_leases_after_round == ()


@pytest.mark.asyncio
async def test_attempted_side_effect_objective_is_held_for_review_not_replanned_or_replayed():
    candidate = _candidate("objective://inventory-write", _attempted_write_lane())

    result = await execute_timeline_replanned_multi_objective_round(
        candidates=(candidate,),
        events=(_event(),),
        rules=(_resource_rule(),),
        replacements_by_objective={},
        bindings=MultiObjectiveBindings(by_objective={}),
        active_leases=(),
        now=NOW,
    )

    decision = result.preparation.decisions[0]
    assert decision.disposition is TimelineSwarmReplanDisposition.HOLD_FOR_REVIEW
    assert decision.review_lane_ids == ("inventory-write",)
    assert result.execution is None


def test_observational_timeline_event_cannot_replan_and_candidate_remains_unchanged():
    candidate = _candidate("objective://inventory", _read_lane())
    preparation = prepare_timeline_replanned_candidates(
        candidates=(candidate,),
        events=(_event(authority=TimelineAuthorityClass.AMBIENT_UNTRUSTED),),
        rules=(_rule(),),
        replacements_by_objective={},
        now=NOW,
    )

    decision = preparation.decisions[0]
    assert decision.disposition is TimelineSwarmReplanDisposition.UNAFFECTED
    assert decision.signal_ids == ()
    assert preparation.runnable_candidates[0].plan == candidate.plan


def test_replacement_for_unknown_objective_fails_closed_before_any_execution():
    candidate = _candidate("objective://inventory", _read_lane())
    with pytest.raises(ValueError, match="timeline_swarm_replacements_reference_unknown_objective"):
        prepare_timeline_replanned_candidates(
            candidates=(candidate,),
            events=(_event(),),
            rules=(_rule(),),
            replacements_by_objective={
                "objective://invented": {"inventory-read": _read_lane()}
            },
            now=NOW,
        )
