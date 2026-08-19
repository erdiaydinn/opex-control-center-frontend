"""Compose reviewed timeline changes into the governed multi-objective swarm runtime.

The Real-World Timeline never mutates a mission directly. Exact reviewed event rules
first produce ``RealityChangeSignal`` objects, the existing objective replanner then
classifies every affected lane, and only fresh replacements for ``REPLAN_SAFE`` lanes
may enter execution. Any attempted/ambiguous side effect holds the whole objective for
review; missing replacement work also holds instead of silently executing a stale plan.

This module is composition only. It delegates actual execution and lease/effect safety
to ``execute_multi_objective_lane_round`` and never grants execution authority itself.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping

from pydantic import BaseModel, model_validator

from .global_lane_lease_broker import GlobalLaneLease, GlobalLaneLeasePolicy
from .global_objective_arbiter import GlobalObjectiveCandidate
from .multi_objective_swarm_runtime import (
    MultiObjectiveBindings,
    MultiObjectiveExecutionRound,
    execute_multi_objective_lane_round,
)
from .objective_replanning import (
    ObjectiveReplanScope,
    assess_objective_replan_scope,
    compose_replanned_parallel_plan,
)
from .parallel_mission_orchestration import ParallelMissionLane
from .real_world_timeline import RealWorldTimelineEvent
from .timeline_replanning_adapter import TimelineReplanRule, timeline_events_to_replan_signals

TIMELINE_SWARM_REPLANNING_CONTRACT = "eay-timeline-swarm-replanning-v1"


class TimelineSwarmReplanDisposition(str, Enum):
    UNAFFECTED = "unaffected"
    REPLANNED = "replanned"
    REPLACEMENT_REQUIRED = "replacement_required"
    HOLD_FOR_REVIEW = "hold_for_review"


class TimelineObjectiveReplanDecision(BaseModel):
    contract: str = TIMELINE_SWARM_REPLANNING_CONTRACT
    objective_ref: str
    tenant_id: str
    disposition: TimelineSwarmReplanDisposition
    signal_ids: tuple[str, ...] = ()
    auto_replan_lane_ids: tuple[str, ...] = ()
    review_lane_ids: tuple[str, ...] = ()
    reason_codes: tuple[str, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def decision_is_non_authoritative(self) -> "TimelineObjectiveReplanDecision":
        if self.execution_authority_granted:
            raise ValueError("timeline_swarm_replan_never_grants_execution_authority")
        if self.disposition is TimelineSwarmReplanDisposition.REPLANNED and not self.auto_replan_lane_ids:
            raise ValueError("timeline_swarm_replanned_requires_safe_lane")
        if self.disposition is TimelineSwarmReplanDisposition.HOLD_FOR_REVIEW and not self.review_lane_ids:
            raise ValueError("timeline_swarm_review_hold_requires_review_lane")
        return self


class TimelineSwarmPreparation(BaseModel):
    contract: str = TIMELINE_SWARM_REPLANNING_CONTRACT
    runnable_candidates: tuple[GlobalObjectiveCandidate, ...]
    decisions: tuple[TimelineObjectiveReplanDecision, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def preparation_is_integral(self) -> "TimelineSwarmPreparation":
        if self.execution_authority_granted:
            raise ValueError("timeline_swarm_preparation_never_grants_execution_authority")
        decision_refs = [item.objective_ref for item in self.decisions]
        if len(decision_refs) != len(set(decision_refs)):
            raise ValueError("timeline_swarm_decision_objectives_must_be_unique")
        runnable_refs = [item.objective_ref for item in self.runnable_candidates]
        if len(runnable_refs) != len(set(runnable_refs)):
            raise ValueError("timeline_swarm_runnable_objectives_must_be_unique")
        return self


class TimelineSwarmExecutionRound(BaseModel):
    contract: str = TIMELINE_SWARM_REPLANNING_CONTRACT
    preparation: TimelineSwarmPreparation
    execution: MultiObjectiveExecutionRound | None = None
    active_leases_after_round: tuple[GlobalLaneLease, ...]
    execution_authority_granted: bool = False

    @model_validator(mode="after")
    def execution_composition_is_non_authoritative(self) -> "TimelineSwarmExecutionRound":
        if self.execution_authority_granted:
            raise ValueError("timeline_swarm_execution_never_grants_execution_authority")
        if self.execution is None:
            if self.preparation.runnable_candidates:
                raise ValueError("timeline_swarm_runnable_candidates_missing_execution")
        elif self.execution.active_leases_after_round != self.active_leases_after_round:
            raise ValueError("timeline_swarm_active_lease_projection_mismatch")
        return self


def _events_by_tenant(
    events: tuple[RealWorldTimelineEvent, ...],
) -> dict[str, tuple[RealWorldTimelineEvent, ...]]:
    grouped: dict[str, list[RealWorldTimelineEvent]] = {}
    for event in events:
        validated = RealWorldTimelineEvent.model_validate(event.model_dump(mode="json"))
        grouped.setdefault(validated.tenant_id, []).append(validated)
    return {tenant: tuple(items) for tenant, items in grouped.items()}


def _decision_from_scope(
    *,
    candidate: GlobalObjectiveCandidate,
    scope: ObjectiveReplanScope,
    signal_ids: tuple[str, ...],
    disposition: TimelineSwarmReplanDisposition,
    reason_codes: tuple[str, ...],
) -> TimelineObjectiveReplanDecision:
    return TimelineObjectiveReplanDecision(
        objective_ref=candidate.objective_ref,
        tenant_id=candidate.tenant_id,
        disposition=disposition,
        signal_ids=signal_ids,
        auto_replan_lane_ids=scope.auto_replan_lane_ids,
        review_lane_ids=scope.review_lane_ids,
        reason_codes=reason_codes,
    )


def prepare_timeline_replanned_candidates(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    events: tuple[RealWorldTimelineEvent, ...],
    rules: tuple[TimelineReplanRule, ...],
    replacements_by_objective: Mapping[str, Mapping[str, ParallelMissionLane]],
    now,
) -> TimelineSwarmPreparation:
    """Prepare only unaffected or safely-replanned objectives for execution."""

    if not candidates:
        raise ValueError("timeline_swarm_replanning_requires_candidate")
    refs = [item.objective_ref for item in candidates]
    if len(refs) != len(set(refs)):
        raise ValueError("timeline_swarm_candidate_objectives_must_be_unique")
    unknown_replacements = set(replacements_by_objective) - set(refs)
    if unknown_replacements:
        raise ValueError(
            "timeline_swarm_replacements_reference_unknown_objective:"
            + ",".join(sorted(unknown_replacements))
        )

    grouped_events = _events_by_tenant(events)
    runnable: list[GlobalObjectiveCandidate] = []
    decisions: list[TimelineObjectiveReplanDecision] = []

    for candidate in candidates:
        tenant_events = grouped_events.get(candidate.tenant_id, ())
        signals = timeline_events_to_replan_signals(
            events=tenant_events,
            rules=rules,
            tenant_id=candidate.tenant_id,
            now=now,
        ) if tenant_events and rules else ()
        replacements = replacements_by_objective.get(candidate.objective_ref, {})

        if not signals:
            if replacements:
                raise ValueError("timeline_swarm_unaffected_objective_has_replacements")
            runnable.append(candidate)
            decisions.append(
                TimelineObjectiveReplanDecision(
                    objective_ref=candidate.objective_ref,
                    tenant_id=candidate.tenant_id,
                    disposition=TimelineSwarmReplanDisposition.UNAFFECTED,
                    reason_codes=("timeline_swarm_no_actionable_reality_change",),
                )
            )
            continue

        scope = assess_objective_replan_scope(plan=candidate.plan, signals=signals)
        signal_ids = tuple(item.signal_id for item in signals)
        if scope.review_lane_ids:
            if replacements:
                raise ValueError("timeline_swarm_review_objective_cannot_accept_replacements")
            decisions.append(
                _decision_from_scope(
                    candidate=candidate,
                    scope=scope,
                    signal_ids=signal_ids,
                    disposition=TimelineSwarmReplanDisposition.HOLD_FOR_REVIEW,
                    reason_codes=("timeline_swarm_side_effect_review_required",),
                )
            )
            continue

        if not scope.auto_replan_lane_ids:
            if replacements:
                raise ValueError("timeline_swarm_unaffected_objective_has_replacements")
            runnable.append(candidate)
            decisions.append(
                _decision_from_scope(
                    candidate=candidate,
                    scope=scope,
                    signal_ids=signal_ids,
                    disposition=TimelineSwarmReplanDisposition.UNAFFECTED,
                    reason_codes=("timeline_swarm_signal_does_not_affect_objective",),
                )
            )
            continue

        if set(replacements) != set(scope.auto_replan_lane_ids):
            decisions.append(
                _decision_from_scope(
                    candidate=candidate,
                    scope=scope,
                    signal_ids=signal_ids,
                    disposition=TimelineSwarmReplanDisposition.REPLACEMENT_REQUIRED,
                    reason_codes=("timeline_swarm_fresh_replacement_required",),
                )
            )
            continue

        replanned = compose_replanned_parallel_plan(
            original=candidate.plan,
            scope=scope,
            replacements=replacements,
        )
        runnable.append(candidate.model_copy(update={"plan": replanned}))
        decisions.append(
            _decision_from_scope(
                candidate=candidate,
                scope=scope,
                signal_ids=signal_ids,
                disposition=TimelineSwarmReplanDisposition.REPLANNED,
                reason_codes=("timeline_swarm_safe_lanes_replanned",),
            )
        )

    return TimelineSwarmPreparation(
        runnable_candidates=tuple(runnable),
        decisions=tuple(decisions),
    )


async def execute_timeline_replanned_multi_objective_round(
    *,
    candidates: tuple[GlobalObjectiveCandidate, ...],
    events: tuple[RealWorldTimelineEvent, ...],
    rules: tuple[TimelineReplanRule, ...],
    replacements_by_objective: Mapping[str, Mapping[str, ParallelMissionLane]],
    bindings: MultiObjectiveBindings,
    active_leases: tuple[GlobalLaneLease, ...],
    now,
    lease_policy: GlobalLaneLeasePolicy | None = None,
    max_transitions_per_lane: int = 100,
) -> TimelineSwarmExecutionRound:
    preparation = prepare_timeline_replanned_candidates(
        candidates=candidates,
        events=events,
        rules=rules,
        replacements_by_objective=replacements_by_objective,
        now=now,
    )
    if not preparation.runnable_candidates:
        return TimelineSwarmExecutionRound(
            preparation=preparation,
            execution=None,
            active_leases_after_round=active_leases,
        )

    execution = await execute_multi_objective_lane_round(
        candidates=preparation.runnable_candidates,
        bindings=bindings,
        active_leases=active_leases,
        now=now,
        lease_policy=lease_policy,
        max_transitions_per_lane=max_transitions_per_lane,
    )
    return TimelineSwarmExecutionRound(
        preparation=preparation,
        execution=execution,
        active_leases_after_round=execution.active_leases_after_round,
    )
