from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.objective_decomposition_admission import (
    ObjectiveDecompositionPolicy,
    ObjectiveDecompositionProposal,
    ProposedObjectiveLane,
    admit_objective_decomposition,
)
from app.parallel_mission_orchestration import ParallelMissionLane
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_worker_registry import SwarmLaneRequirement

NOW = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)


def _lane(lane_id: str, *, side_effect: bool = False) -> ParallelMissionLane:
    step = MissionStep(
        step_id="step-1",
        description=f"advance {lane_id}",
        side_effect=side_effect,
        idempotency_key=(f"idem-{lane_id}-0000000001" if side_effect else None),
        effect_verifier_ref=("effect://authoritative" if side_effect else None),
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"objective {lane_id}",
        tenant_id="YS_TR",
        steps=(step,),
    )
    spec = MissionExecutionSpec(
        step_id="step-1",
        kind=MissionExecutionKind.CAPABILITY,
        capability_ref="capability://write" if side_effect else "capability://read",
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        exclusive_resource_refs=(
            (f"resource://{lane_id}",) if side_effect else ()
        ),
    )


def _proposal_lane(
    lane: ParallelMissionLane,
    *,
    scheduling_class: LaneSchedulingClass | None = None,
    cost: int = 1,
    weight: int = 1,
) -> ProposedObjectiveLane:
    write = lane.has_pending_side_effect()
    return ProposedObjectiveLane(
        lane=lane,
        profile=ParallelLaneSchedulingProfile(
            lane_id=lane.lane_id,
            scheduling_class=scheduling_class or (
                LaneSchedulingClass.EXECUTION if write else LaneSchedulingClass.RESEARCH
            ),
            estimated_cost_units=cost,
            concurrency_weight=weight,
            shedable=not write,
            preemptible=not write,
        ),
        requirement=SwarmLaneRequirement(lane_id=lane.lane_id),
        evidence_refs=(f"evidence://decomposition/{lane.lane_id}",),
    )


def _proposal(items: tuple[ProposedObjectiveLane, ...]) -> ObjectiveDecompositionProposal:
    return ObjectiveDecompositionProposal(
        objective_ref="objective://fanout",
        tenant_id="YS_TR",
        lanes=items,
        decomposition_evidence_refs=("evidence://planner/root",),
        max_parallel_lanes=16,
    )


def test_admission_accepts_256_evidence_bound_read_lanes_when_policy_allows():
    items = tuple(_proposal_lane(_lane(f"lane-{index:03d}")) for index in range(256))
    admitted = admit_objective_decomposition(
        proposal=_proposal(items),
        policy=ObjectiveDecompositionPolicy(
            max_lanes=256,
            max_total_cost_units=256,
            max_total_concurrency_weight=256,
        ),
    )
    assert len(admitted.plan.lanes) == 256
    assert admitted.plan.max_parallel_lanes == 16
    assert admitted.total_cost_units == 256
    assert admitted.total_concurrency_weight == 256
    assert admitted.mutating_lane_count == 0
    assert admitted.execution_authority_granted is False


def test_default_fanout_limit_rejects_129_lane_model_proposal():
    items = tuple(_proposal_lane(_lane(f"lane-{index:03d}")) for index in range(129))
    with pytest.raises(ValueError, match="objective_decomposition_fanout_limit_exceeded"):
        admit_objective_decomposition(
            proposal=_proposal(items),
            policy=ObjectiveDecompositionPolicy(),
        )


def test_mutating_lane_cannot_hide_inside_research_scheduling_class():
    lane = _lane("inventory-write", side_effect=True)
    proposed = _proposal_lane(lane, scheduling_class=LaneSchedulingClass.RESEARCH)
    with pytest.raises(ValueError, match="mutation_requires_execution_class"):
        admit_objective_decomposition(
            proposal=_proposal((proposed,)),
            policy=ObjectiveDecompositionPolicy(),
        )


def test_decomposition_rejects_nonfresh_checkpoint_instead_of_replanning_history():
    lane = _lane("read")
    advanced = record_step_result(
        lane.definition,
        lane.checkpoint,
        step_id="step-1",
        succeeded=True,
        evidence_refs=("evidence://completed",),
        now=NOW,
    )
    lane = lane.model_copy(update={"checkpoint": advanced})
    with pytest.raises(ValueError, match="objective_decomposition_requires_fresh_checkpoint"):
        admit_objective_decomposition(
            proposal=_proposal((_proposal_lane(lane),)),
            policy=ObjectiveDecompositionPolicy(),
        )


def test_aggregate_cost_budget_is_enforced_before_swarm_admission():
    first = _proposal_lane(_lane("first"), cost=10)
    second = _proposal_lane(_lane("second"), cost=10)
    with pytest.raises(ValueError, match="objective_decomposition_cost_budget_exceeded"):
        admit_objective_decomposition(
            proposal=_proposal((first, second)),
            policy=ObjectiveDecompositionPolicy(max_total_cost_units=15),
        )
