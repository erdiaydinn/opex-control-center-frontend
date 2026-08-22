from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from app.colony_fanout_fanin_runtime import (
    ColonyEvidenceClaimBinding,
    ColonyEvidenceStance,
    ColonyEvidenceStatus,
    ColonyFanInPolicy,
    ColonyLaneArtifactPublication,
    EvidenceColonyReview,
    ExecutiveSynthesisStatus,
    build_executive_synthesis_candidate,
    publish_colony_round_artifacts,
    verify_colony_evidence,
)
from app.parallel_mission_orchestration import (
    ParallelLaneDisposition,
    ParallelLaneResult,
)
from app.parallel_mission_scheduler import LaneSchedulingClass
from app.swarm_blackboard import (
    SwarmBlackboardEntryKind,
    SwarmBlackboardLedger,
    append_blackboard_entry,
    build_blackboard_entry,
)
from app.swarm_colony_runtime import (
    SwarmColonyAssignment,
    SwarmColonyDescriptor,
    SwarmColonyExecutionRound,
    SwarmColonyKind,
    SwarmColonyTopology,
    SwarmColonyWave,
)
from app.swarm_parallel_runtime import (
    SwarmAssignment,
    SwarmExecutionRound,
    SwarmShard,
    SwarmWave,
)
from app.swarm_worker_registry import (
    SwarmWorkerClass,
    SwarmWorkerDescriptor,
    SwarmWorkerRegistry,
)

NOW = datetime(2026, 8, 19, 12, 0, tzinfo=timezone.utc)
TENANT = "YS_TR"
OBJECTIVE = "objective://fanout-fanin-test"


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
) -> SwarmWorkerDescriptor:
    return SwarmWorkerDescriptor(
        worker_id=worker_id,
        tenant_id=TENANT,
        worker_class=worker_class,
        supported_scheduling_classes=(scheduling_class,),
    )


def _registry() -> SwarmWorkerRegistry:
    return SwarmWorkerRegistry(
        tenant_id=TENANT,
        workers=(
            _worker("worker-data-a", SwarmWorkerClass.COMPANY_READ, LaneSchedulingClass.COMPANY_READ),
            _worker("worker-data-b", SwarmWorkerClass.COMPANY_READ, LaneSchedulingClass.COMPANY_READ),
            _worker("worker-research", SwarmWorkerClass.RESEARCH, LaneSchedulingClass.RESEARCH),
            _worker("worker-simulation", SwarmWorkerClass.SIMULATION, LaneSchedulingClass.SIMULATION),
            _worker("worker-evidence", SwarmWorkerClass.REASONING, LaneSchedulingClass.INTERACTIVE),
            _worker("worker-action", SwarmWorkerClass.EXECUTION, LaneSchedulingClass.EXECUTION),
        ),
    )


def _policy(
    *,
    minimum: int = 3,
    eligible: tuple[str, ...] = (
        "colony://data",
        "colony://research",
        "colony://simulation",
    ),
    required: tuple[str, ...] = ("colony://data", "colony://research"),
) -> ColonyFanInPolicy:
    return ColonyFanInPolicy(
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        evidence_colony_ref="colony://evidence",
        eligible_producer_colony_refs=eligible,
        required_producer_colony_refs=required,
        minimum_independent_producer_colonies=minimum,
        policy_review_evidence_ref="review://policy/fanin-v1",
    )


def _review(*, reviewer: str = "worker-evidence", reviewed_at: datetime | None = None):
    return EvidenceColonyReview(
        review_id="review-1",
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        evidence_colony_ref="colony://evidence",
        reviewer_worker_id=reviewer,
        review_evidence_ref="evidence-review://review-1",
        reviewed_at=reviewed_at or NOW + timedelta(minutes=30),
    )


