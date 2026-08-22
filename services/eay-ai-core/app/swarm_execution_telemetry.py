"""Secret-safe aggregate telemetry for Jarvis multi-objective swarm rounds.

This module summarizes orchestration health, not business truth. It deliberately
retains no prompts, payloads, company values, credentials or raw blocker details.
The resulting snapshot may inform scheduling/attention layers but never grants
truth or execution authority.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from .mission_runtime import MissionStatus
from .multi_objective_swarm_runtime import MultiObjectiveExecutionRound
from .parallel_mission_orchestration import ParallelLaneDisposition

SWARM_EXECUTION_TELEMETRY_CONTRACT = "eay-swarm-execution-telemetry-v1"


def _canonical_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _blocker_code(value: str) -> str:
    """Keep only low-cardinality blocker class; strip lane/step/resource detail."""

    return value.split(":", 1)[0].strip() or "unknown_blocker"


class ObjectiveExecutionTelemetry(BaseModel):
    objective_ref: str = Field(min_length=1)
    selected_lane_count: int = Field(ge=0)
    executed_lane_count: int = Field(ge=0)
    failed_lane_count: int = Field(ge=0)
    deferred_lane_count: int = Field(ge=0)
    completed_lane_count: int = Field(ge=0)
    halted_lane_count: int = Field(ge=0)
    transitions_executed: int = Field(ge=0)
    blocker_codes: tuple[str, ...] = ()


class SwarmExecutionTelemetrySnapshot(BaseModel):
    contract: str = SWARM_EXECUTION_TELEMETRY_CONTRACT
    tenant_id: str = Field(min_length=1)
    observed_at: datetime
    objective_count: int = Field(ge=0)
    objective_telemetry: tuple[ObjectiveExecutionTelemetry, ...]
    admitted_lane_count: int = Field(ge=0)
    globally_deferred_lane_count: int = Field(ge=0)
    released_lease_count: int = Field(ge=0)
    held_lease_count: int = Field(ge=0)
    total_transitions_executed: int = Field(ge=0)
    operational_pressure_score: float = Field(ge=0.0, le=1.0)
    blocker_codes: tuple[str, ...] = ()
    raw_payload_retained: bool = False
    business_values_retained: bool = False
    credential_material_retained: bool = False
    authoritative_truth_surface: bool = False
    execution_authority_granted: bool = False
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def telemetry_is_non_authoritative_and_integral(self) -> "SwarmExecutionTelemetrySnapshot":
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("swarm_telemetry_requires_timezone")
        if (
            self.raw_payload_retained
            or self.business_values_retained
            or self.credential_material_retained
        ):
            raise ValueError("swarm_telemetry_cannot_retain_sensitive_content")
        if self.authoritative_truth_surface:
            raise ValueError("swarm_telemetry_never_becomes_business_truth")
        if self.execution_authority_granted:
            raise ValueError("swarm_telemetry_never_grants_execution_authority")
        if self.objective_count != len(self.objective_telemetry):
            raise ValueError("swarm_telemetry_objective_count_mismatch")
        if self.total_transitions_executed != sum(
            item.transitions_executed for item in self.objective_telemetry
        ):
            raise ValueError("swarm_telemetry_transition_count_mismatch")
        if len(self.blocker_codes) != len(set(self.blocker_codes)):
            raise ValueError("swarm_telemetry_blocker_codes_must_be_unique")
        expected = _canonical_hash(
            self.model_dump(mode="json", exclude={"fingerprint"})
        )
        if self.fingerprint != expected:
            raise ValueError("swarm_telemetry_fingerprint_mismatch")
        return self


def _objective_telemetry(round_item) -> ObjectiveExecutionTelemetry:
    blockers: list[str] = []
    executed = failed = deferred = completed = halted = transitions = 0
    for result in round_item.results:
        blockers.extend(_blocker_code(item) for item in result.blockers)
        if result.summary is not None:
            blockers.extend(_blocker_code(item) for item in result.summary.blockers)
            transitions += result.summary.transitions_executed
            if result.summary.checkpoint.status is MissionStatus.COMPLETED:
                completed += 1
            elif result.summary.checkpoint.status is MissionStatus.HALTED:
                halted += 1
        if result.disposition is ParallelLaneDisposition.EXECUTED:
            executed += 1
        elif result.disposition is ParallelLaneDisposition.FAILED:
            failed += 1
        elif result.disposition in {
            ParallelLaneDisposition.DEFERRED,
            ParallelLaneDisposition.TERMINAL,
        }:
            deferred += 1

    return ObjectiveExecutionTelemetry(
        objective_ref=round_item.objective_ref,
        selected_lane_count=len(round_item.selected_lane_ids),
        executed_lane_count=executed,
        failed_lane_count=failed,
        deferred_lane_count=deferred,
        completed_lane_count=completed,
        halted_lane_count=halted,
        transitions_executed=transitions,
        blocker_codes=tuple(sorted(set(blockers))),
    )


def build_swarm_execution_telemetry(
    *,
    execution_round: MultiObjectiveExecutionRound,
    tenant_id: str,
    observed_at: datetime,
) -> SwarmExecutionTelemetrySnapshot:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("swarm_telemetry_requires_timezone")
    if any(item.tenant_id != tenant_id for item in execution_round.objective_rounds):
        raise ValueError("swarm_telemetry_cross_tenant_objective_forbidden")
    if any(item.tenant_id != tenant_id for item in execution_round.admission.selected):
        raise ValueError("swarm_telemetry_cross_tenant_admission_forbidden")
    if any(item.tenant_id != tenant_id for item in execution_round.active_leases_after_round):
        raise ValueError("swarm_telemetry_cross_tenant_lease_forbidden")

    objective_items = tuple(
        _objective_telemetry(item)
        for item in sorted(execution_round.objective_rounds, key=lambda value: value.objective_ref)
    )
    admitted = len(execution_round.admission.selected)
    globally_deferred = len(execution_round.deferred)
    held = len(execution_round.held_lease_ids)
    released = len(execution_round.released_lease_ids)
    all_blockers = tuple(
        sorted(
            {
                *(
                    _blocker_code(blocker)
                    for blockers in execution_round.deferred.values()
                    for blocker in blockers
                ),
                *(
                    blocker
                    for item in objective_items
                    for blocker in item.blocker_codes
                ),
            }
        )
    )

    lane_pressure_denominator = admitted + globally_deferred
    deferred_ratio = (
        globally_deferred / lane_pressure_denominator
        if lane_pressure_denominator
        else 0.0
    )
    lease_pressure_denominator = held + released
    held_ratio = (
        held / lease_pressure_denominator
        if lease_pressure_denominator
        else 0.0
    )
    blocked_objectives = sum(bool(item.blocker_codes) for item in objective_items)
    objective_pressure = (
        blocked_objectives / len(objective_items)
        if objective_items
        else 0.0
    )
    pressure = round(
        min(
            (0.45 * deferred_ratio)
            + (0.35 * held_ratio)
            + (0.20 * objective_pressure),
            1.0,
        ),
        6,
    )

    payload = dict(
        tenant_id=tenant_id,
        observed_at=observed_at,
        objective_count=len(objective_items),
        objective_telemetry=objective_items,
        admitted_lane_count=admitted,
        globally_deferred_lane_count=globally_deferred,
        released_lease_count=released,
        held_lease_count=held,
        total_transitions_executed=sum(
            item.transitions_executed for item in objective_items
        ),
        operational_pressure_score=pressure,
        blocker_codes=all_blockers,
    )
    draft = SwarmExecutionTelemetrySnapshot.model_construct(
        **payload,
        fingerprint="0" * 64,
    )
    fingerprint = _canonical_hash(
        draft.model_dump(mode="json", exclude={"fingerprint"})
    )
    return SwarmExecutionTelemetrySnapshot(**payload, fingerprint=fingerprint)
