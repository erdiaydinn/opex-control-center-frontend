from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mission_execution import (
    CapabilityExecutionOutcome,
    MissionExecutionKind,
    MissionExecutionSpec,
)
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelLaneDisposition,
    ParallelMissionLane,
    ParallelMissionPlan,
    execute_parallel_mission_round,
)

NOW = datetime(2026, 8, 19, 1, 45, tzinfo=timezone.utc)


class _UnusedGateway:
    pass


def _writer(_receipt: object) -> str:
    return "evidence://reasoning"


def _lane(*, lane_id: str, capability_ref: str, required_permission: str | None = None):
    step = MissionStep(
        step_id="step",
        description="advance",
        required_permission=required_permission,
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id="YS_TR",
        steps=(step,),
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(
            MissionExecutionSpec(
                step_id="step",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref=capability_ref,
            ),
        ),
    )


@pytest.mark.asyncio
async def test_unexpected_failure_in_one_lane_does_not_cancel_independent_lane():
    broken = _lane(
        lane_id="broken-auth",
        capability_ref="inventory.read",
        required_permission="inventory.read",
    )
    healthy = _lane(lane_id="research", capability_ref="research.read")
    calls: list[str] = []

    async def exploding_authorization(_definition, _step, _capability_ref):
        raise RuntimeError("secret internal detail must not escape")

    async def broken_handler(_definition, _step, _state, _idempotency_key):
        raise AssertionError("authorization failure must happen before handler")

    async def healthy_handler(_definition, _step, _state, _idempotency_key):
        calls.append("research")
        return CapabilityExecutionOutcome(
            succeeded=True,
            evidence_refs=("evidence://research",),
        )

    plan = ParallelMissionPlan(
        objective_ref="objective://isolation",
        tenant_id="YS_TR",
        lanes=(broken, healthy),
        max_parallel_lanes=2,
    )
    result = await execute_parallel_mission_round(
        plan=plan,
        bindings={
            "broken-auth": ParallelLaneBindings(
                gateway=_UnusedGateway(),  # type: ignore[arg-type]
                reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
                capability_handlers={"inventory.read": broken_handler},
                authorization_checker=exploding_authorization,
            ),
            "research": ParallelLaneBindings(
                gateway=_UnusedGateway(),  # type: ignore[arg-type]
                reasoning_evidence_writer=_writer,  # type: ignore[arg-type]
                capability_handlers={"research.read": healthy_handler},
            ),
        },
    )

    by_lane = {item.lane_id: item for item in result.results}
    assert by_lane["broken-auth"].disposition is ParallelLaneDisposition.FAILED
    assert by_lane["broken-auth"].blockers == (
        "parallel_lane_execution_failed:RuntimeError",
    )
    assert "secret internal detail" not in repr(by_lane["broken-auth"])
    assert by_lane["research"].disposition is ParallelLaneDisposition.EXECUTED
    assert by_lane["research"].summary is not None
    assert by_lane["research"].summary.transitions_executed == 1
    assert calls == ["research"]