def _append(
    ledger: SwarmBlackboardLedger,
    *,
    entry_id: str,
    colony_ref: str,
    worker_id: str,
    kind: SwarmBlackboardEntryKind,
    observed_at: datetime = NOW,
    recorded_at: datetime | None = None,
) -> tuple[SwarmBlackboardLedger, object]:
    entry = build_blackboard_entry(
        entry_id=entry_id,
        tenant_id=TENANT,
        objective_ref=OBJECTIVE,
        colony_ref=colony_ref,
        worker_id=worker_id,
        kind=kind,
        subject_ref=f"subject://{entry_id}",
        artifact_ref=f"artifact://{entry_id}",
        evidence_refs=(f"evidence://{entry_id}",),
        observed_at=observed_at,
        recorded_at=recorded_at or observed_at + timedelta(seconds=1),
        confidence=0.9,
    )
    updated = append_blackboard_entry(
        ledger=ledger,
        entry=entry,
        registry=_registry(),
        topology=_topology(),
    )
    return updated, entry


def _claim(entry, proposition: str, stance: ColonyEvidenceStance = ColonyEvidenceStance.SUPPORTS):
    return ColonyEvidenceClaimBinding(
        entry_id=entry.entry_id,
        entry_fingerprint=entry.fingerprint,
        proposition_ref=proposition,
        stance=stance,
    )


def _three_colony_ledger():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, data = _append(
        ledger,
        entry_id="data-1",
        colony_ref="colony://data",
        worker_id="worker-data-a",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
    )
    ledger, research = _append(
        ledger,
        entry_id="research-1",
        colony_ref="colony://research",
        worker_id="worker-research",
        kind=SwarmBlackboardEntryKind.FINDING,
    )
    ledger, simulation = _append(
        ledger,
        entry_id="simulation-1",
        colony_ref="colony://simulation",
        worker_id="worker-simulation",
        kind=SwarmBlackboardEntryKind.SIMULATION,
    )
    return ledger, data, research, simulation


def test_three_independent_colonies_fan_in_to_verified_executive_candidate():
    ledger, data, research, simulation = _three_colony_ledger()
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(),
        review=_review(),
        claims=(
            _claim(data, "proposition://demand-pressure"),
            _claim(research, "proposition://demand-pressure"),
            _claim(simulation, "proposition://demand-pressure"),
        ),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=5),
    )

    assert bundle.status is ColonyEvidenceStatus.VERIFIED
    assert bundle.producer_colony_refs == (
        "colony://data",
        "colony://research",
        "colony://simulation",
    )
    assert bundle.truth_authority_granted is False
    assert bundle.causal_claim_proven is False
    assert bundle.decision_authority_granted is False
    assert bundle.execution_authority_granted is False

    candidate = build_executive_synthesis_candidate(bundle)
    assert candidate.status is ExecutiveSynthesisStatus.READY
    assert candidate.canonical_grounded_guard_required is True
    assert candidate.private_chain_of_thought_exposed is False
    assert candidate.truth_authority_granted is False
    assert candidate.execution_authority_granted is False


def test_many_workers_from_one_colony_do_not_fake_independent_quorum():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, first = _append(
        ledger,
        entry_id="data-a",
        colony_ref="colony://data",
        worker_id="worker-data-a",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
    )
    ledger, second = _append(
        ledger,
        entry_id="data-b",
        colony_ref="colony://data",
        worker_id="worker-data-b",
        kind=SwarmBlackboardEntryKind.FINDING,
    )
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(minimum=2, eligible=("colony://data", "colony://research"), required=()),
        review=_review(),
        claims=(
            _claim(first, "proposition://same-colony"),
            _claim(second, "proposition://same-colony"),
        ),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=5),
    )
    assert bundle.status is ColonyEvidenceStatus.INSUFFICIENT
    assert bundle.producer_colony_refs == ("colony://data",)
    assert "colony_fanin_independent_producer_quorum_missing" in bundle.blockers
    assert build_executive_synthesis_candidate(bundle).status is ExecutiveSynthesisStatus.BLOCKED


