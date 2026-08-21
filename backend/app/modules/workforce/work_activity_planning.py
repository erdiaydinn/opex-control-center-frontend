"""Generic work-activity planning bridge.

This module connects governed activity demand to capability-feasible capacity and
the existing proposal-only Workforce optimizer. It does not execute shifts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from typing import Iterable

from .optimizer_authority import OptimizationCandidate, OptimizerRequest, OptimizerProposal, build_optimizer_proposal
from .work_activity_authority import WorkActivityDemandSnapshot


ZERO = Decimal("0")


class WorkActivityPlanningError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CapabilityWorker:
    employee_id: str
    available_hours: Decimal
    skill_keys: frozenset[str]
    certification_keys: frozenset[str] = frozenset()
    equipment_keys: frozenset[str] = frozenset()
    source_ref: str = ""

    def __post_init__(self) -> None:
        if not self.employee_id.strip():
            raise WorkActivityPlanningError("employee_id is required")
        if self.available_hours < ZERO:
            raise WorkActivityPlanningError("available_hours cannot be negative")
        if not self.source_ref.strip():
            raise WorkActivityPlanningError("worker capacity requires source_ref provenance")


@dataclass(frozen=True, slots=True)
class ActivityCapacityRow:
    activity_key: str
    required_man_hours: Decimal
    allocated_man_hours: Decimal
    deficit_man_hours: Decimal
    required_skill_keys: tuple[str, ...]
    required_certification_keys: tuple[str, ...]
    required_equipment_keys: tuple[str, ...]
    eligible_worker_ids: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "activity_key": self.activity_key,
            "required_man_hours": str(self.required_man_hours),
            "allocated_man_hours": str(self.allocated_man_hours),
            "deficit_man_hours": str(self.deficit_man_hours),
            "required_skill_keys": list(self.required_skill_keys),
            "required_certification_keys": list(self.required_certification_keys),
            "required_equipment_keys": list(self.required_equipment_keys),
            "eligible_worker_ids": list(self.eligible_worker_ids),
        }


@dataclass(frozen=True, slots=True)
class WorkActivityCapacityPlan:
    tenant_id: str
    location_id: str
    interval_start: str
    interval_minutes: int
    demand_snapshot_fingerprint: str
    required_man_hours: Decimal
    available_man_hours: Decimal
    allocated_man_hours: Decimal
    deficit_man_hours: Decimal
    recommended_people: int
    root_cause: str
    primary_capability_target: str | None
    rows: tuple[ActivityCapacityRow, ...]
    worker_source_refs: tuple[str, ...]
    human_approval_required: bool = True
    automatic_execution_permitted: bool = False

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "interval_start": self.interval_start,
            "interval_minutes": self.interval_minutes,
            "demand_snapshot_fingerprint": self.demand_snapshot_fingerprint,
            "required_man_hours": str(self.required_man_hours),
            "available_man_hours": str(self.available_man_hours),
            "allocated_man_hours": str(self.allocated_man_hours),
            "deficit_man_hours": str(self.deficit_man_hours),
            "recommended_people": self.recommended_people,
            "root_cause": self.root_cause,
            "primary_capability_target": self.primary_capability_target,
            "rows": [row.as_record() for row in self.rows],
            "worker_source_refs": list(self.worker_source_refs),
            "human_approval_required": self.human_approval_required,
            "automatic_execution_permitted": self.automatic_execution_permitted,
        }


def _eligible(worker: CapabilityWorker, contribution) -> bool:
    return (
        set(contribution.required_skill_keys).issubset(worker.skill_keys)
        and set(contribution.required_certification_keys).issubset(worker.certification_keys)
        and set(contribution.required_equipment_keys).issubset(worker.equipment_keys)
    )


def build_work_activity_capacity_plan(
    demand: WorkActivityDemandSnapshot,
    workers: Iterable[CapabilityWorker],
) -> WorkActivityCapacityPlan:
    """Allocate every available worker hour at most once to activity demand.

    Scarcer activity capability bundles are allocated first, making the result
    deterministic and preventing generic headcount from masquerading as usable
    capacity.
    """
    worker_rows = tuple(sorted(workers, key=lambda item: item.employee_id))
    ids = [worker.employee_id for worker in worker_rows]
    if len(ids) != len(set(ids)):
        raise WorkActivityPlanningError("employee_id values must be unique")
    remaining = {worker.employee_id: worker.available_hours for worker in worker_rows}

    contributions = [item for item in demand.contributions if item.man_hours > ZERO]

    def eligible_ids(item) -> tuple[str, ...]:
        return tuple(worker.employee_id for worker in worker_rows if _eligible(worker, item))

    contributions.sort(
        key=lambda item: (
            sum((remaining[worker_id] for worker_id in eligible_ids(item)), ZERO),
            item.activity_key,
            item.driver_key,
        )
    )
    rows: list[ActivityCapacityRow] = []
    for contribution in contributions:
        needed = contribution.man_hours
        qualified = [worker for worker in worker_rows if _eligible(worker, contribution)]
        qualified.sort(
            key=lambda worker: (
                len(worker.skill_keys) + len(worker.certification_keys) + len(worker.equipment_keys),
                worker.employee_id,
            )
        )
        allocated = ZERO
        for worker in qualified:
            if needed <= ZERO:
                break
            available = remaining[worker.employee_id]
            if available <= ZERO:
                continue
            amount = min(needed, available)
            remaining[worker.employee_id] -= amount
            needed -= amount
            allocated += amount
        rows.append(
            ActivityCapacityRow(
                activity_key=contribution.activity_key,
                required_man_hours=contribution.man_hours,
                allocated_man_hours=allocated,
                deficit_man_hours=max(needed, ZERO),
                required_skill_keys=tuple(contribution.required_skill_keys),
                required_certification_keys=tuple(contribution.required_certification_keys),
                required_equipment_keys=tuple(contribution.required_equipment_keys),
                eligible_worker_ids=tuple(worker.employee_id for worker in qualified),
            )
        )

    required = sum((row.required_man_hours for row in rows), ZERO)
    allocated = sum((row.allocated_man_hours for row in rows), ZERO)
    deficit = sum((row.deficit_man_hours for row in rows), ZERO)
    available = sum((worker.available_hours for worker in worker_rows), ZERO)
    interval_hours = Decimal(demand.interval_minutes) / Decimal("60")
    recommended_people = int((deficit / interval_hours).to_integral_value(rounding=ROUND_CEILING)) if deficit > ZERO else 0
    deficit_rows = [row for row in rows if row.deficit_man_hours > ZERO]

    if not deficit_rows:
        root_cause = "no_pressure_signal"
        primary_target = None
    elif available + Decimal("0.000001") >= required:
        root_cause = "skill_mix_constraint"
        primary = sorted(deficit_rows, key=lambda row: (-row.deficit_man_hours, row.activity_key))[0]
        if len(primary.required_skill_keys) == 1 and not primary.required_certification_keys and not primary.required_equipment_keys:
            primary_target = primary.required_skill_keys[0]
        else:
            primary_target = f"activity:{primary.activity_key}"
    else:
        root_cause = "manpower_capacity_shortage"
        primary_target = None

    return WorkActivityCapacityPlan(
        tenant_id=demand.tenant_id,
        location_id=demand.location_id,
        interval_start=demand.interval_start.isoformat(),
        interval_minutes=demand.interval_minutes,
        demand_snapshot_fingerprint=demand.snapshot_fingerprint,
        required_man_hours=required,
        available_man_hours=available,
        allocated_man_hours=allocated,
        deficit_man_hours=deficit,
        recommended_people=recommended_people,
        root_cause=root_cause,
        primary_capability_target=primary_target,
        rows=tuple(rows),
        worker_source_refs=tuple(sorted({worker.source_ref for worker in worker_rows})),
    )


def build_optimizer_for_activity_plan(
    plan: WorkActivityCapacityPlan,
    *,
    model_version: str,
    candidates: tuple[OptimizationCandidate, ...],
    max_incremental_cost_minor_units: int,
    max_actions: int = 4,
) -> OptimizerProposal:
    """Translate the generic capacity plan into the existing proposal authority."""
    if len(plan.demand_snapshot_fingerprint) != 64:
        raise WorkActivityPlanningError("demand snapshot fingerprint must be SHA-256")
    root_cause = plan.root_cause
    skill_deficit = plan.deficit_man_hours if root_cause == "skill_mix_constraint" else ZERO
    request = OptimizerRequest(
        tenant_id=plan.tenant_id,
        location_id=plan.location_id,
        model_version=model_version,
        dpi_snapshot_fingerprint=plan.demand_snapshot_fingerprint,
        root_cause=root_cause,
        manpower_shortage=root_cause == "manpower_capacity_shortage",
        capacity_gap_man_hours=plan.deficit_man_hours,
        skill_deficit_man_hours=skill_deficit,
        candidates=candidates,
        max_incremental_cost_minor_units=max_incremental_cost_minor_units,
        max_actions=max_actions,
        required_skill=plan.primary_capability_target if root_cause == "skill_mix_constraint" else None,
    )
    return build_optimizer_proposal(request)
