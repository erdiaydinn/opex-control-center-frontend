"""Versioned Workforce demand and labor-standard authority (roadmap 11/60).

The existing demand_model module remains the canonical math kernel. This layer
adds effective-dated labor standards, deterministic input/output fingerprints and
fully explainable demand contributors. It deliberately does not schedule named
employees or infer labor standards when approved authority is missing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Iterable

from .demand_model import (
    DemandOverheads,
    PickerDemandComponents,
    compute_hourly_picker_demand,
    task_man_hours,
)


ZERO = Decimal("0")
ONE = Decimal("1")
CANONICAL_ACTIVITIES = tuple(PickerDemandComponents().as_mapping().keys())
SUPPORTED_INTERVAL_MINUTES = frozenset({15, 30, 60})


class DemandAuthorityError(ValueError):
    """Raised when demand truth cannot be resolved without guessing."""


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DemandAuthorityError(f"{field_name} must be timezone-aware")


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _canonical_hash(value: object) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class LaborStandardVersion:
    activity: str
    version: int
    seconds_per_unit: Decimal
    people: Decimal
    effective_from: datetime
    source_ref: str
    approved_by: str
    effective_until: datetime | None = None
    status: str = "approved"

    def __post_init__(self) -> None:
        if self.activity not in CANONICAL_ACTIVITIES:
            raise DemandAuthorityError(f"unsupported labor-standard activity: {self.activity}")
        if self.version <= 0:
            raise DemandAuthorityError("labor-standard version must be positive")
        if self.seconds_per_unit <= ZERO:
            raise DemandAuthorityError("seconds_per_unit must be positive")
        if self.people <= ZERO:
            raise DemandAuthorityError("people must be positive")
        _aware(self.effective_from, "effective_from")
        if self.effective_until is not None:
            _aware(self.effective_until, "effective_until")
            if self.effective_until <= self.effective_from:
                raise DemandAuthorityError("effective_until must be after effective_from")
        if self.status not in {"approved", "retired"}:
            raise DemandAuthorityError("labor-standard status must be approved or retired")
        if not self.source_ref.strip():
            raise DemandAuthorityError("labor standard requires source_ref provenance")
        if not self.approved_by.strip():
            raise DemandAuthorityError("labor standard requires approved_by")

    def is_effective(self, at: datetime) -> bool:
        _aware(at, "at")
        return (
            self.status == "approved"
            and self.effective_from <= at
            and (self.effective_until is None or at < self.effective_until)
        )

    @property
    def authority_ref(self) -> str:
        return f"{self.activity}:v{self.version}:{self.effective_from.isoformat()}"


@dataclass(frozen=True, slots=True)
class DemandDriver:
    driver_key: str
    activity: str
    volume: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        if not self.driver_key.strip():
            raise DemandAuthorityError("driver_key is required")
        if self.activity not in CANONICAL_ACTIVITIES:
            raise DemandAuthorityError(f"unsupported demand activity: {self.activity}")
        if self.volume < ZERO:
            raise DemandAuthorityError("driver volume cannot be negative")
        if not self.source_ref.strip():
            raise DemandAuthorityError("demand driver requires source_ref provenance")


@dataclass(frozen=True, slots=True)
class DemandRequest:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    drivers: tuple[DemandDriver, ...]
    overheads: DemandOverheads = DemandOverheads()

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.location_id.strip():
            raise DemandAuthorityError("tenant_id and location_id are required")
        _aware(self.interval_start, "interval_start")
        if self.interval_minutes not in SUPPORTED_INTERVAL_MINUTES:
            raise DemandAuthorityError("interval_minutes must be one of 15, 30 or 60")
        if not self.model_version.strip():
            raise DemandAuthorityError("model_version is required")
        keys = [driver.driver_key for driver in self.drivers]
        if len(keys) != len(set(keys)):
            raise DemandAuthorityError("driver_key values must be unique within a demand request")


@dataclass(frozen=True, slots=True)
class DemandContribution:
    driver_key: str
    activity: str
    volume: Decimal
    source_ref: str
    labor_standard_ref: str
    labor_standard_source_ref: str
    seconds_per_unit: Decimal
    people: Decimal
    man_hours: Decimal

    def canonical(self) -> dict[str, str]:
        return {
            "driver_key": self.driver_key,
            "activity": self.activity,
            "volume": _decimal_text(self.volume),
            "source_ref": self.source_ref,
            "labor_standard_ref": self.labor_standard_ref,
            "labor_standard_source_ref": self.labor_standard_source_ref,
            "seconds_per_unit": _decimal_text(self.seconds_per_unit),
            "people": _decimal_text(self.people),
            "man_hours": _decimal_text(self.man_hours),
        }


@dataclass(frozen=True, slots=True)
class DemandSnapshot:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    input_fingerprint: str
    snapshot_fingerprint: str
    base_man_hours: Decimal
    overhead_man_hours: Decimal
    required_man_hours: Decimal
    required_people: Decimal
    contributions: tuple[DemandContribution, ...]
    labor_standard_refs: tuple[str, ...]

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "interval_start": self.interval_start.isoformat(),
            "interval_minutes": self.interval_minutes,
            "model_version": self.model_version,
            "input_fingerprint": self.input_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "base_man_hours": _decimal_text(self.base_man_hours),
            "overhead_man_hours": _decimal_text(self.overhead_man_hours),
            "required_man_hours": _decimal_text(self.required_man_hours),
            "required_people": _decimal_text(self.required_people),
            "labor_standard_refs": list(self.labor_standard_refs),
            "contributions": [item.canonical() for item in self.contributions],
        }


def resolve_labor_standard(
    standards: Iterable[LaborStandardVersion],
    *,
    activity: str,
    at: datetime,
) -> LaborStandardVersion:
    effective = [
        standard
        for standard in standards
        if standard.activity == activity and standard.is_effective(at)
    ]
    if not effective:
        raise DemandAuthorityError(
            f"no approved effective labor standard for non-zero {activity} demand"
        )
    if len(effective) != 1:
        refs = ",".join(sorted(item.authority_ref for item in effective))
        raise DemandAuthorityError(
            f"ambiguous effective labor standards for {activity}: {refs}"
        )
    return effective[0]


def build_demand_snapshot(
    request: DemandRequest,
    standards: Iterable[LaborStandardVersion],
) -> DemandSnapshot:
    """Build an immutable deterministic demand snapshot from approved authority.

    Non-zero demand is never calculated from a default/guessed MHS. Every
    contributor points to an exact effective labor-standard version and source.
    """

    standards = tuple(standards)
    contributions: list[DemandContribution] = []
    activity_hours = {activity: ZERO for activity in CANONICAL_ACTIVITIES}

    for driver in sorted(request.drivers, key=lambda item: (item.activity, item.driver_key)):
        if driver.volume == ZERO:
            continue
        standard = resolve_labor_standard(
            standards,
            activity=driver.activity,
            at=request.interval_start,
        )
        man_hours = task_man_hours(
            volume=driver.volume,
            seconds_per_unit=standard.seconds_per_unit,
            people=standard.people,
        )
        activity_hours[driver.activity] += man_hours
        contributions.append(
            DemandContribution(
                driver_key=driver.driver_key,
                activity=driver.activity,
                volume=driver.volume,
                source_ref=driver.source_ref,
                labor_standard_ref=standard.authority_ref,
                labor_standard_source_ref=standard.source_ref,
                seconds_per_unit=standard.seconds_per_unit,
                people=standard.people,
                man_hours=man_hours,
            )
        )

    components = PickerDemandComponents(**activity_hours)
    calculated = compute_hourly_picker_demand(components, request.overheads)
    interval_hours = Decimal(request.interval_minutes) / Decimal("60")
    required_people = (
        calculated.total_man_hours / interval_hours
        if interval_hours > ZERO
        else ZERO
    )
    labor_refs = tuple(sorted({item.labor_standard_ref for item in contributions}))
    canonical_contributions = [item.canonical() for item in contributions]
    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "interval_start": request.interval_start.isoformat(),
        "interval_minutes": request.interval_minutes,
        "model_version": request.model_version,
        "overheads": {
            "fatigue_factor": _decimal_text(request.overheads.fatigue_factor),
            "buffer_tasks": _decimal_text(request.overheads.buffer_tasks),
            "break_time": _decimal_text(request.overheads.break_time),
        },
        "contributions": canonical_contributions,
        "labor_standard_refs": list(labor_refs),
    }
    input_fingerprint = _canonical_hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "base_man_hours": _decimal_text(calculated.base_man_hours),
        "overhead_man_hours": _decimal_text(calculated.overhead_man_hours),
        "required_man_hours": _decimal_text(calculated.total_man_hours),
        "required_people": _decimal_text(required_people),
    }
    snapshot_fingerprint = _canonical_hash(output_payload)

    return DemandSnapshot(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        interval_start=request.interval_start,
        interval_minutes=request.interval_minutes,
        model_version=request.model_version,
        input_fingerprint=input_fingerprint,
        snapshot_fingerprint=snapshot_fingerprint,
        base_man_hours=calculated.base_man_hours,
        overhead_man_hours=calculated.overhead_man_hours,
        required_man_hours=calculated.total_man_hours,
        required_people=required_people,
        contributions=tuple(contributions),
        labor_standard_refs=labor_refs,
    )
