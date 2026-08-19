"""Evidence-based worker/task routing preferences for Jarvis swarms.

This layer learns no production weights and grants no authority. It aggregates bounded,
source-referenced task outcomes into deterministic routing preferences among workers that
are already eligible under the canonical worker registry. Suspended/draining workers stay
excluded by eligibility; insufficient evidence remains neutral instead of inventing skill.
"""

from __future__ import annotations

from datetime import datetime
from typing import Iterable

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_orchestration import ParallelMissionLane
from .parallel_mission_scheduler import LaneSchedulingClass, ParallelLaneSchedulingProfile
from .swarm_worker_registry import (
    SwarmLaneRequirement,
    SwarmWorkerRegistry,
    eligible_swarm_workers,
    inferred_lane_capability_refs,
)

WORKER_TASK_ROUTING_CONTRACT = "eay-worker-task-routing-v1"


class WorkerTaskOutcomeEvidence(BaseModel):
    contract: str = WORKER_TASK_ROUTING_CONTRACT
    worker_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    scheduling_class: LaneSchedulingClass
    capability_ref: str | None = None
    succeeded: bool
    observed_at: datetime
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def evidence_is_bound_and_non_authoritative(self) -> "WorkerTaskOutcomeEvidence":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("worker_task_outcome_requires_timezone")
        if self.execution_authority_granted:
            raise ValueError("worker_task_outcome_never_grants_execution_authority")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise ValueError("worker_task_outcome_evidence_refs_must_be_unique")
        return self


class WorkerTaskRoutingPolicy(BaseModel):
    contract: str = WORKER_TASK_ROUTING_CONTRACT
    min_samples_for_preference: int = Field(default=5, ge=1, le=100)
    max_evidence_age_seconds: int = Field(default=30 * 86_400, ge=60, le=365 * 86_400)
    min_evidence_confidence: float = Field(default=0.8, ge=0.0, le=1.0)
    prior_successes: float = Field(default=1.0, ge=0.0, le=100.0)
    prior_failures: float = Field(default=1.0, ge=0.0, le=100.0)


class WorkerRoutingScore(BaseModel):
    worker_id: str
    matching_samples: int = Field(ge=0)
    successes: int = Field(ge=0)
    failures: int = Field(ge=0)
    posterior_success_rate: float = Field(ge=0.0, le=1.0)
    preference_eligible: bool


class WorkerTaskRoutingPreference(BaseModel):
    contract: str = WORKER_TASK_ROUTING_CONTRACT
    lane_id: str
    tenant_id: str
    ordered_worker_ids: tuple[str, ...]
    scores: tuple[WorkerRoutingScore, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def preference_is_consistent_and_non_authoritative(self) -> "WorkerTaskRoutingPreference":
        if self.execution_authority_granted:
            raise ValueError("worker_task_routing_never_grants_execution_authority")
        score_ids = [item.worker_id for item in self.scores]
        if len(score_ids) != len(set(score_ids)):
            raise ValueError("worker_task_routing_score_workers_must_be_unique")
        if set(score_ids) != set(self.ordered_worker_ids):
            raise ValueError("worker_task_routing_order_score_mismatch")
        return self


def _matching_outcomes(
    *,
    worker_id: str,
    tenant_id: str,
    profile: ParallelLaneSchedulingProfile,
    lane_capability_refs: frozenset[str],
    outcomes: Iterable[WorkerTaskOutcomeEvidence],
    now: datetime,
    policy: WorkerTaskRoutingPolicy,
) -> tuple[WorkerTaskOutcomeEvidence, ...]:
    selected: list[WorkerTaskOutcomeEvidence] = []
    for item in outcomes:
        if item.worker_id != worker_id or item.tenant_id != tenant_id:
            continue
        if item.scheduling_class is not profile.scheduling_class:
            continue
        if item.confidence < policy.min_evidence_confidence:
            continue
        if item.observed_at > now:
            continue
        if (now - item.observed_at).total_seconds() > policy.max_evidence_age_seconds:
            continue
        if item.capability_ref is not None and item.capability_ref not in lane_capability_refs:
            continue
        selected.append(item)
    return tuple(selected)


def rank_workers_for_lane(
    *,
    registry: SwarmWorkerRegistry,
    lane: ParallelMissionLane,
    profile: ParallelLaneSchedulingProfile,
    requirement: SwarmLaneRequirement,
    outcomes: tuple[WorkerTaskOutcomeEvidence, ...],
    now: datetime,
    policy: WorkerTaskRoutingPolicy | None = None,
) -> WorkerTaskRoutingPreference:
    """Rank only workers already eligible under the canonical registry contract."""

    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("worker_task_routing_now_requires_timezone")
    rules = policy or WorkerTaskRoutingPolicy()
    candidates = eligible_swarm_workers(
        registry=registry,
        lane=lane,
        profile=profile,
        requirement=requirement,
    )
    lane_caps = frozenset(
        set(inferred_lane_capability_refs(lane))
        | set(requirement.required_capability_refs)
    )
    scores: list[WorkerRoutingScore] = []
    for worker in candidates:
        matching = _matching_outcomes(
            worker_id=worker.worker_id,
            tenant_id=registry.tenant_id,
            profile=profile,
            lane_capability_refs=lane_caps,
            outcomes=outcomes,
            now=now,
            policy=rules,
        )
        successes = sum(1 for item in matching if item.succeeded)
        failures = len(matching) - successes
        denominator = (
            successes
            + failures
            + rules.prior_successes
            + rules.prior_failures
        )
        rate = (
            (successes + rules.prior_successes) / denominator
            if denominator > 0
            else 0.5
        )
        eligible = len(matching) >= rules.min_samples_for_preference
        scores.append(
            WorkerRoutingScore(
                worker_id=worker.worker_id,
                matching_samples=len(matching),
                successes=successes,
                failures=failures,
                posterior_success_rate=rate if eligible else 0.5,
                preference_eligible=eligible,
            )
        )

    ordered_scores = tuple(
        sorted(
            scores,
            key=lambda item: (
                0 if item.preference_eligible else 1,
                -item.posterior_success_rate if item.preference_eligible else 0.0,
                -item.matching_samples if item.preference_eligible else 0,
                item.worker_id,
            ),
        )
    )
    return WorkerTaskRoutingPreference(
        lane_id=lane.lane_id,
        tenant_id=registry.tenant_id,
        ordered_worker_ids=tuple(item.worker_id for item in ordered_scores),
        scores=ordered_scores,
    )


def routing_preferences_for_plan(
    *,
    registry: SwarmWorkerRegistry,
    lanes: tuple[ParallelMissionLane, ...],
    profiles: dict[str, ParallelLaneSchedulingProfile],
    requirements: dict[str, SwarmLaneRequirement],
    outcomes: tuple[WorkerTaskOutcomeEvidence, ...],
    now: datetime,
    policy: WorkerTaskRoutingPolicy | None = None,
) -> dict[str, WorkerTaskRoutingPreference]:
    lane_ids = {item.lane_id for item in lanes}
    if set(profiles) != lane_ids or set(requirements) != lane_ids:
        raise ValueError("worker_task_routing_maps_must_cover_lanes_exactly")
    return {
        lane.lane_id: rank_workers_for_lane(
            registry=registry,
            lane=lane,
            profile=profiles[lane.lane_id],
            requirement=requirements[lane.lane_id],
            outcomes=outcomes,
            now=now,
            policy=policy,
        )
        for lane in lanes
    }