def test_independent_support_and_refute_on_same_proposition_blocks_synthesis():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, data = _append(
        ledger,
        entry_id="conflict-data",
        colony_ref="colony://data",
        worker_id="worker-data-a",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
    )
    ledger, research = _append(
        ledger,
        entry_id="conflict-research",
        colony_ref="colony://research",
        worker_id="worker-research",
        kind=SwarmBlackboardEntryKind.FINDING,
    )
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(minimum=2, eligible=("colony://data", "colony://research")),
        review=_review(),
        claims=(
            _claim(data, "proposition://root-cause", ColonyEvidenceStance.SUPPORTS),
            _claim(research, "proposition://root-cause", ColonyEvidenceStance.REFUTES),
        ),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=5),
    )
    assert bundle.status is ColonyEvidenceStatus.CONFLICT
    assert "colony_fanin_independent_claim_conflict" in bundle.blockers
    candidate = build_executive_synthesis_candidate(bundle)
    assert candidate.status is ExecutiveSynthesisStatus.BLOCKED
    assert "executive_synthesis_requires_verified_colony_evidence" in candidate.blockers


def test_late_recorded_evidence_is_invisible_to_historical_fan_in():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, data = _append(
        ledger,
        entry_id="historic-data",
        colony_ref="colony://data",
        worker_id="worker-data-a",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
    )
    ledger, research = _append(
        ledger,
        entry_id="historic-research",
        colony_ref="colony://research",
        worker_id="worker-research",
        kind=SwarmBlackboardEntryKind.FINDING,
        recorded_at=NOW + timedelta(minutes=20),
    )
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(minimum=2, eligible=("colony://data", "colony://research")),
        review=_review(reviewed_at=NOW + timedelta(minutes=30)),
        claims=(
            _claim(data, "proposition://historical"),
            _claim(research, "proposition://historical"),
        ),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=5),
    )
    assert bundle.status is ColonyEvidenceStatus.INSUFFICIENT
    assert bundle.support_entry_refs == ("historic-data",)
    assert "colony_fanin_claim_entry_not_visible" in bundle.blockers


def test_fingerprint_tamper_cannot_enter_fan_in_via_model_copy_bypass():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, data = _append(
        ledger,
        entry_id="tamper-data",
        colony_ref="colony://data",
        worker_id="worker-data-a",
        kind=SwarmBlackboardEntryKind.OBSERVATION,
    )
    tampered = data.model_copy(update={"artifact_ref": "artifact://tampered"})
    bypassed_ledger = ledger.model_copy(update={"entries": (tampered,)})
    with pytest.raises(ValueError, match="swarm_blackboard_entry_fingerprint_mismatch"):
        verify_colony_evidence(
            ledger=bypassed_ledger,
            policy=_policy(minimum=1, eligible=("colony://data",), required=()),
            review=_review(),
            claims=(_claim(data, "proposition://tamper"),),
            registry=_registry(),
            topology=_topology(),
            as_of=NOW + timedelta(minutes=5),
        )


def test_evidence_review_must_be_performed_by_evidence_colony_worker():
    ledger, data, _, _ = _three_colony_ledger()
    with pytest.raises(ValueError, match="colony_fanin_reviewer_not_in_evidence_colony"):
        verify_colony_evidence(
            ledger=ledger,
            policy=_policy(minimum=1, eligible=("colony://data",), required=()),
            review=_review(reviewer="worker-data-a"),
            claims=(_claim(data, "proposition://reviewer"),),
            registry=_registry(),
            topology=_topology(),
            as_of=NOW + timedelta(minutes=5),
        )


def test_action_result_does_not_become_claim_evidence_without_verified_action_bridge():
    ledger = SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE)
    ledger, action = _append(
        ledger,
        entry_id="action-result",
        colony_ref="colony://action",
        worker_id="worker-action",
        kind=SwarmBlackboardEntryKind.ACTION_RESULT,
    )
    bundle = verify_colony_evidence(
        ledger=ledger,
        policy=_policy(
            minimum=1,
            eligible=("colony://action",),
            required=(),
        ),
        review=_review(),
        claims=(_claim(action, "proposition://effect-observed"),),
        registry=_registry(),
        topology=_topology(),
        as_of=NOW + timedelta(minutes=5),
    )
    assert bundle.status is ColonyEvidenceStatus.INSUFFICIENT
    assert "colony_fanin_action_result_requires_verified_action_bridge" in bundle.blockers
    assert bundle.truth_authority_granted is False


