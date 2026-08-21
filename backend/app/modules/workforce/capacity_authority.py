"""Effective Capacity Engine authority for roadmap 12/60.

This module composes existing Workforce foundations instead of creating a second
scheduler. It converts scheduled worker hours into effective capacity after
absence, breaks, other unavailability and skill feasibility. Outputs are
fingerprinted, deterministic and explainable so pressure/DPI can consume them
without treating roster headcount as usable capacity.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json

from .skill_capacity import SkillDemand, WorkerSkillCapacity, allocate_skill_capacity

ZERO = Decimal("0")
ONE = Decimal("1")
SUPPORTED_INTERVAL_MINUTES = frozenset({15, 30, 60})


class CapacityAuthorityError(ValueError):
    """Raised when effective capacity cannot be calculated without guessing."""


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise CapacityAuthorityError(f"{field_name} must be timezone-aware")


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _hash(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CapacityWorker:
    employee_id: str
    scheduled_hours: Decimal
    skills: frozenset[str]
    source_ref: str
    absence_hours: Decimal = ZERO
    break_hours: Decimal = ZERO
    unavailable_hours: Decimal = ZERO

    def __post_init__(self) -> None:
        if not self.employee_id.strip():
            raise CapacityAuthorityError("employee_id is required")
        if self.scheduled_hours < ZERO:
            raise CapacityAuthorityError("scheduled_hours cannot be negative")
        if any(
            value < ZERO
            for value in (self.absence_hours, self.break_hours, self.unavailable_hours)
        ):
            raise CapacityAuthorityError("capacity deductions cannot be negative")
        if self.absence_hours + self.break_hours + self.unavailable_hours > self.scheduled_hours:
            raise CapacityAuthorityError("worker deductions cannot exceed scheduled hours")
        if not self.skills:
            raise CapacityAuthorityError("capacity worker requires at least one approved skill")
        if not self.source_ref.strip():
            raise CapacityAuthorityError("capacity worker requires source_ref provenance")

    @property
    def available_hours(self) -> Decimal:
        return (
            self.scheduled_hours
            - self.absence_hours
            - self.break_hours
            - self.unavailable_hours
        )

    def canonical(self) -> dict[str, object]:
        return {
            "employee_id": self.employee_id,
            "scheduled_hours": _decimal_text(self.scheduled_hours),
            "absence_hours": _decimal_text(self.absence_hours),
            "break_hours": _decimal_text(self.break_hours),
            "unavailable_hours": _decimal_text(self.unavailable_hours),
            "available_hours": _decimal_text(self.available_hours),
            "skills": sorted(self.skills),
            "source_ref": self.source_ref,
        }


@dataclass(frozen=True, slots=True)
class EffectiveCapacityRequest:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    workers: tuple[CapacityWorker, ...]
    source_refs: tuple[str, ...]
    skill_demand: SkillDemand | None = None
    productivity_factor: Decimal = ONE

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.location_id.strip():
            raise CapacityAuthorityError("tenant_id and location_id are required")
        _aware(self.interval_start, "interval_start")
        if self.interval_minutes not in SUPPORTED_INTERVAL_MINUTES:
            raise CapacityAuthorityError("interval_minutes must be one of 15, 30 or 60")
        if not self.model_version.strip():
            raise CapacityAuthorityError("model_version is required")
        employee_ids = [worker.employee_id for worker in self.workers]
        if len(employee_ids) != len(set(employee_ids)):
            raise CapacityAuthorityError("employee_id values must be unique in a capacity request")
        if not self.source_refs or any(not value.strip() for value in self.source_refs):
            raise CapacityAuthorityError("capacity request requires authoritative source_refs")
        if not (ZERO < self.productivity_factor <= Decimal("1.5")):
            raise CapacityAuthorityError("productivity_factor must be in (0, 1.5]")


@dataclass(frozen=True, slots=True)
class EffectiveCapacitySnapshot:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    input_fingerprint: str
    snapshot_fingerprint: str
    scheduled_man_hours: Decimal
    absence_man_hours: Decimal
    break_man_hours: Decimal
    unavailable_man_hours: Decimal
    net_available_man_hours: Decimal
    skill_feasible_man_hours: Decimal
    skill_deficit_man_hours: Decimal
    productivity_factor: Decimal
    effective_man_hours: Decimal
    scheduled_fte: Decimal
    effective_capacity: Decimal
    skill_deficits: dict[str, Decimal]
    unused_worker_hours: dict[str, Decimal]
    source_refs: tuple[str, ...]
    contributors: tuple[dict[str, object], ...]

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "interval_start": self.interval_start.isoformat(),
            "interval_minutes": self.interval_minutes,
            "model_version": self.model_version,
            "input_fingerprint": self.input_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "scheduled_man_hours": _decimal_text(self.scheduled_man_hours),
            "absence_man_hours": _decimal_text(self.absence_man_hours),
            "break_man_hours": _decimal_text(self.break_man_hours),
            "unavailable_man_hours": _decimal_text(self.unavailable_man_hours),
            "net_available_man_hours": _decimal_text(self.net_available_man_hours),
            "skill_feasible_man_hours": _decimal_text(self.skill_feasible_man_hours),
            "skill_deficit_man_hours": _decimal_text(self.skill_deficit_man_hours),
            "productivity_factor": _decimal_text(self.productivity_factor),
            "effective_man_hours": _decimal_text(self.effective_man_hours),
            "scheduled_fte": _decimal_text(self.scheduled_fte),
            "effective_capacity": _decimal_text(self.effective_capacity),
            "skill_deficits": {
                key: _decimal_text(value) for key, value in sorted(self.skill_deficits.items())
            },
            "unused_worker_hours": {
                key: _decimal_text(value)
                for key, value in sorted(self.unused_worker_hours.items())
            },
            "source_refs": list(self.source_refs),
            "contributors": list(self.contributors),
        }


def build_effective_capacity_snapshot(
    request: EffectiveCapacityRequest,
) -> EffectiveCapacitySnapshot:
    workers = tuple(sorted(request.workers, key=lambda item: item.employee_id))
    scheduled = sum((worker.scheduled_hours for worker in workers), ZERO)
    absence = sum((worker.absence_hours for worker in workers), ZERO)
    breaks = sum((worker.break_hours for worker in workers), ZERO)
    unavailable = sum((worker.unavailable_hours for worker in workers), ZERO)
    net_available = sum((worker.available_hours for worker in workers), ZERO)

    if request.skill_demand is None:
        skill_feasible = net_available
        skill_deficits: dict[str, Decimal] = {}
        unused_worker_hours = {
            worker.employee_id: ZERO for worker in workers
        }
    else:
        allocation = allocate_skill_capacity(
            request.skill_demand,
            tuple(
                WorkerSkillCapacity(
                    employee_id=worker.employee_id,
                    available_hours=worker.available_hours,
                    skills=worker.skills,
                )
                for worker in workers
            ),
        )
        skill_feasible = sum(allocation.allocated_hours.values(), ZERO)
        skill_deficits = dict(allocation.deficit_hours)
        unused_worker_hours = dict(allocation.unused_worker_hours)

    skill_deficit_total = sum(skill_deficits.values(), ZERO)
    effective_man_hours = skill_feasible * request.productivity_factor
    interval_hours = Decimal(request.interval_minutes) / Decimal("60")
    scheduled_fte = scheduled / interval_hours if interval_hours > ZERO else ZERO
    effective_capacity = effective_man_hours / interval_hours if interval_hours > ZERO else ZERO

    contributors = tuple(worker.canonical() for worker in workers)
    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "interval_start": request.interval_start.isoformat(),
        "interval_minutes": request.interval_minutes,
        "model_version": request.model_version,
        "workers": list(contributors),
        "source_refs": sorted(request.source_refs),
        "productivity_factor": _decimal_text(request.productivity_factor),
        "skill_demand": (
            {
                skill: _decimal_text(hours)
                for skill, hours in sorted(request.skill_demand.required_hours.items())
            }
            if request.skill_demand is not None
            else None
        ),
    }
    input_fingerprint = _hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "scheduled_man_hours": _decimal_text(scheduled),
        "absence_man_hours": _decimal_text(absence),
        "break_man_hours": _decimal_text(breaks),
        "unavailable_man_hours": _decimal_text(unavailable),
        "net_available_man_hours": _decimal_text(net_available),
        "skill_feasible_man_hours": _decimal_text(skill_feasible),
        "skill_deficit_man_hours": _decimal_text(skill_deficit_total),
        "effective_man_hours": _decimal_text(effective_man_hours),
        "scheduled_fte": _decimal_text(scheduled_fte),
        "effective_capacity": _decimal_text(effective_capacity),
        "skill_deficits": {
            key: _decimal_text(value) for key, value in sorted(skill_deficits.items())
        },
    }
    snapshot_fingerprint = _hash(output_payload)

    return EffectiveCapacitySnapshot(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        interval_start=request.interval_start,
        interval_minutes=request.interval_minutes,
        model_version=request.model_version,
        input_fingerprint=input_fingerprint,
        snapshot_fingerprint=snapshot_fingerprint,
        scheduled_man_hours=scheduled,
        absence_man_hours=absence,
        break_man_hours=breaks,
        unavailable_man_hours=unavailable,
        net_available_man_hours=net_available,
        skill_feasible_man_hours=skill_feasible,
        skill_deficit_man_hours=skill_deficit_total,
        productivity_factor=request.productivity_factor,
        effective_man_hours=effective_man_hours,
        scheduled_fte=scheduled_fte,
        effective_capacity=effective_capacity,
        skill_deficits=skill_deficits,
        unused_worker_hours=unused_worker_hours,
        source_refs=tuple(sorted(request.source_refs)),
        contributors=contributors,
    )
