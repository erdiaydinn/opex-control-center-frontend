"""Execute multiple Jarvis objectives concurrently under lane-level global leases.

This is composition, not a new mission engine. It uses the canonical lane lease broker
for cross-objective write ownership and delegates every admitted objective back to
`execute_parallel_mission_round()`. Terminal lanes are removed before lease admission.
Unknown/tampered admission references fail closed.

A mutating lease is auto-released only when every side-effect step that was pending at
admission ends SUCCEEDED with evidence. Mission execution already refuses to mark a
successful side effect without authoritative effect verification. Ambiguous outcomes,
runtime failures, partial write progress, or failed side effects keep the lease held for
explicit reconciliation. This module never grants business execution authority.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .global_lane_lease_broker import (
    GlobalLaneLease,
    GlobalLaneLeaseAdmission,
    GlobalLaneLeasePolicy,
    LaneLeaseReleaseDisposition,
    admit_global_lane_leases,
    admitted_plans_from_lane_leases,
    release_global_lane_lease,
)
from .global_objective_arbiter import GlobalObjectiveCandidate
from .mission_runtime import MissionStatus, StepStatus
from .parallel_mission_orchestration import (
    ParallelLaneBindings,
    ParallelLaneDisposition,
    ParallelMissionLane,
    ParallelMissionRound,
    execute_parallel_mission_round,
)

MULTI_OBJECTIVE_SWARM_RUNTIME_CONTRACT = "eay-multi-objective-swarm-runtime-v1"

_TERMINAL_STATUSES = {
    MissionStatus.COMPLETED,
    MissionStatus.FAILED,
    MissionStatus.HALTED,
}


@dataclass(frozen=True)
class MultiObjectiveBindings:
    by_objective: Mapping[str, Mapping[str, ParallelLaneBindings]]


class MultiObjectiveExecutionRound(BaseModel):
    contract: str = MULTI_OBJECTIVE_SWARM_RUNTIME_CONTRACT
    admission: GlobalLaneLeaseAdmission
    objective_rounds: tuple[ParallelMissionRound, ...]
    deferred: dict[str, tuple[str, ...]]
    active_leases_after_round: tuple[GlobalLaneLease, ...]
    released_lease_ids: tuple[str, ...] = ()
    held_lease_ids: tuple[str, ...] = ()
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def composition_is_non_authoritative_and_integral(self) -> "MultiObjectiveExecutionRound":
        if self.execution_authority_granted:
            raise ValueError("multi_objective_runtime_never_grants_execution_authority")
        objective_refs = [item.objective_ref for item in self.objective_rounds]
        if len(objective_refs) != len(set(objective_refs)):
            raise ValueError("multi_objective_runtime_objective_rounds_must_be_unique")
        lease_ids = [item.lease_id for item in self.active_leases_after_round]
        if len(lease_ids) != len(set(lease_ids)):
            raise ValueError("multi_objective_runtime_active_lease_ids_must_be_unique")
        if set(self.released_lease_ids) & set(self.held_lease_ids):
            raise ValueError("multi_objective_runtime_release_hold_overlap")
        return self


def _lane_key(objective_ref: str, lane_id: str) -> str:
    return f"{objective_ref}::{lane_id}"


def _nonterminal_candidates(
    candidates: tuple[GlobalObjectiveCandidate, ...],
) -> tuple[tuple[GlobalObjectiveCandidate, ...], dict[str, tuple[str, ...]]]:
    active: list[GlobalObjectiveCandidate] = []
    deferred: dict[str, tuple[str, ...]] = {}
    for candidate in candidates:
        lanes = tuple(
            lane
            for lane in candidate.plan.lanes
            if lane.checkpoint.status not in _TERMINAL_STATUSES
        )
        for lane in candidate.plan.lanes:
            if lane.checkpoint.status in _TERMINAL_STATUSES:
                deferred[_lane_key(candidate.objective_ref, lane.lane_id)] = (
                    "global_lane_terminal",
                )
        if not lanes:
            continue
        active.append(
            candidate.model_copy(
                update={
                    "plan": candidate.plan.model_copy(
                        update={
                            "lanes": lanes,
                            "max_parallel_lanes": min(
                                candidate.plan.max_parallel_lanes,
                                len(lanes),
                            ),
                        }
                    )
                }
            )
        )
    return tuple(active), deferred


def validate_lane_lease_admission(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    admission: GlobalLaneLeaseAdmission,
) -> None:
    """Fail closed if an admission references an objective/lane not in the supplied plans."""

    known: dict[str, tuple[str, set[str]]] = {
        candidate.objective_ref: (
            candidate.tenant_id,
            {lane.lane_id for lane in candidate.plan.lanes},
        )
        for candidate in candidates
    }
    for selected in admission.selected:
        known_objective = known.get(selected.objective_ref)
        if known_objective is None:
            raise ValueError("multi_objective_admission_unknown_objective")
        tenant_id, lane_ids = known_objective
        if selected.tenant_id != tenant_id:
            raise ValueError("multi_objective_admission_tenant_mismatch")
        if selected.lane_id not in lane_ids:
            raise ValueError("multi_objective_admission_unknown_lane")
    issued_by_id = {item.lease_id: item for item in admission.issued_leases}
    for selected in admission.selected:
        if not selected.mutating:
            continue
        lease = issued_by_id.get(selected.lease_id or "")
        if lease is None:
            raise ValueError("multi_objective_admission_mutation_lease_missing")
        if (
            lease.objective_ref != selected.objective_ref
            or lease.lane_id != selected.lane_id
            or lease.tenant_id != selected.tenant_id
        ):
            raise ValueError("multi_objective_admission_mutation_lease_mismatch")


def _lease_release_from_result(
    *,
    lease: GlobalLaneLease,
    original_lane: ParallelMissionLane,
    result_round: ParallelMissionRound,
    released_at: datetime,
) -> GlobalLaneLease | None:
    result = next(
        (item for item in result_round.results if item.lane_id == original_lane.lane_id),
        None,
    )
    if result is None:
        raise ValueError("multi_objective_runtime_lane_result_missing")

    if result.disposition is ParallelLaneDisposition.DEFERRED:
        evidence = tuple(
            f"parallel-deferred://{original_lane.definition.tenant_id}/"
            f"{original_lane.definition.mission_id}/{original_lane.lane_id}/{blocker}"
            for blocker in result.blockers
        ) or (
            f"parallel-deferred://{original_lane.definition.tenant_id}/"
            f"{original_lane.definition.mission_id}/{original_lane.lane_id}/not-selected",
        )
        return release_global_lane_lease(
            lease=lease,
            released_at=released_at,
            disposition=LaneLeaseReleaseDisposition.NO_SIDE_EFFECT_ATTEMPTED,
            evidence_refs=evidence,
        )

    if result.disposition is not ParallelLaneDisposition.EXECUTED or result.summary is None:
        return None

    before = {item.step_id: item for item in original_lane.checkpoint.steps}
    after = {item.step_id: item for item in result.summary.checkpoint.steps}
    pending_side_effect_steps = tuple(
        step
        for step in original_lane.definition.steps
        if step.side_effect
        and before[step.step_id].status
        in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED}
    )
    if not pending_side_effect_steps:
        raise ValueError("multi_objective_runtime_lease_without_pending_side_effect")

    if any(after[step.step_id].ambiguous_outcome for step in pending_side_effect_steps):
        return None
    if not all(
        after[step.step_id].status is StepStatus.SUCCEEDED
        for step in pending_side_effect_steps
    ):
        return None

    evidence_refs = tuple(
        dict.fromkeys(
            ref
            for step in pending_side_effect_steps
            for ref in after[step.step_id].evidence_refs
            if ref
        )
    )
    if not evidence_refs:
        return None
    return release_global_lane_lease(
        lease=lease,
        released_at=released_at,
        disposition=LaneLeaseReleaseDisposition.VERIFIED_EFFECT,
        evidence_refs=evidence_refs,
    )


async def execute_multi_objective_lane_round(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    bindings: MultiObjectiveBindings,
    active_leases: tuple[GlobalLaneLease, ...],
    now: datetime,
    lease_policy: GlobalLaneLeasePolicy | None = None,
    max_transitions_per_lane: int = 100,
) -> MultiObjectiveExecutionRound:
    """Admit globally, execute per objective concurrently, and reconcile safe leases."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("multi_objective_runtime_now_requires_timezone")
    if not candidates:
        raise ValueError("multi_objective_runtime_requires_candidate")
    objective_refs = [item.objective_ref for item in candidates]
    if len(objective_refs) != len(set(objective_refs)):
        raise ValueError("multi_objective_runtime_objective_refs_must_be_unique")

    active_candidates, terminal_deferred = _nonterminal_candidates(candidates)
    if active_candidates:
        admission = admit_global_lane_leases(
            candidates=active_candidates,
            active_leases=active_leases,
            now=now,
            policy=lease_policy,
        )
        validate_lane_lease_admission(
            candidates=active_candidates,
            admission=admission,
        )
        plans = admitted_plans_from_lane_leases(
            candidates=active_candidates,
            admission=admission,
        )
    else:
        admission = GlobalLaneLeaseAdmission(
            selected=(),
            deferred={},
            issued_leases=(),
        )
        plans = {}

    candidate_by_ref = {item.objective_ref: item for item in active_candidates}
    for objective_ref, plan in plans.items():
        objective_bindings = bindings.by_objective.get(objective_ref)
        if objective_bindings is None:
            raise ValueError("multi_objective_runtime_objective_bindings_missing")
        missing = {lane.lane_id for lane in plan.lanes} - set(objective_bindings)
        if missing:
            raise ValueError(
                "multi_objective_runtime_lane_bindings_missing:"
                + ",".join(sorted(missing))
            )
        if objective_ref not in candidate_by_ref:
            raise ValueError("multi_objective_runtime_projected_unknown_objective")

    async def execute_objective(objective_ref: str) -> ParallelMissionRound:
        plan = plans[objective_ref]
        objective_bindings = bindings.by_objective[objective_ref]
        return await execute_parallel_mission_round(
            plan=plan,
            bindings=objective_bindings,
            max_transitions_per_lane=max_transitions_per_lane,
        )

    objective_rounds = tuple(
        await asyncio.gather(
            *(execute_objective(objective_ref) for objective_ref in sorted(plans))
        )
    ) if plans else ()
    round_by_ref = {item.objective_ref: item for item in objective_rounds}
    original_lane_map = {
        _lane_key(candidate.objective_ref, lane.lane_id): lane
        for candidate in active_candidates
        for lane in candidate.plan.lanes
    }

    released: list[GlobalLaneLease] = []
    held: list[GlobalLaneLease] = []
    for lease in admission.issued_leases:
        objective_round = round_by_ref.get(lease.objective_ref)
        original_lane = original_lane_map.get(_lane_key(lease.objective_ref, lease.lane_id))
        if objective_round is None or original_lane is None:
            raise ValueError("multi_objective_runtime_lease_execution_binding_missing")
        checkpoint_release_time = max(
            (
                item.summary.checkpoint.checkpointed_at
                for item in objective_round.results
                if item.lane_id == lease.lane_id and item.summary is not None
            ),
            default=now,
        )
        resolved = _lease_release_from_result(
            lease=lease,
            original_lane=original_lane,
            result_round=objective_round,
            released_at=max(now, checkpoint_release_time),
        )
        if resolved is None:
            held.append(lease)
        else:
            released.append(resolved)

    active_after = tuple(
        sorted(
            (*active_leases, *released, *held),
            key=lambda item: (item.acquired_at, item.lease_id),
        )
    )
    deferred = dict(terminal_deferred)
    deferred.update(admission.deferred)
    return MultiObjectiveExecutionRound(
        admission=admission,
        objective_rounds=objective_rounds,
        deferred=deferred,
        active_leases_after_round=active_after,
        released_lease_ids=tuple(item.lease_id for item in released),
        held_lease_ids=tuple(item.lease_id for item in held),
    )