def _colony_round(*, disposition: ParallelLaneDisposition = ParallelLaneDisposition.EXECUTED):
    assignment = SwarmAssignment(lane_id="lane-data", worker_id="worker-data-a")
    wave = SwarmWave(
        objective_ref=OBJECTIVE,
        tenant_id=TENANT,
        selected_lane_ids=("lane-data",),
        assignments=(assignment,),
        shards=(SwarmShard(shard_id="swarm-shard-001", assignments=(assignment,)),),
        deferred={},
        total_concurrency_weight=1,
        total_cost_units=1,
    )
    execution = SwarmExecutionRound(
        wave=wave,
        shard_rounds=(),
        results=(
            ParallelLaneResult(
                lane_id="lane-data",
                disposition=disposition,
                blockers=("test_failure",) if disposition is ParallelLaneDisposition.FAILED else (),
            ),
        ),
    )
    colony_wave = SwarmColonyWave(
        wave=wave,
        assignments=(
            SwarmColonyAssignment(
                lane_id="lane-data",
                worker_id="worker-data-a",
                colony_ref="colony://data",
                colony_kind=SwarmColonyKind.DATA,
            ),
        ),
    )
    return SwarmColonyExecutionRound(execution=execution, colony_wave=colony_wave)


def _publication(*, lane_id: str = "lane-data", kind=SwarmBlackboardEntryKind.FINDING):
    return ColonyLaneArtifactPublication(
        lane_id=lane_id,
        entry_id=f"published-{lane_id}",
        kind=kind,
        subject_ref=f"subject://{lane_id}",
        artifact_ref=f"artifact://{lane_id}",
        evidence_refs=(f"evidence://{lane_id}",),
        observed_at=NOW,
        recorded_at=NOW + timedelta(seconds=1),
        confidence=0.8,
    )


def test_fanout_publication_is_bound_to_actual_canonical_assignment():
    ledger = publish_colony_round_artifacts(
        ledger=SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE),
        colony_round=_colony_round(),
        publications=(_publication(),),
        registry=_registry(),
        topology=_topology(),
    )
    assert len(ledger.entries) == 1
    assert ledger.entries[0].worker_id == "worker-data-a"
    assert ledger.entries[0].colony_ref == "colony://data"

    with pytest.raises(ValueError, match="colony_publication_unselected_lane_forbidden"):
        publish_colony_round_artifacts(
            ledger=SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE),
            colony_round=_colony_round(),
            publications=(_publication(lane_id="lane-unselected"),),
            registry=_registry(),
            topology=_topology(),
        )


def test_failed_lane_can_publish_only_blocker_reference():
    with pytest.raises(ValueError, match="colony_publication_failed_lane_requires_blocker"):
        publish_colony_round_artifacts(
            ledger=SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE),
            colony_round=_colony_round(disposition=ParallelLaneDisposition.FAILED),
            publications=(_publication(kind=SwarmBlackboardEntryKind.FINDING),),
            registry=_registry(),
            topology=_topology(),
        )

    ledger = publish_colony_round_artifacts(
        ledger=SwarmBlackboardLedger(tenant_id=TENANT, objective_ref=OBJECTIVE),
        colony_round=_colony_round(disposition=ParallelLaneDisposition.FAILED),
        publications=(_publication(kind=SwarmBlackboardEntryKind.BLOCKER),),
        registry=_registry(),
        topology=_topology(),
    )
    assert ledger.entries[0].kind is SwarmBlackboardEntryKind.BLOCKER


def test_policy_never_allows_action_result_to_be_direct_fanin_claim_type():
    with pytest.raises(ValueError, match="colony_fanin_v1_forbids_action_result_as_claim_evidence"):
        ColonyFanInPolicy(
            tenant_id=TENANT,
            objective_ref=OBJECTIVE,
            evidence_colony_ref="colony://evidence",
            eligible_producer_colony_refs=("colony://action",),
            minimum_independent_producer_colonies=1,
            allowed_entry_kinds=(SwarmBlackboardEntryKind.ACTION_RESULT,),
            policy_review_evidence_ref="review://policy/action-result",
        )
