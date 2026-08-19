import asyncio
from datetime import datetime, timedelta, timezone
from typing import cast

import pytest

from app.engine_gateway import EngineGateway
from app.global_lane_lease_broker import (
    GlobalLaneLeaseAdmission,
    GlobalLaneSelection,
    LaneLeaseReleaseDisposition,
)
from app.global_objective_arbiter import GlobalObjectiveCandidate
from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStatus, MissionStep, new_checkpoint, record_step_result
from app.multi_objective_swarm_runtime import (
    MultiObjectiveBindings,
    execute_multi_objective_lane_round,
    validate_lane_lease_admission,
)
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelMissionLane,
    ParallelMissionPlan,
)


NOW = datetime(2026, 8, 19, 9, 30, tzinfo=timezone.utc)


async def _unused_reasoning_writer(_receipt) -> str:
    return "reasoning://unused"


def _lane(
    lane_id: str,
    *,
    resource_ref: str | None = None,
    idempotency_key: str | None = None,
    priority: int = 50,
    terminal: bool = False,
) -> ParallelMissionLane:
    mutating = resource_ref is not None
    step = MissionStep(
        step_id="step",
        description=lane_id,
        side_effect=mutating,
        idempotency_key=idempotency_key if mutating else None,
        effect_verifier_ref="effect://verify" if mutating else None,
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective-{lane_id}",
        tenant_id="YS_TR",
        steps=(step,),
    )
    checkpoint = new_checkpoint(definition, now=NOW)
    if terminal:
        checkpoint = record_step_result(
            definition,
            checkpoint,
            step_id="step",
            succeeded=True,
            evidence_refs=("evidence://terminal",),
            now=NOW + timedelta(seconds=1),
        )
        assert checkpoint.status is MissionStatus.COMPLETED
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=checkpoint,
        specs=(
            MissionExecutionSpec(
                step_id="step",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref="capability://write" if mutating else "capability://read",
            ),
        ),
        priority=priority,
        exclusive_resource_refs=((resource_ref,) if resource_ref else ()),
    )


def _candidate(
    objective_ref: str,
    lanes: tuple[ParallelMissionLane, ...],
    *,
    priority: int,
) -> GlobalObjectiveCandidate:
    return GlobalObjectiveCandidate(
        objective_ref=objective_ref,
        tenant_id="YS_TR",
        priority=priority,
        plan=ParallelMissionPlan(
            objective_ref=objective_ref,
            tenant_id="YS_TR",
            lanes=lanes,
            max_parallel_lanes=min(16, len(lanes)),
        ),
    )


def _bindings_for(
    candidate: GlobalObjectiveCandidate,
    *,
    read_started: list[str] | None = None,
    read_gate: asyncio.Event | None = None,
    ambiguous_write_lane: str | None = None,
) -> dict[str, ParallelLaneBindings]:
    result: dict[str, ParallelLaneBindings] = {}
    for lane in candidate.plan.lanes:
        async def handler(definition, _step, _state, _idempotency_key, *, _lane_id=lane.lane_id):
            if _lane_id.endswith("read") or "read" in _lane_id:
                if read_started is not None:
                    read_started.append(_lane_id)
                if read_gate is not None:
                    if len(read_started or ()) >= 2:
                        read_gate.set()
                    await asyncio.wait_for(read_gate.wait(), timeout=1.0)
                return CapabilityExecutionOutcome(
                    succeeded=True,
                    evidence_refs=(f"read-evidence://{_lane_id}",),
                )
            if _lane_id == ambiguous_write_lane:
                return CapabilityExecutionOutcome(
                    succeeded=False,
                    ambiguous_outcome=True,
                    evidence_refs=(f"write-evidence://{_lane_id}/ambiguous",),
                    error_code="timeout_after_submit",
                )
            return CapabilityExecutionOutcome(
                succeeded=True,
                effect_verified=True,
                evidence_refs=(f"effect-verification://{_lane_id}",),
                transaction_ref=f"transaction://{_lane_id}",
            )

        result[lane.lane_id] = ParallelLaneBindings(
            gateway=cast(EngineGateway, object()),
            reasoning_evidence_writer=cast(object, _unused_reasoning_writer),
            capability_handlers={
                "capability://read": handler,
                "capability://write": handler,
            },
        )
    return result


