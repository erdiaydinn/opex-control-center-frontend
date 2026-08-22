"""Conservative cross-objective resource arbitration for Jarvis swarms.

Independent objectives may each be internally safe yet still race one another for the
same store, device, user-scoped mutation or idempotency key. This layer admits whole
objectives concurrently only when their pending mutation claims are globally compatible.
Read-only objectives remain freely parallel. Same-named resources in different tenants
are isolated and do not conflict.

The arbiter is concurrency control only; admission never grants business authority.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .parallel_mission_orchestration import ParallelMissionPlan

GLOBAL_OBJECTIVE_ARBITER_CONTRACT = "eay-global-objective-arbiter-v1"


class GlobalObjectiveCandidate(BaseModel):
    contract: str = GLOBAL_OBJECTIVE_ARBITER_CONTRACT
    objective_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    plan: ParallelMissionPlan
    priority: int = Field(default=50, ge=0, le=100)
    deadline_at: datetime | None = None
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def candidate_is_bound_and_non_authoritative(self) -> "GlobalObjectiveCandidate":
        if self.execution_authority_granted:
            raise ValueError("global_objective_candidate_never_grants_execution_authority")
        if self.plan.objective_ref != self.objective_ref:
            raise ValueError("global_objective_candidate_plan_objective_mismatch")
        if self.plan.tenant_id != self.tenant_id:
            raise ValueError("global_objective_candidate_plan_tenant_mismatch")
        if self.deadline_at is not None and (
            self.deadline_at.tzinfo is None or self.deadline_at.utcoffset() is None
        ):
            raise ValueError("global_objective_deadline_requires_timezone")
        return self


class GlobalObjectiveArbitrationPolicy(BaseModel):
    contract: str = GLOBAL_OBJECTIVE_ARBITER_CONTRACT
    max_concurrent_objectives: int = Field(default=64, ge=1, le=256)


class GlobalObjectiveAdmission(BaseModel):
    contract: str = GLOBAL_OBJECTIVE_ARBITER_CONTRACT
    selected_objective_refs: tuple[str, ...]
    deferred: dict[str, tuple[str, ...]]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def admission_is_non_authoritative(self) -> "GlobalObjectiveAdmission":
        if self.execution_authority_granted:
            raise ValueError("global_objective_admission_never_grants_execution_authority")
        if len(self.selected_objective_refs) != len(set(self.selected_objective_refs)):
            raise ValueError("global_objective_selected_refs_must_be_unique")
        if set(self.selected_objective_refs) & set(self.deferred):
            raise ValueError("global_objective_selected_deferred_overlap")
        return self


def _ranking_key(candidate: GlobalObjectiveCandidate) -> tuple[int, float, int, str]:
    if candidate.deadline_at is None:
        return (1, float("inf"), -candidate.priority, candidate.objective_ref)
    return (0, candidate.deadline_at.timestamp(), -candidate.priority, candidate.objective_ref)


def _pending_claims(candidate: GlobalObjectiveCandidate) -> tuple[frozenset[str], frozenset[str]]:
    resources: set[str] = set()
    idempotency_keys: set[str] = set()
    for lane in candidate.plan.lanes:
        if not lane.has_pending_side_effect():
            continue
        resources.update(lane.exclusive_resource_refs)
        idempotency_keys.update(lane.pending_idempotency_keys())
    return frozenset(resources), frozenset(idempotency_keys)


def _conflict_reasons(
    candidate: GlobalObjectiveCandidate,
    selected: tuple[GlobalObjectiveCandidate, ...],
) -> tuple[str, ...]:
    resources, keys = _pending_claims(candidate)
    blockers: list[str] = []
    for other in selected:
        if other.tenant_id != candidate.tenant_id:
            continue
        other_resources, other_keys = _pending_claims(other)
        if resources & other_resources:
            blockers.append("global_objective_resource_conflict")
        if keys & other_keys:
            blockers.append("global_objective_idempotency_conflict")
    return tuple(dict.fromkeys(blockers))


def arbitrate_global_objectives(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    policy: GlobalObjectiveArbitrationPolicy,
) -> GlobalObjectiveAdmission:
    """Select a deterministic set of objectives whose pending writes cannot race."""

    if not candidates:
        raise ValueError("global_objective_arbitration_requires_candidate")
    refs = [item.objective_ref for item in candidates]
    if len(refs) != len(set(refs)):
        raise ValueError("global_objective_refs_must_be_unique")

    ordered = sorted(candidates, key=_ranking_key)
    selected: list[GlobalObjectiveCandidate] = []
    deferred: dict[str, tuple[str, ...]] = {}
    for candidate in ordered:
        if len(selected) >= policy.max_concurrent_objectives:
            deferred[candidate.objective_ref] = ("global_objective_capacity_deferred",)
            continue
        blockers = _conflict_reasons(candidate, tuple(selected))
        if blockers:
            deferred[candidate.objective_ref] = blockers
            continue
        selected.append(candidate)

    return GlobalObjectiveAdmission(
        selected_objective_refs=tuple(item.objective_ref for item in selected),
        deferred=deferred,
    )
