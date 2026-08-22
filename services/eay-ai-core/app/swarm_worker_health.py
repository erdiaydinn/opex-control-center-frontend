"""Evidence-bound worker health, quarantine and admission backpressure for Jarvis.

Worker health is routing evidence, never business authority. Health can only degrade
a worker automatically (READY -> DRAINING -> SUSPENDED). Recovery from a degraded
state is intentionally outside this module so a later success cannot silently
re-enable a quarantined runtime.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .parallel_mission_orchestration import ParallelLaneDisposition
from .swarm_parallel_runtime import SwarmExecutionPolicy, SwarmExecutionRound
from .swarm_worker_registry import (
    SwarmWorkerRegistry,
    SwarmWorkerState,
)

SWARM_WORKER_HEALTH_CONTRACT = "eay-swarm-worker-health-v1"


class WorkerOutcomeKind(str, Enum):
    SUCCESS = "success"
    RUNTIME_FAILURE = "runtime_failure"
    AMBIGUOUS_SIDE_EFFECT = "ambiguous_side_effect"
    TRUTH_BLOCKED = "truth_blocked"
    POLICY_BLOCKED = "policy_blocked"


class WorkerHealthObservation(BaseModel):
    contract: str = SWARM_WORKER_HEALTH_CONTRACT
    worker_id: str = Field(min_length=1)
    lane_id: str = Field(min_length=1)
    observed_at: datetime
    outcome_kind: WorkerOutcomeKind
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    failure_code: str | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def observation_is_non_authoritative(self) -> "WorkerHealthObservation":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("swarm_worker_health_observation_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("swarm_worker_health_never_grants_execution_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("swarm_worker_health_evidence_refs_must_be_unique")
        return self


class WorkerHealthPolicy(BaseModel):
    contract: str = SWARM_WORKER_HEALTH_CONTRACT
    drain_after_consecutive_failures: int = Field(default=2, ge=1, le=20)
    suspend_after_consecutive_failures: int = Field(default=3, ge=1, le=50)
    ambiguous_side_effect_suspends: bool = True

    @model_validator(mode="after")
    def thresholds_are_ordered(self) -> "WorkerHealthPolicy":
        if self.suspend_after_consecutive_failures < self.drain_after_consecutive_failures:
            raise ValueError("swarm_worker_health_suspend_threshold_before_drain")
        return self


class SwarmWorkerHealthRecord(BaseModel):
    contract: str = SWARM_WORKER_HEALTH_CONTRACT
    worker_id: str = Field(min_length=1)
    state: SwarmWorkerState = SwarmWorkerState.READY
    total_observations: int = Field(default=0, ge=0)
    successes: int = Field(default=0, ge=0)
    runtime_failures: int = Field(default=0, ge=0)
    ambiguous_side_effects: int = Field(default=0, ge=0)
    consecutive_failures: int = Field(default=0, ge=0)
    last_observed_at: datetime | None = None
    last_failure_code: str | None = None

    @model_validator(mode="after")
    def timestamp_is_aware(self) -> "SwarmWorkerHealthRecord":
        if self.last_observed_at is not None and (
            self.last_observed_at.tzinfo is None or self.last_observed_at.utcoffset() is None
        ):
            raise ValueError("swarm_worker_health_record_requires_timezone")
        return self


class WorkerHealthUpdate(BaseModel):
    contract: str = SWARM_WORKER_HEALTH_CONTRACT
    registry: SwarmWorkerRegistry
    records: tuple[SwarmWorkerHealthRecord, ...]
    degraded_worker_ids: tuple[str, ...]
    ready_assignment_slots: int = Field(ge=0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def update_is_non_authoritative(self) -> "WorkerHealthUpdate":
        if self.execution_authority_granted:
            raise ValueError("swarm_worker_health_update_never_grants_execution_authority")
        if len(self.degraded_worker_ids) != len(set(self.degraded_worker_ids)):
            raise ValueError("swarm_worker_health_degraded_ids_must_be_unique")
        return self


def worker_health_observations_from_round(
    *,
    execution: SwarmExecutionRound,
    observed_at: datetime,
) -> tuple[WorkerHealthObservation, ...]:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("swarm_worker_health_round_time_requires_timezone")

    assignment_map = {item.lane_id: item.worker_id for item in execution.wave.assignments}
    observations: list[WorkerHealthObservation] = []
    for result in execution.results:
        worker_id = assignment_map[result.lane_id]
        blockers = result.blockers
        summary = result.summary
        ambiguous = bool(
            summary
            and any(step.ambiguous_outcome for step in summary.checkpoint.steps)
        )
        if ambiguous:
            kind = WorkerOutcomeKind.AMBIGUOUS_SIDE_EFFECT
        elif result.disposition is ParallelLaneDisposition.FAILED:
            kind = WorkerOutcomeKind.RUNTIME_FAILURE
        elif summary is not None and summary.checkpoint.status is MissionStatus.FAILED:
            kind = WorkerOutcomeKind.RUNTIME_FAILURE
        elif any(item.startswith("live_company_truth_") for item in blockers):
            kind = WorkerOutcomeKind.TRUTH_BLOCKED
        elif any(
            "authorization" in item or "permission" in item
            for item in blockers
        ):
            kind = WorkerOutcomeKind.POLICY_BLOCKED
        elif any(
            item.startswith("capability_execution_failed:")
            or item.startswith("reasoning_execution_failed:")
            for item in blockers
        ):
            kind = WorkerOutcomeKind.RUNTIME_FAILURE
        else:
            kind = WorkerOutcomeKind.SUCCESS

        failure_code = blockers[0] if blockers and kind in {
            WorkerOutcomeKind.RUNTIME_FAILURE,
            WorkerOutcomeKind.AMBIGUOUS_SIDE_EFFECT,
        } else None
        evidence_refs: list[str] = [
            f"swarm-worker-assignment://{worker_id}/{result.lane_id}"
        ]
        if summary is not None:
            for step in summary.checkpoint.steps:
                evidence_refs.extend(step.evidence_refs)
        observations.append(
            WorkerHealthObservation(
                worker_id=worker_id,
                lane_id=result.lane_id,
                observed_at=observed_at,
                outcome_kind=kind,
                evidence_refs=tuple(dict.fromkeys(evidence_refs)),
                failure_code=failure_code,
            )
        )
    return tuple(observations)


def _state_rank(state: SwarmWorkerState) -> int:
    return {
        SwarmWorkerState.READY: 0,
        SwarmWorkerState.DRAINING: 1,
        SwarmWorkerState.SUSPENDED: 2,
    }[state]


def _more_degraded(
    current: SwarmWorkerState,
    candidate: SwarmWorkerState,
) -> SwarmWorkerState:
    return candidate if _state_rank(candidate) > _state_rank(current) else current


def update_swarm_worker_health(
    *,
    registry: SwarmWorkerRegistry,
    existing_records: Mapping[str, SwarmWorkerHealthRecord],
    observations: tuple[WorkerHealthObservation, ...],
    policy: WorkerHealthPolicy,
) -> WorkerHealthUpdate:
    worker_map = {item.worker_id: item for item in registry.workers}
    unknown_records = set(existing_records) - set(worker_map)
    if unknown_records:
        raise ValueError("swarm_worker_health_record_worker_not_registered")
    if any(item.worker_id not in worker_map for item in observations):
        raise ValueError("swarm_worker_health_observation_worker_not_registered")

    records: dict[str, SwarmWorkerHealthRecord] = {}
    for worker_id, worker in worker_map.items():
        prior = existing_records.get(worker_id)
        if prior is None:
            records[worker_id] = SwarmWorkerHealthRecord(
                worker_id=worker_id,
                state=worker.state,
            )
            continue
        if prior.worker_id != worker_id:
            raise ValueError("swarm_worker_health_record_identity_mismatch")
        records[worker_id] = prior.model_copy(
            update={"state": _more_degraded(worker.state, prior.state)}
        )

    for observation in sorted(observations, key=lambda item: (item.observed_at, item.lane_id)):
        record = records[observation.worker_id]
        update = {
            "total_observations": record.total_observations + 1,
            "last_observed_at": observation.observed_at,
        }
        state = record.state
        if observation.outcome_kind is WorkerOutcomeKind.SUCCESS:
            update["successes"] = record.successes + 1
            update["consecutive_failures"] = 0
        elif observation.outcome_kind is WorkerOutcomeKind.RUNTIME_FAILURE:
            consecutive = record.consecutive_failures + 1
            update["runtime_failures"] = record.runtime_failures + 1
            update["consecutive_failures"] = consecutive
            update["last_failure_code"] = observation.failure_code
            if consecutive >= policy.suspend_after_consecutive_failures:
                state = _more_degraded(state, SwarmWorkerState.SUSPENDED)
            elif consecutive >= policy.drain_after_consecutive_failures:
                state = _more_degraded(state, SwarmWorkerState.DRAINING)
        elif observation.outcome_kind is WorkerOutcomeKind.AMBIGUOUS_SIDE_EFFECT:
            update["ambiguous_side_effects"] = record.ambiguous_side_effects + 1
            update["consecutive_failures"] = record.consecutive_failures + 1
            update["last_failure_code"] = observation.failure_code
            if policy.ambiguous_side_effect_suspends:
                state = _more_degraded(state, SwarmWorkerState.SUSPENDED)
            else:
                state = _more_degraded(state, SwarmWorkerState.DRAINING)
        # Truth/policy blocks are not worker-fault evidence and do not reset or increment failures.
        update["state"] = state
        records[observation.worker_id] = record.model_copy(update=update)

    degraded: list[str] = []
    updated_workers = []
    for worker in registry.workers:
        record = records[worker.worker_id]
        state = _more_degraded(worker.state, record.state)
        if state is not worker.state:
            degraded.append(worker.worker_id)
        updated_workers.append(worker.model_copy(update={"state": state}))

    updated_registry = registry.model_copy(update={"workers": tuple(updated_workers)})
    ready_slots = sum(
        item.max_concurrent_assignments
        for item in updated_registry.workers
        if item.state is SwarmWorkerState.READY
    )
    return WorkerHealthUpdate(
        registry=updated_registry,
        records=tuple(records[item.worker_id] for item in updated_registry.workers),
        degraded_worker_ids=tuple(degraded),
        ready_assignment_slots=ready_slots,
    )


def health_adjusted_swarm_policy(
    *,
    policy: SwarmExecutionPolicy,
    health: WorkerHealthUpdate,
) -> SwarmExecutionPolicy:
    """Cap admission to healthy routing capacity; never increase configured limits."""

    adjusted_active = max(1, min(policy.max_active_workers, max(1, health.ready_assignment_slots)))
    return policy.model_copy(update={"max_active_workers": adjusted_active})