@pytest.mark.asyncio
async def test_conflicting_write_serializes_only_write_while_reads_execute_across_objectives() -> None:
    first = _candidate(
        "objective-a",
        (
            _lane("a-write", resource_ref="store:fulya:inventory", idempotency_key="idem-a", priority=90),
            _lane("a-read", priority=80),
        ),
        priority=90,
    )
    second = _candidate(
        "objective-b",
        (
            _lane("b-write", resource_ref="store:fulya:inventory", idempotency_key="idem-b", priority=90),
            _lane("b-read", priority=80),
        ),
        priority=80,
    )
    read_started: list[str] = []
    read_gate = asyncio.Event()
    result = await execute_multi_objective_lane_round(
        candidates=(first, second),
        bindings=MultiObjectiveBindings(
            by_objective={
                first.objective_ref: _bindings_for(first, read_started=read_started, read_gate=read_gate),
                second.objective_ref: _bindings_for(second, read_started=read_started, read_gate=read_gate),
            }
        ),
        active_leases=(),
        now=NOW,
    )

    assert {"a-read", "b-read"} <= set(read_started)
    assert "objective-b::b-write" in result.deferred
    assert result.deferred["objective-b::b-write"] == ("global_lane_resource_lease_conflict",)
    assert len(result.released_lease_ids) == 1
    released = next(item for item in result.active_leases_after_round if item.lease_id in result.released_lease_ids)
    assert released.release_disposition is LaneLeaseReleaseDisposition.VERIFIED_EFFECT
    assert released.execution_authority_granted is False

    second_write_only = _candidate(
        "objective-b-next",
        (_lane("b-next-write", resource_ref="store:fulya:inventory", idempotency_key="idem-b-next"),),
        priority=80,
    )
    second_round = await execute_multi_objective_lane_round(
        candidates=(second_write_only,),
        bindings=MultiObjectiveBindings(
            by_objective={second_write_only.objective_ref: _bindings_for(second_write_only)}
        ),
        active_leases=result.active_leases_after_round,
        now=NOW + timedelta(minutes=1),
    )
    assert len(second_round.admission.selected) == 1
    assert second_round.deferred == {}


@pytest.mark.asyncio
async def test_ambiguous_write_holds_lease_and_blocks_following_objective() -> None:
    first = _candidate(
        "objective-a",
        (_lane("a-write", resource_ref="store:fulya:inventory", idempotency_key="idem-a"),),
        priority=90,
    )
    first_round = await execute_multi_objective_lane_round(
        candidates=(first,),
        bindings=MultiObjectiveBindings(
            by_objective={
                first.objective_ref: _bindings_for(first, ambiguous_write_lane="a-write")
            }
        ),
        active_leases=(),
        now=NOW,
    )

    assert len(first_round.held_lease_ids) == 1
    held = next(item for item in first_round.active_leases_after_round if item.lease_id in first_round.held_lease_ids)
    assert held.released_at is None

    contender = _candidate(
        "objective-b",
        (_lane("b-write", resource_ref="store:fulya:inventory", idempotency_key="idem-b"),),
        priority=80,
    )
    blocked = await execute_multi_objective_lane_round(
        candidates=(contender,),
        bindings=MultiObjectiveBindings(by_objective={contender.objective_ref: _bindings_for(contender)}),
        active_leases=first_round.active_leases_after_round,
        now=NOW + timedelta(seconds=10),
    )
    assert blocked.admission.selected == ()
    assert blocked.deferred["objective-b::b-write"] == ("global_lane_resource_lease_conflict",)


@pytest.mark.asyncio
async def test_terminal_lane_is_deferred_before_global_lease_admission() -> None:
    terminal = _candidate(
        "objective-terminal",
        (_lane("terminal-write", resource_ref="store:fulya:inventory", idempotency_key="terminal", terminal=True),),
        priority=100,
    )
    result = await execute_multi_objective_lane_round(
        candidates=(terminal,),
        bindings=MultiObjectiveBindings(by_objective={}),
        active_leases=(),
        now=NOW + timedelta(minutes=1),
    )

    assert result.admission.selected == ()
    assert result.admission.issued_leases == ()
    assert result.deferred == {"objective-terminal::terminal-write": ("global_lane_terminal",)}


def test_unknown_or_tenant_drifted_admission_reference_fails_closed() -> None:
    candidate = _candidate(
        "objective-a",
        (_lane("read"),),
        priority=50,
    )
    unknown = GlobalLaneLeaseAdmission(
        selected=(
            GlobalLaneSelection(
                objective_ref="objective-a",
                tenant_id="YS_TR",
                lane_id="invented-lane",
                mutating=False,
            ),
        ),
        deferred={},
        issued_leases=(),
    )
    with pytest.raises(ValueError, match="multi_objective_admission_unknown_lane"):
        validate_lane_lease_admission(candidates=(candidate,), admission=unknown)

    tenant_drift = GlobalLaneLeaseAdmission(
        selected=(
            GlobalLaneSelection(
                objective_ref="objective-a",
                tenant_id="DE",
                lane_id="read",
                mutating=False,
            ),
        ),
        deferred={},
        issued_leases=(),
    )
    with pytest.raises(ValueError, match="multi_objective_admission_tenant_mismatch"):
        validate_lane_lease_admission(candidates=(candidate,), admission=tenant_drift)
