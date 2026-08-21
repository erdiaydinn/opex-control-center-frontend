"""Tenant-scoped, industry-neutral work activity and labor-demand authority.

This is the generic successor layer above the original darkstore/picker demand
model. It deliberately keeps the old model intact as a compatibility profile.
No restaurant, factory, retail, kiosk or warehouse activity is hard-coded into
runtime authority: tenants approve effective-dated activity and labor-standard
versions, and demand fails closed when either authority is missing or ambiguous.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json
import re
from typing import Iterable


ZERO = Decimal("0")
SUPPORTED_INTERVAL_MINUTES = frozenset({15, 30, 60})
DEMAND_MODES = frozenset({"VOLUME", "FIXED", "EVENT"})
AUTHORITY_STATUSES = frozenset({"APPROVED", "RETIRED"})
_ACTIVITY_KEY = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_UNIT_KEY = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


class WorkActivityAuthorityError(ValueError):
    """Raised when activity/labor authority cannot be resolved without guessing."""


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise WorkActivityAuthorityError(f"{field_name} must be timezone-aware")


def _nonempty(value: str, field_name: str) -> str:
    result = str(value or "").strip()
    if not result:
        raise WorkActivityAuthorityError(f"{field_name} is required")
    return result


def _unique_tuple(values: Iterable[str]) -> tuple[str, ...]:
    normalized = tuple(str(value).strip() for value in values if str(value).strip())
    if len(normalized) != len(set(normalized)):
        raise WorkActivityAuthorityError("activity capability keys must be unique")
    return tuple(sorted(normalized))


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
class WorkActivityVersion:
    tenant_id: str
    activity_key: str
    version: int
    display_name: str
    category: str
    unit_key: str
    demand_mode: str
    effective_from: datetime
    source_ref: str
    approved_by: str
    required_skill_keys: tuple[str, ...] = ()
    required_certification_keys: tuple[str, ...] = ()
    required_equipment_keys: tuple[str, ...] = ()
    safety_tags: tuple[str, ...] = ()
    location_types: tuple[str, ...] = ()
    effective_until: datetime | None = None
    status: str = "APPROVED"

    def __post_init__(self) -> None:
        _nonempty(self.tenant_id, "tenant_id")
        if not _ACTIVITY_KEY.fullmatch(self.activity_key):
            raise WorkActivityAuthorityError("activity_key must be stable snake_case")
        if self.version <= 0:
            raise WorkActivityAuthorityError("activity version must be positive")
        _nonempty(self.display_name, "display_name")
        _nonempty(self.category, "category")
        if not _UNIT_KEY.fullmatch(self.unit_key):
            raise WorkActivityAuthorityError("unit_key must be stable snake_case")
        if self.demand_mode not in DEMAND_MODES:
            raise WorkActivityAuthorityError(f"unsupported demand_mode: {self.demand_mode}")
        if self.status not in AUTHORITY_STATUSES:
            raise WorkActivityAuthorityError(f"unsupported activity status: {self.status}")
        _aware(self.effective_from, "effective_from")
        if self.effective_until is not None:
            _aware(self.effective_until, "effective_until")
            if self.effective_until <= self.effective_from:
                raise WorkActivityAuthorityError("effective_until must be after effective_from")
        _nonempty(self.source_ref, "source_ref")
        _nonempty(self.approved_by, "approved_by")
        object.__setattr__(self, "required_skill_keys", _unique_tuple(self.required_skill_keys))
        object.__setattr__(self, "required_certification_keys", _unique_tuple(self.required_certification_keys))
        object.__setattr__(self, "required_equipment_keys", _unique_tuple(self.required_equipment_keys))
        object.__setattr__(self, "safety_tags", _unique_tuple(self.safety_tags))
        object.__setattr__(self, "location_types", _unique_tuple(self.location_types))

    def is_effective(self, *, tenant_id: str, at: datetime) -> bool:
        _aware(at, "at")
        return (
            self.tenant_id == tenant_id
            and self.status == "APPROVED"
            and self.effective_from <= at
            and (self.effective_until is None or at < self.effective_until)
        )

    @property
    def authority_ref(self) -> str:
        return f"{self.tenant_id}:{self.activity_key}:v{self.version}:{self.effective_from.isoformat()}"


@dataclass(frozen=True, slots=True)
class ActivityLaborStandardVersion:
    tenant_id: str
    activity_key: str
    version: int
    seconds_per_unit: Decimal
    people: Decimal
    effective_from: datetime
    source_ref: str
    approved_by: str
    effective_until: datetime | None = None
    status: str = "APPROVED"

    def __post_init__(self) -> None:
        _nonempty(self.tenant_id, "tenant_id")
        if not _ACTIVITY_KEY.fullmatch(self.activity_key):
            raise WorkActivityAuthorityError("activity_key must be stable snake_case")
        if self.version <= 0:
            raise WorkActivityAuthorityError("labor-standard version must be positive")
        if self.seconds_per_unit <= ZERO:
            raise WorkActivityAuthorityError("seconds_per_unit must be positive")
        if self.people <= ZERO:
            raise WorkActivityAuthorityError("people must be positive")
        if self.status not in AUTHORITY_STATUSES:
            raise WorkActivityAuthorityError(f"unsupported labor-standard status: {self.status}")
        _aware(self.effective_from, "effective_from")
        if self.effective_until is not None:
            _aware(self.effective_until, "effective_until")
            if self.effective_until <= self.effective_from:
                raise WorkActivityAuthorityError("effective_until must be after effective_from")
        _nonempty(self.source_ref, "source_ref")
        _nonempty(self.approved_by, "approved_by")

    def is_effective(self, *, tenant_id: str, at: datetime) -> bool:
        _aware(at, "at")
        return (
            self.tenant_id == tenant_id
            and self.status == "APPROVED"
            and self.effective_from <= at
            and (self.effective_until is None or at < self.effective_until)
        )

    @property
    def authority_ref(self) -> str:
        return f"{self.tenant_id}:{self.activity_key}:labor:v{self.version}:{self.effective_from.isoformat()}"


@dataclass(frozen=True, slots=True)
class WorkloadSignal:
    driver_key: str
    activity_key: str
    demand_mode: str
    quantity: Decimal
    source_ref: str

    def __post_init__(self) -> None:
        _nonempty(self.driver_key, "driver_key")
        if not _ACTIVITY_KEY.fullmatch(self.activity_key):
            raise WorkActivityAuthorityError("activity_key must be stable snake_case")
        if self.demand_mode not in DEMAND_MODES:
            raise WorkActivityAuthorityError(f"unsupported signal demand_mode: {self.demand_mode}")
        if self.quantity < ZERO:
            raise WorkActivityAuthorityError("workload quantity cannot be negative")
        _nonempty(self.source_ref, "source_ref")


@dataclass(frozen=True, slots=True)
class WorkActivityDemandRequest:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    signals: tuple[WorkloadSignal, ...]

    def __post_init__(self) -> None:
        _nonempty(self.tenant_id, "tenant_id")
        _nonempty(self.location_id, "location_id")
        _aware(self.interval_start, "interval_start")
        if self.interval_minutes not in SUPPORTED_INTERVAL_MINUTES:
            raise WorkActivityAuthorityError("interval_minutes must be one of 15, 30 or 60")
        _nonempty(self.model_version, "model_version")
        driver_keys = [signal.driver_key for signal in self.signals]
        if len(driver_keys) != len(set(driver_keys)):
            raise WorkActivityAuthorityError("driver_key values must be unique within a demand request")


@dataclass(frozen=True, slots=True)
class WorkActivityDemandContribution:
    driver_key: str
    activity_key: str
    activity_name: str
    category: str
    unit_key: str
    demand_mode: str
    quantity: Decimal
    source_ref: str
    activity_authority_ref: str
    labor_standard_ref: str
    labor_standard_source_ref: str
    seconds_per_unit: Decimal
    people: Decimal
    man_hours: Decimal
    required_skill_keys: tuple[str, ...]
    required_certification_keys: tuple[str, ...]
    required_equipment_keys: tuple[str, ...]
    safety_tags: tuple[str, ...]

    def canonical(self) -> dict[str, object]:
        return {
            "driver_key": self.driver_key,
            "activity_key": self.activity_key,
            "activity_name": self.activity_name,
            "category": self.category,
            "unit_key": self.unit_key,
            "demand_mode": self.demand_mode,
            "quantity": _decimal_text(self.quantity),
            "source_ref": self.source_ref,
            "activity_authority_ref": self.activity_authority_ref,
            "labor_standard_ref": self.labor_standard_ref,
            "labor_standard_source_ref": self.labor_standard_source_ref,
            "seconds_per_unit": _decimal_text(self.seconds_per_unit),
            "people": _decimal_text(self.people),
            "man_hours": _decimal_text(self.man_hours),
            "required_skill_keys": list(self.required_skill_keys),
            "required_certification_keys": list(self.required_certification_keys),
            "required_equipment_keys": list(self.required_equipment_keys),
            "safety_tags": list(self.safety_tags),
        }


@dataclass(frozen=True, slots=True)
class WorkActivityDemandSnapshot:
    tenant_id: str
    location_id: str
    interval_start: datetime
    interval_minutes: int
    model_version: str
    input_fingerprint: str
    snapshot_fingerprint: str
    required_man_hours: Decimal
    required_people: Decimal
    contributions: tuple[WorkActivityDemandContribution, ...]
    activity_authority_refs: tuple[str, ...]
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
            "required_man_hours": _decimal_text(self.required_man_hours),
            "required_people": _decimal_text(self.required_people),
            "activity_authority_refs": list(self.activity_authority_refs),
            "labor_standard_refs": list(self.labor_standard_refs),
            "contributions": [item.canonical() for item in self.contributions],
        }


def resolve_activity(
    activities: Iterable[WorkActivityVersion],
    *,
    tenant_id: str,
    activity_key: str,
    at: datetime,
) -> WorkActivityVersion:
    effective = [
        activity
        for activity in activities
        if activity.activity_key == activity_key and activity.is_effective(tenant_id=tenant_id, at=at)
    ]
    if not effective:
        raise WorkActivityAuthorityError(
            f"no approved effective work activity for {tenant_id}:{activity_key}"
        )
    if len(effective) != 1:
        refs = ",".join(sorted(item.authority_ref for item in effective))
        raise WorkActivityAuthorityError(
            f"ambiguous effective work activities for {tenant_id}:{activity_key}: {refs}"
        )
    return effective[0]


def resolve_activity_labor_standard(
    standards: Iterable[ActivityLaborStandardVersion],
    *,
    tenant_id: str,
    activity_key: str,
    at: datetime,
) -> ActivityLaborStandardVersion:
    effective = [
        standard
        for standard in standards
        if standard.activity_key == activity_key and standard.is_effective(tenant_id=tenant_id, at=at)
    ]
    if not effective:
        raise WorkActivityAuthorityError(
            f"no approved effective labor standard for {tenant_id}:{activity_key}"
        )
    if len(effective) != 1:
        refs = ",".join(sorted(item.authority_ref for item in effective))
        raise WorkActivityAuthorityError(
            f"ambiguous effective labor standards for {tenant_id}:{activity_key}: {refs}"
        )
    return effective[0]


def build_work_activity_demand_snapshot(
    request: WorkActivityDemandRequest,
    activities: Iterable[WorkActivityVersion],
    labor_standards: Iterable[ActivityLaborStandardVersion],
) -> WorkActivityDemandSnapshot:
    """Calculate interval demand from tenant-approved activity and labor authority.

    FIXED and EVENT work are represented as auditable occurrence counts; VOLUME
    work uses business units such as orders/items/pallets. All three use an exact
    approved seconds-per-unit standard. The engine never invents a default MHS.
    """

    activity_versions = tuple(activities)
    standard_versions = tuple(labor_standards)
    contributions: list[WorkActivityDemandContribution] = []
    required_man_hours = ZERO

    for signal in sorted(request.signals, key=lambda item: (item.activity_key, item.driver_key)):
        if signal.quantity == ZERO:
            continue
        activity = resolve_activity(
            activity_versions,
            tenant_id=request.tenant_id,
            activity_key=signal.activity_key,
            at=request.interval_start,
        )
        if signal.demand_mode != activity.demand_mode:
            raise WorkActivityAuthorityError(
                f"signal mode {signal.demand_mode} does not match activity mode {activity.demand_mode} "
                f"for {signal.activity_key}"
            )
        standard = resolve_activity_labor_standard(
            standard_versions,
            tenant_id=request.tenant_id,
            activity_key=signal.activity_key,
            at=request.interval_start,
        )
        man_hours = (signal.quantity * standard.seconds_per_unit * standard.people) / Decimal("3600")
        required_man_hours += man_hours
        contributions.append(
            WorkActivityDemandContribution(
                driver_key=signal.driver_key,
                activity_key=activity.activity_key,
                activity_name=activity.display_name,
                category=activity.category,
                unit_key=activity.unit_key,
                demand_mode=activity.demand_mode,
                quantity=signal.quantity,
                source_ref=signal.source_ref,
                activity_authority_ref=activity.authority_ref,
                labor_standard_ref=standard.authority_ref,
                labor_standard_source_ref=standard.source_ref,
                seconds_per_unit=standard.seconds_per_unit,
                people=standard.people,
                man_hours=man_hours,
                required_skill_keys=activity.required_skill_keys,
                required_certification_keys=activity.required_certification_keys,
                required_equipment_keys=activity.required_equipment_keys,
                safety_tags=activity.safety_tags,
            )
        )

    interval_hours = Decimal(request.interval_minutes) / Decimal("60")
    required_people = required_man_hours / interval_hours
    activity_refs = tuple(sorted({item.activity_authority_ref for item in contributions}))
    labor_refs = tuple(sorted({item.labor_standard_ref for item in contributions}))
    canonical_contributions = [item.canonical() for item in contributions]
    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "interval_start": request.interval_start.isoformat(),
        "interval_minutes": request.interval_minutes,
        "model_version": request.model_version,
        "activity_authority_refs": list(activity_refs),
        "labor_standard_refs": list(labor_refs),
        "contributions": canonical_contributions,
    }
    input_fingerprint = _canonical_hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "required_man_hours": _decimal_text(required_man_hours),
        "required_people": _decimal_text(required_people),
    }
    snapshot_fingerprint = _canonical_hash(output_payload)

    return WorkActivityDemandSnapshot(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        interval_start=request.interval_start,
        interval_minutes=request.interval_minutes,
        model_version=request.model_version,
        input_fingerprint=input_fingerprint,
        snapshot_fingerprint=snapshot_fingerprint,
        required_man_hours=required_man_hours,
        required_people=required_people,
        contributions=tuple(contributions),
        activity_authority_refs=activity_refs,
        labor_standard_refs=labor_refs,
    )
