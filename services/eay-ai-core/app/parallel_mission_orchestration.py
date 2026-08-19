"""Parallel, resource-safe mission orchestration for Jarvis.

A single durable mission already supports an internal DAG. This layer coordinates
multiple independent missions for one tenant/objective so Jarvis can advance
research, company observation, simulation and execution lanes concurrently.

Parallelism never creates shared authority. Every lane keeps its own live-truth,
authorization, capability and checkpoint boundaries. Lanes that can mutate the
same exclusive resource, or reuse the same side-effect idempotency key, are
serialized rather than raced. Unexpected failure in one selected lane is also
contained to that lane so unrelated work can finish.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from pydantic import BaseModel, Field, model_validator

from .engine_gateway import EngineGateway
from .live_company_readiness import DecisionTruthReceipt
from .mission_execution import (
    AuthorizationChecker,
    CapabilityHandler,
    MissionExecutionSpec,
    MissionExecutionSummary,
    ReasoningEvidenceWriter,
    execute_mission_until_blocked,
)
from .mission_runtime import MissionCheckpoint, MissionDefinition, MissionStatus, StepStatus

PARALLEL_MISSION_ORCHESTRATION_CONTRACT = "eay-parallel-mission-orchestration-v1"


class ParallelLaneDisposition(str, Enum):
    EXECUTED = "executed"
    FAILED = "failed"
    DEFERRED = "deferred"
    TERMINAL = "terminal"


class ParallelMissionLane(BaseModel):
    lane_id: str = Field(min_length=1)
    definition: MissionDefinition
    checkpoint: MissionCheckpoint
    specs: tuple[MissionExecutionSpec, ...]
    priority: int = Field(default=50, ge=0, le=100)
    exclusive_resource_refs: tuple[str, ...] = ()

    @model_validator(mode="after")
    def lane_is_integral(self) -> "ParallelMissionLane":
        if self.definition.mission_id != self.checkpoint.mission_id:
            raise ValueError("parallel_lane_checkpoint_mission_mismatch")
        if self.definition.tenant_id != self.checkpoint.tenant_id:
            raise ValueError("parallel_lane_checkpoint_tenant_mismatch")
        if self.definition.fingerprint() != self.checkpoint.definition_fingerprint:
            raise ValueError("parallel_lane_checkpoint_definition_drift")
        step_ids = {item.step_id for item in self.definition.steps}
        if {item.step_id for item in self.specs} != step_ids or len(self.specs) != len(step_ids):
            raise ValueError("parallel_lane_specs_must_cover_definition_exactly")
        if len(self.exclusive_resource_refs) != len(set(self.exclusive_resource_refs)):
            raise ValueError("parallel_lane_resource_refs_must_be_unique")
        if any(step.side_effect for step in self.definition.steps) and not self.exclusive_resource_refs:
            raise ValueError("parallel_mutating_lane_requires_exclusive_resource_ref")
        return self

    def has_pending_side_effect(self) -> bool:
        states = {item.step_id: item for item in self.checkpoint.steps}
        return any(
            step.side_effect
            and states[step.step_id].status
            in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED}
            for step in self.definition.steps
        )

    def pending_idempotency_keys(self) -> frozenset[str]:
        states = {item.step_id: item for item in self.checkpoint.steps}
        return frozenset(
            step.idempotency_key
            for step in self.definition.steps
            if step.side_effect
            and step.idempotency_key
            and states[step.step_id].status
            in {StepStatus.PENDING, StepStatus.RUNNING, StepStatus.FAILED}
        )


class ParallelMissionPlan(BaseModel):
    contract: str = PARALLEL_MISSION_ORCHESTRATION_CONTRACT
    objective_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    lanes: tuple[ParallelMissionLane, ...] = Field(min_length=1)
    max_parallel_lanes: int = Field(default=4, ge=1, le=16)
    shared_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def plan_is_tenant_bound_and_non_authoritative(self) -> "ParallelMissionPlan":
        if self.shared_execution_authority_granted:
            raise ValueError("parallel_plan_never_grants_shared_execution_authority")
        lane_ids = [item.lane_id for item in self.lanes]
        mission_ids = [item.definition.mission_id for item in self.lanes]
        if len(lane_ids) != len(set(lane_ids)):
            raise ValueError("parallel_lane_ids_must_be_unique")
        if len(mission_ids) != len(set(mission_ids)):
            raise ValueError("parallel_mission_ids_must_be_unique")
        if any(item.definition.tenant_id != self.tenant_id for item in self.lanes):
            raise ValueError("parallel_cross_tenant_lane_forbidden")
        return self


@dataclass(frozen=True)
class ParallelLaneBindings:
    gateway: EngineGateway
    reasoning_evidence_writer: ReasoningEvidenceWriter
    capability_handlers: Mapping[str, CapabilityHandler]
    authorization_checker: AuthorizationChecker | None = None
    decision_truth_receipts: Mapping[str, DecisionTruthReceipt] | None = None


class ParallelLaneResult(BaseModel):
    lane_id: str
    disposition: ParallelLaneDisposition
    summary: MissionExecutionSummary | None = None
    blockers: tuple[str, ...] = ()


class ParallelMissionRound(BaseModel):
    contract: str = PARALLEL_MISSION_ORCHESTRATION_CONTRACT
    objective_ref: str
    tenant_id: str
    selected_lane_ids: tuple[str, ...]
    results: tuple[ParallelLaneResult, ...]
    shared_execution_authority_granted: bool = False

    @model_validator(mode="after")
    def round_is_non_authoritative(self) -> "ParallelMissionRound":
        if self.shared_execution_authority_granted:
            raise ValueError("parallel_round_never_grants_shared_execution_authority")
        if len(self.selected_lane_ids) != len(set(self.selected_lane_ids)):
            raise ValueError("parallel_round_selected_lanes_must_be_unique")
        return self


def _terminal(lane: ParallelMissionLane) -> bool:
    return lane.checkpoint.status in {
        MissionStatus.COMPLETED,
        MissionStatus.FAILED,
        MissionStatus.HALTED,
    }


def parallel_lane_conflict_blockers(
    lane: ParallelMissionLane,
    selected: tuple[ParallelMissionLane, ...],
) -> tuple[str, ...]:
    """Return canonical resource/idempotency blockers for one candidate lane.

    Both the base orchestrator and higher-level schedulers must call this helper
    so safety semantics cannot drift between admission paths.
    """

    lane_resources = set(lane.exclusive_resource_refs)
    lane_keys = set(lane.pending_idempotency_keys())
    blockers: list[str] = []
    for other in selected:
        shared_resources = lane_resources & set(other.exclusive_resource_refs)
        if shared_resources and (
            lane.has_pending_side_effect() or other.has_pending_side_effect()
        ):
            blockers.append("parallel_resource_conflict")
        if lane_keys & set(other.pending_idempotency_keys()):
            blockers.append("parallel_idempotency_conflict")
    return tuple(dict.fromkeys(blockers))


def select_parallel_wave(
    plan: ParallelMissionPlan,
) -> tuple[tuple[str, ...], dict[str, tuple[str, ...]]]:
    """Select one safe concurrent wave and explain every deferral."""

    selected: list[ParallelMissionLane] = []
    deferred: dict[str, tuple[str, ...]] = {}
    ordered = sorted(plan.lanes, key=lambda item: (-item.priority, item.lane_id))

    for lane in ordered:
        if _terminal(lane):
            deferred[lane.lane_id] = ("parallel_lane_terminal",)
            continue
        if len(selected) >= plan.max_parallel_lanes:
            deferred[lane.lane_id] = ("parallel_capacity_deferred",)
            continue

        blockers = parallel_lane_conflict_blockers(lane, tuple(selected))
        if blockers:
            deferred[lane.lane_id] = blockers
            continue
        selected.append(lane)

    return tuple(item.lane_id for item in selected), deferred


async def execute_parallel_mission_round(
    *,
    plan: ParallelMissionPlan,
    bindings: Mapping[str, ParallelLaneBindings],
    max_transitions_per_lane: int = 100,
) -> ParallelMissionRound:
    if max_transitions_per_lane < 1:
        raise ValueError("parallel_lane_transition_budget_must_be_positive")
    selected_ids, deferred = select_parallel_wave(plan)
    lane_map = {item.lane_id: item for item in plan.lanes}
    missing_bindings = set(selected_ids) - set(bindings)
    if missing_bindings:
        raise ValueError(
            "parallel_selected_lane_binding_missing:" + ",".join(sorted(missing_bindings))
        )

    async def run_lane(lane_id: str) -> ParallelLaneResult:
        lane = lane_map[lane_id]
        runtime = bindings[lane_id]
        try:
            summary = await execute_mission_until_blocked(
                definition=lane.definition,
                checkpoint=lane.checkpoint,
                specs=lane.specs,
                gateway=runtime.gateway,
                reasoning_evidence_writer=runtime.reasoning_evidence_writer,
                capability_handlers=runtime.capability_handlers,
                authorization_checker=runtime.authorization_checker,
                decision_truth_receipts=runtime.decision_truth_receipts,
                max_transitions=max_transitions_per_lane,
            )
        except Exception as exc:  # sanitize and contain lane-local runtime failures
            return ParallelLaneResult(
                lane_id=lane_id,
                disposition=ParallelLaneDisposition.FAILED,
                blockers=(f"parallel_lane_execution_failed:{type(exc).__name__}",),
            )
        return ParallelLaneResult(
            lane_id=lane_id,
            disposition=ParallelLaneDisposition.EXECUTED,
            summary=summary,
            blockers=summary.blockers,
        )

    executed = await asyncio.gather(*(run_lane(lane_id) for lane_id in selected_ids))
    executed_map = {item.lane_id: item for item in executed}
    results: list[ParallelLaneResult] = []
    for lane in plan.lanes:
        if lane.lane_id in executed_map:
            results.append(executed_map[lane.lane_id])
            continue
        blockers = deferred.get(lane.lane_id, ("parallel_lane_not_selected",))
        disposition = (
            ParallelLaneDisposition.TERMINAL
            if blockers == ("parallel_lane_terminal",)
            else ParallelLaneDisposition.DEFERRED
        )
        results.append(
            ParallelLaneResult(
                lane_id=lane.lane_id,
                disposition=disposition,
                blockers=blockers,
            )
        )

    return ParallelMissionRound(
        objective_ref=plan.objective_ref,
        tenant_id=plan.tenant_id,
        selected_lane_ids=selected_ids,
        results=tuple(results),
    )
