"""Scheduled capability-capacity adapter for governed Workforce demand.

This bridge compares a governed activity-demand snapshot with the canonical
Employee Master and scheduled shifts for the same worksite/interval. It counts
only employees whose capabilities can actually satisfy each activity bundle.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from . import service
from .work_activity_planning import (
    CapabilityWorker,
    WorkActivityCapacityPlan,
    build_work_activity_capacity_plan,
)
from .work_activity_runtime import build_catalog_demand_snapshot


ZERO = Decimal("0")


def _normal(value: object) -> str:
    return str(value or "").strip().casefold().replace("i̇", "i")


def _worksite_aliases(worksite_id: str) -> set[str]:
    target = _normal(worksite_id)
    for warehouse in service.list_warehouses():
        aliases = {
            _normal(warehouse.get("id")),
            _normal(warehouse.get("code")),
            _normal(warehouse.get("name")),
            _normal(str(warehouse.get("name") or "").split(" (")[0]),
        }
        if target in aliases:
            aliases.discard("")
            return aliases
    return {target} if target else set()


def _shift_matches_worksite(shift: dict, aliases: set[str]) -> bool:
    candidates = {
        _normal(shift.get("warehouse_id")),
        _normal(shift.get("warehouse")),
        _normal(str(shift.get("warehouse") or "").split(" (")[0]),
    }
    candidates.discard("")
    return bool(candidates.intersection(aliases))


def _scheduled_workers(worksite_id: str, interval_start, interval_minutes: int) -> tuple[CapabilityWorker, ...]:
    interval_end = interval_start + timedelta(minutes=interval_minutes)
    aliases = _worksite_aliases(worksite_id)
    shifts_by_employee: dict[str, list[dict]] = {}

    for shift in service.list_shifts():
        if shift.get("status") in {"İptal", "Tamamlandı"}:
            continue
        if not _shift_matches_worksite(shift, aliases):
            continue
        start, end = service._shift_interval(shift)
        overlap_start = max(start, interval_start)
        overlap_end = min(end, interval_end)
        if overlap_end <= overlap_start:
            continue
        employee_id = str(shift.get("person_id") or "")
        if employee_id:
            shifts_by_employee.setdefault(employee_id, []).append(
                {**shift, "_overlap_minutes": Decimal(str((overlap_end - overlap_start).total_seconds() / 60))}
            )

    workers: list[CapabilityWorker] = []
    interval_hours = Decimal(interval_minutes) / Decimal("60")
    for employee_id, shifts in sorted(shifts_by_employee.items()):
        person = service.resolve_person_identity(employee_id, "EMPLOYEE_ID")
        if person is None or not service.person_has_workforce_access(person, interval_start.date().isoformat()):
            continue
        day_context = service._day_context(employee_id, interval_start.date().isoformat())
        if day_context.get("on_approved_leave"):
            continue
        overlap_hours = sum((row["_overlap_minutes"] for row in shifts), ZERO) / Decimal("60")
        available_hours = min(overlap_hours, interval_hours)
        if available_hours <= ZERO:
            continue
        source_ref = "workforce-schedule:" + ",".join(
            sorted(str(row.get("id") or "unknown") for row in shifts)
        )
        workers.append(
            CapabilityWorker(
                employee_id=employee_id,
                available_hours=available_hours,
                skill_keys=frozenset(str(value) for value in person.get("skill_keys") or []),
                certification_keys=frozenset(
                    str(value) for value in person.get("certification_keys") or []
                ),
                equipment_keys=frozenset(str(value) for value in person.get("equipment_keys") or []),
                source_ref=source_ref,
            )
        )
    return tuple(workers)


def build_scheduled_capacity_plan(
    *,
    worksite_id: str,
    interval_start,
    interval_minutes: int,
    model_version: str,
    signals: list[dict],
) -> WorkActivityCapacityPlan:
    demand = build_catalog_demand_snapshot(
        worksite_id=worksite_id,
        interval_start=interval_start,
        interval_minutes=interval_minutes,
        model_version=model_version,
        signals=signals,
    )
    workers = _scheduled_workers(worksite_id, interval_start, interval_minutes)
    return build_work_activity_capacity_plan(demand, workers)
