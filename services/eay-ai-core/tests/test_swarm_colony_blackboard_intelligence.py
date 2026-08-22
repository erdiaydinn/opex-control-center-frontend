from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.mission_execution import MissionExecutionKind, MissionExecutionSpec
from app.mission_runtime import MissionDefinition, MissionStep, new_checkpoint
from app.parallel_mission_orchestration import ParallelMissionLane, ParallelMissionPlan
from app.parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from app.swarm_blackboard import (
    SwarmBlackboardEntryKind,
    SwarmBlackboardLedger,
    append_blackboard_entry,
    build_blackboard_entry,
    visible_blackboard_entries,
)
from app.swarm_colony_runtime import (
    SwarmColonyDescriptor,
    SwarmColonyKind,
    SwarmColonyLanePolicy,
    SwarmColonyTopology,
    compile_colony_requirements,
    schedule_colony_swarm_wave,
)
from app.swarm_parallel_runtime import SwarmExecutionPolicy
from app.swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
)

NOW = datetime(2026, 8, 19, 10, 30, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECTIVE = "objective://colony-test"


def _lane(
    lane_id: str,
    capability_ref: str,
    *,
    side_effect: bool = False,
) -> ParallelMissionLane:
    step = MissionStep(
        step_id="work",
        description=f"{lane_id} specialist work",
        side_effect=side_effect,
        idempotency_key=f"idem-{lane_id}" if side_effect else None,
        effect_verifier_ref=f"verifier://{lane_id}" if side_effect else None,
    )
    definition = MissionDefinition(
        mission_id=f"mission-{lane_id}",
        objective=f"run {lane_id}",
        tenant_id=TENANT,
        steps=(step,),
    )
    return ParallelMissionLane(
        lane_id=lane_id,
        definition=definition,
        checkpoint=new_checkpoint(definition, now=NOW),
        specs=(
            MissionExecutionSpec(
                step_id="work",
                kind=MissionExecutionKind.CAPABILITY,
                capability_ref=capability_ref,
            ),
        ),
        exclusive_resource_refs=(f"resource://{lane_id}",) if side_effect else (),
    )


def _topology() -> SwarmColonyTopology:
    return SwarmColonyTopology(
        tenant_id=TENANT,
        colonies=(
            SwarmColonyDescriptor(
                colony_ref="colony://data",
                tenant_id=TENANT,
                kind=SwarmColonyKind.DATA,
                worker_classes=(SwarmWorkerClass.COMPANY_READ,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://ops",
                tenant_id=TENANT,
                kind=SwarmColonyKind.OPERATIONS,
                worker_classes=(SwarmWorkerClass.GENERAL,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://research",
                tenant_id=TENANT,
                kind=SwarmColonyKind.RESEARCH,
                worker_classes=(SwarmWorkerClass.RESEARCH,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://simulation",
                tenant_id=TENANT,
                kind=SwarmColonyKind.SIMULATION,
                worker_classes=(SwarmWorkerClass.SIMULATION,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://evidence",
                tenant_id=TENANT,
                kind=SwarmColonyKind.EVIDENCE,
                worker_classes=(SwarmWorkerClass.REASONING,),
            ),
            SwarmColonyDescriptor(
                colony_ref="colony://action",
                tenant_id=TENANT,
                kind=SwarmColonyKind.ACTION,
                worker_classes=(SwarmWorkerClass.EXECUTION,),
                may_handle_side_effect_lanes=True,
            ),
        ),
    )


def _worker(
    worker_id: str,
    worker_class: SwarmWorkerClass,
    scheduling_class: LaneSchedulingClass,
    capability_ref: str,
) -> SwarmWorkerDescriptor:
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id=TENANT,
        worker_class=worker_class,
        supported_scheduling_classes=(scheduling_class,),
        capability_refs=(capability_ref,),
    )


def _fixture():
    lanes = (
        _lane("data", "company.read"),
        _lane("ops", "ops.analyze"),
        _lane("research", "research.web"),
        _lane("simulation", "digital-twin.run"),
        _lane("evidence", "evidence.verify"),
        _lane("action", "inventory.adjust", side_effect=True),
    )
    profiles = {
        "data": ParallelLaneSchedulingProfile(
            lane_id="data", scheduling_class=LaneSchedulingClass.COMPANY_READ
        ),
        "ops": ParallelLaneSchedulingProfile(
            lane_id="ops", scheduling_class=LaneSchedulingClass.INTERACTIVE
        ),
        "research": ParallelLaneSchedulingProfile(
            lane_id="research", scheduling_class=LaneSchedulingClass.RESEARCH
        ),
        "simulation": ParallelLaneSchedulingProfile(
            lane_id="simulation", scheduling_class=LaneSchedulingClass.SIMULATION
        ),
        "evidence": ParallelLaneSchedulingProfile(
            lane_id="evidence", scheduling_class=LaneSchedulingClass.INTERACTIVE
        ),
        "action": ParallelLaneSchedulingProfile(
            lane_id="action",
            scheduling_class=LaneSchedulingClass.EXECUTION,
            shedable=False,
            preemptible=False,
        ),
    }
    requirements = {
        lane.lane_id: SwarmLaneRequirement(
            lane_id=lane.lane_id,
            required_capability_refs=(lane.specs[0].capability_ref,),
        )
        for lane in lanes
    }
    lane_policies = {
        "data": SwarmColonyLanePolicy(
            lane_id="data", allowed_colony_refs=("colony://data",)
        ),
        "ops": SwarmColonyLanePolicy(
            lane_id="ops", allowed_colony_refs=("colony://ops",)
        ),
        "research": SwarmColonyLanePolicy(
            lane_id="research", allowed_colony_refs=("colony://research",)
        ),
        "simulation": SwarmColonyLanePolicy(
            lane_id="simulation", allowed_colony_refs=("colony://simulation",)
        ),
        "evidence": SwarmColonyLanePolicy(
            lane_id="evidence", allowed_colony_refs=("colony://evidence",)
        ),
        "action": SwarmColonyLanePolicy(
            lane_id="action",
            allowed_colony_refs=("colony://data", "colony://action"),
        ),
    }
    registry = SwarmWorkerRegistry(
        tenant_id=TENANT,
        workers=(
            _worker(
                "worker-data",
                SwarmWorkerClass.COMPANY_READ,
                LaneSchedulingClass.COMPANY_READ,
                "company.read",
            ),
            _worker(
                "worker-ops",
                SwarmWorkerClass.GENERAL,
                LaneSchedulingClass.INTERACTIVE,
                "ops.analyze",
            ),
            _worker(
                "worker-research",
                SwarmWorkerClass.RESEARCH,
                LaneSchedulingClass.RESEARCH,
                "research.web",
            ),
            _worker(
                "worker-simulation",
                SwarmWorkerClass.SIMULATION,
                LaneSchedulingClass.SIMULATION,
                "digital-twin.run",
            ),
            _worker(
                "worker-evidence",
                SwarmWorkerClass.REASONING,
                LaneSchedulingClass.INTERACTIVE,
                "evidence.verify",
            ),
            _worker(
                "worker-action",
                SwarmWorkerClass.EXECUTION,
                LaneSchedulingClass.EXECUTION,
                "inventory.adjust",
            ),
        ),
    )
    return (
        ParallelMissionPlan(
            objective_ref=OBJECTIVE,
            tenant_id=TENANT,
            lanes=lanes,
            max_parallel_lanes=8,
        ),
        profiles,
        requirements,
        lane_policies,
        registry,
    )


def test_specialist_colonies_route_six_independent_lanes_in_one_canonical_wave():
    plan, profiles, requirements, lane_policies, registry = _fixture()
    wave = schedule_colony_swarm_wave(
        plan=plan,
        profiles=profiles,
        base_requirements=requirements,
        lane_policies=lane_policies,
        topology=_topology(),
        registry=registry,
        policy=SwarmExecutionPolicy(max_active_workers=16, shard_size=4),
        now=NOW,
    )

    assert set(wave.wave.selected_lane_ids) == {
        "action",
        "data",
        "evidence",
        "ops",
        "research",
        "simulation",
    }
    by_lane = {item.lane_id: item for item in wave.assignments}
    assert by_lane["data"].colony_kind is SwarmColonyKind.DATA
    assert by_lane["ops"].colony_kind is SwarmColonyKind.OPERATIONS
    assert by_lane["research"].colony_kind is SwarmColonyKind.RESEARCH
    assert by_lane["simulation"].colony_kind is SwarmColonyKind.SIMULATION
    assert by_lane["evidence"].colony_kind is SwarmColonyKind.EVIDENCE
    assert by_lane["action"].colony_kind is SwarmColonyKind.ACTION
    assert wave.execution_authority_granted is False


def test_side_effect_lane_cannot_be_owned_by_data_colony_even_if_policy_mentions_it():
    plan, _, requirements, lane_policies, _ = _fixture()
    compiled = compile_colony_requirements(
        plan=plan,
        base_requirements=requirements,
        lane_policies=lane_policies,
        topology=_topology(),
    )
    assert compiled.requirements["action"].required_worker_classes == (
        SwarmWorkerClass.EXECUTION,
    )


def test_side_effect_lane_without_action_colony_fails_closed():
    plan, _, requirements, lane_policies, _ = _fixture()
    policies = dict(lane_policies)
    policies["action"] = SwarmColonyLanePolicy(
        lane_id="action", allowed_colony_refs=("colony://data",)
    )
    with pytest.raises(ValueError, match="swarm_colony_side_effect_requires_action_colony"):
        compile_colony_requirements(
            plan=plan,
            base_requirements=requirements,
            lane_policies=policies,
            topology=_topology(),
        )


def test_blackboard_accepts_cross_colony_evidence_refs_without_promoting_truth():
    _, _, _, _, registry = _fixture()
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    data_entry = build_blackboard_entry(
        entry_id="entry-data-1",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://data",
        worker_id="worker-data",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
        subject_ref="company-source://workforce/picker-shift-order-lookup/v1",
        artifact_ref="artifact://secure/company-read/receipt-1",
        evidence_refs=("bigquery-execution://abc123",),
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        confidence=1.0,
    )
    ledger = append_blackboard_entry(
        ledger=ledger,
        entry=data_entry,
        registry=registry,
        topology=_topology(),
    )
    evidence_entry = build_blackboard_entry(
        entry_id="entry-evidence-1",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://evidence",
        worker_id="worker-evidence",
        kind=SwarmBlackboardEntryKind.FINDING,
        subject_ref="claim://picker-attribution/checked",
        artifact_ref="artifact://secure/evidence/finding-1",
        evidence_refs=(f"blackboard-entry://{data_entry.fingerprint}",),
        observed_at=NOW + timedelta(seconds=2),
        recorded_at=NOW + timedelta(seconds=3),
        confidence=0.95,
    )
    ledger = append_blackboard_entry(
        ledger=ledger,
        entry=evidence_entry,
        registry=registry,
        topology=_topology(),
    )

    visible = visible_blackboard_entries(
        ledger=ledger,
        as_of=NOW + timedelta(seconds=5),
    )
    assert [item.entry_id for item in visible] == ["entry-data-1", "entry-evidence-1"]
    assert all(item.truth_authority_granted is False for item in visible)
    assert all(item.execution_authority_granted is False for item in visible)


def test_blackboard_historical_replay_cannot_see_late_recorded_evidence():
    _, _, _, _, registry = _fixture()
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    entry = build_blackboard_entry(
        entry_id="entry-late",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://research",
        worker_id="worker-research",
        kind=SwarmBlackboardEntryKind.FINDING,
        subject_ref="research://event/context",
        artifact_ref="artifact://secure/research/late",
        evidence_refs=("source://verified/research-1",),
        observed_at=NOW,
        recorded_at=NOW + timedelta(minutes=10),
        confidence=0.9,
    )
    ledger = append_blackboard_entry(
        ledger=ledger,
        entry=entry,
        registry=registry,
        topology=_topology(),
    )
    assert visible_blackboard_entries(
        ledger=ledger,
        as_of=NOW + timedelta(minutes=5),
    ) == ()
    assert len(
        visible_blackboard_entries(
            ledger=ledger,
            as_of=NOW + timedelta(minutes=11),
        )
    ) == 1


def test_blackboard_rejects_tampering_wrong_colony_and_secret_bearing_refs():
    _, _, _, _, registry = _fixture()
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    entry = build_blackboard_entry(
        entry_id="entry-safe",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://data",
        worker_id="worker-data",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
        subject_ref="company://safe",
        artifact_ref="artifact://secure/safe",
        evidence_refs=("evidence://safe",),
        observed_at=NOW,
        recorded_at=NOW,
        confidence=1.0,
    )

    with pytest.raises(ValueError, match="swarm_blackboard_entry_fingerprint_mismatch"):
        append_blackboard_entry(
            ledger=ledger,
            entry=entry.model_copy(update={"confidence": 0.2}),
            registry=registry,
            topology=_topology(),
        )

    wrong_colony = build_blackboard_entry(
        entry_id="entry-wrong-colony",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref="colony://research",
        worker_id="worker-data",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
        subject_ref="company://safe",
        artifact_ref="artifact://secure/safe-2",
        evidence_refs=("evidence://safe-2",),
        observed_at=NOW,
        recorded_at=NOW,
        confidence=1.0,
    )
    with pytest.raises(ValueError, match="swarm_blackboard_producer_colony_mismatch"):
        append_blackboard_entry(
            ledger=ledger,
            entry=wrong_colony,
            registry=registry,
            topology=_topology(),
        )

    with pytest.raises(ValueError, match="swarm_blackboard_secret_bearing_reference_forbidden"):
        build_blackboard_entry(
            entry_id="entry-secret",
            tenant_id=TENANT,
            objective_ref=OBJECTIVE,
            colony_ref="colony://data",
            worker_id="worker-data",
            kind=SwarmBlackboardEntryKind.OBSERVATION,
            subject_ref="company://safe",
            artifact_ref="https://internal/report?token=secret",
            evidence_refs=("evidence://safe",),
            observed_at=NOW,
            recorded_at=NOW,
            confidence=1.0,
        )
