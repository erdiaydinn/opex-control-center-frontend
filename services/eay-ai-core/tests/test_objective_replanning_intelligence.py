from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint, record_step_result
from app.objective_replanning import (
    LaneReplanDisposition,
    RealityChangeSignal,
    assess_objective_replan_scope,
    compose_replanned_parallel_plan,
)
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan

NOW = datetime(2026, 8, 19, 7, 0, tzinfo=timezone.utc)


def _lane(
    lane_id: str,
    *,
    capability_ref: str,
    side_effect: bool = False,
    resource_ref: str | None = None,
    truth_requirement: str | None = None,
) -> ParallelMissionLane:
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
        capability_ref=capability_ref,
        decision_truth_requirement_id=truth_requirement,
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(spec,),
        exclusive_resource_refs=(() if resource_ref is None else (resource_ref,)),
    )


def _signal(**kwargs) -> RealityChangeSignal:
    return RealityChangeSignal(
        signal_id=kwargs.pop("signal_id", "signal-1"),
        tenant_id=kwargs.pop("tenant_id", "YS_TR"),
        observed_at=NOW,
        evidence_refs=("evidence://reality-change",),
        **kwargs,
    )


def test_truth_invalidation_replans_read_lane_but_preserves_unaffected_lane():
    orders = _lane(
        "orders-read",
        capability_ref="company.orders.read",
        truth_requirement="truth.orders.v2",
    )
    research = _lane("research", capability_ref="research.web")
    plan = ParallelMissionPlan(
        objective_ref="objective://ops",
        tenant_id="YS_TR",
        lanes=(orders, research),
    )
    scope = assess_objective_replan_scope(
        plan=plan,
        signals=(
            _signal(invalidated_truth_requirement_ids=("truth.orders.v2",)),
        ),
    )
    by_lane = {item.lane_id: item for item in scope.assessments}
    assert by_lane["orders-read"].disposition is LaneReplanDisposition.REPLAN_SAFE
    assert by_lane["research"].disposition is LaneReplanDisposition.PRESERVE
    assert scope.auto_replan_lane_ids == ("orders-read",)
    assert scope.preserved_lane_ids == ("research",)
    assert scope.review_lane_ids == ()


def test_attempted_side_effect_can_never_be_silently_replanned():
    lane = _lane(
        "inventory-write",
        capability_ref="inventory.adjust",
        side_effect=True,
        resource_ref="store://fulya/inventory",
    )
    checkpoint = record_step_result(
        lane.definition,
        lane.checkpoint,
        step_id="step-1",
        succeeded=True,
        evidence_refs=("evidence://verified-write",),
        now=NOW,
    )
    lane = lane.model_copy(update={"checkpoint": checkpoint})
    plan = ParallelMissionPlan(
        objective_ref="objective://inventory",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    scope = assess_objective_replan_scope(
        plan=plan,
        signals=(
            _signal(affected_resource_refs=("store://fulya/inventory",)),
        ),
    )
    assert scope.review_lane_ids == ("inventory-write",)
    assert scope.assessments[0].disposition is LaneReplanDisposition.HOLD_FOR_REVIEW
    assert "objective_replan_attempted_side_effect_requires_review" in scope.assessments[0].reason_codes

    with pytest.raises(ValueError, match="objective_replan_review_required"):
        compose_replanned_parallel_plan(
            original=plan,
            scope=scope,
            replacements={},
        )


def test_safe_replacement_preserves_unaffected_checkpoint_exactly():
    changed = _lane(
        "orders-read",
        capability_ref="company.orders.read",
        truth_requirement="truth.orders.v2",
    )
    untouched = _lane("research", capability_ref="research.web")
    untouched_checkpoint = record_step_result(
        untouched.definition,
        untouched.checkpoint,
        step_id="step-1",
        succeeded=True,
        evidence_refs=("evidence://research",),
        now=NOW,
    )
    untouched = untouched.model_copy(update={"checkpoint": untouched_checkpoint})
    original = ParallelMissionPlan(
        objective_ref="objective://ops",
        tenant_id="YS_TR",
        lanes=(changed, untouched),
    )
    scope = assess_objective_replan_scope(
        plan=original,
        signals=(
            _signal(invalidated_truth_requirement_ids=("truth.orders.v2",)),
        ),
    )
    replacement = _lane(
        "orders-read",
        capability_ref="company.orders.read.v3",
        truth_requirement="truth.orders.v3",
    )
    replanned = compose_replanned_parallel_plan(
        original=original,
        scope=scope,
        replacements={"orders-read": replacement},
    )
    by_lane = {item.lane_id: item for item in replanned.lanes}
    assert by_lane["orders-read"].definition.fingerprint() == replacement.definition.fingerprint()
    assert by_lane["research"].checkpoint == untouched_checkpoint


def test_cross_tenant_reality_signal_is_rejected():
    lane = _lane("research", capability_ref="research.web")
    plan = ParallelMissionPlan(
        objective_ref="objective://safe",
        tenant_id="YS_TR",
        lanes=(lane,),
    )
    with pytest.raises(ValueError, match="objective_replan_cross_tenant_signal_forbidden"):
        assess_objective_replan_scope(
            plan=plan,
            signals=(
                _signal(
                    tenant_id="DE_DE",
                    changed_capability_refs=("research.web",),
                ),
            ),
        )
