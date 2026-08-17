"""Demand Pressure Index and root-cause authority for roadmap 13/60.

DPI deliberately composes the governed demand (11/60) and effective-capacity
(12/60) truths. Bad operational KPIs are not sufficient evidence of a manpower
shortage. Capacity, skill feasibility and KPI provenance remain separate inputs
so downstream optimization cannot justify extra people from KPI degradation
alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
import hashlib
import json

ZERO = Decimal("0")
ONE = Decimal("1")


class DpiAuthorityError(ValueError):
    """Raised when pressure/root cause cannot be resolved without guessing."""


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise DpiAuthorityError(f"{field_name} must be timezone-aware")


def _decimal_text(value: Decimal) -> str:
    if value == ZERO:
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _hash(value: object) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class KpiObservation:
    key: str
    actual: Decimal
    target: Decimal
    direction: str
    source_ref: str

    def __post_init__(self) -> None:
        if not self.key.strip():
            raise DpiAuthorityError("KPI key is required")
        if self.direction not in {"lower_is_better", "higher_is_better"}:
            raise DpiAuthorityError("KPI direction is unsupported")
        if not self.source_ref.strip():
            raise DpiAuthorityError("KPI observation requires source_ref provenance")

    @property
    def is_bad(self) -> bool:
        if self.direction == "lower_is_better":
            return self.actual > self.target
        return self.actual < self.target

    def canonical(self) -> dict[str, str | bool]:
        return {
            "key": self.key,
            "actual": _decimal_text(self.actual),
            "target": _decimal_text(self.target),
            "direction": self.direction,
            "source_ref": self.source_ref,
            "is_bad": self.is_bad,
        }


@dataclass(frozen=True, slots=True)
class DpiRequest:
    tenant_id: str
    location_id: str
    interval_start: datetime
    model_version: str
    demand_snapshot_fingerprint: str
    capacity_snapshot_fingerprint: str
    required_man_hours: Decimal
    effective_man_hours: Decimal
    skill_deficit_man_hours: Decimal
    kpis: tuple[KpiObservation, ...]
    demand_source_ref: str
    capacity_source_ref: str
    capacity_tolerance_man_hours: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        if not self.tenant_id.strip() or not self.location_id.strip():
            raise DpiAuthorityError("tenant_id and location_id are required")
        _aware(self.interval_start, "interval_start")
        if not self.model_version.strip():
            raise DpiAuthorityError("model_version is required")
        for value, name in (
            (self.required_man_hours, "required_man_hours"),
            (self.effective_man_hours, "effective_man_hours"),
            (self.skill_deficit_man_hours, "skill_deficit_man_hours"),
            (self.capacity_tolerance_man_hours, "capacity_tolerance_man_hours"),
        ):
            if value < ZERO:
                raise DpiAuthorityError(f"{name} cannot be negative")
        for fingerprint, name in (
            (self.demand_snapshot_fingerprint, "demand_snapshot_fingerprint"),
            (self.capacity_snapshot_fingerprint, "capacity_snapshot_fingerprint"),
        ):
            if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
                raise DpiAuthorityError(f"{name} must be lowercase SHA-256")
        if not self.demand_source_ref.strip() or not self.capacity_source_ref.strip():
            raise DpiAuthorityError("demand and capacity source refs are required")
        keys = [item.key for item in self.kpis]
        if len(keys) != len(set(keys)):
            raise DpiAuthorityError("KPI keys must be unique")


@dataclass(frozen=True, slots=True)
class DpiSnapshot:
    tenant_id: str
    location_id: str
    interval_start: datetime
    model_version: str
    input_fingerprint: str
    snapshot_fingerprint: str
    demand_pressure_index: Decimal
    capacity_gap_man_hours: Decimal
    capacity_sufficient: bool
    kpi_bad: bool
    bad_kpi_keys: tuple[str, ...]
    manpower_shortage: bool
    root_cause: str
    automatic_extra_people_permitted: bool
    staffing_review_required: bool
    explanation: tuple[str, ...]
    demand_snapshot_fingerprint: str
    capacity_snapshot_fingerprint: str

    def as_record(self) -> dict[str, object]:
        return {
            "tenant_id": self.tenant_id,
            "location_id": self.location_id,
            "interval_start": self.interval_start.isoformat(),
            "model_version": self.model_version,
            "input_fingerprint": self.input_fingerprint,
            "snapshot_fingerprint": self.snapshot_fingerprint,
            "demand_pressure_index": _decimal_text(self.demand_pressure_index),
            "capacity_gap_man_hours": _decimal_text(self.capacity_gap_man_hours),
            "capacity_sufficient": self.capacity_sufficient,
            "kpi_bad": self.kpi_bad,
            "bad_kpi_keys": list(self.bad_kpi_keys),
            "manpower_shortage": self.manpower_shortage,
            "root_cause": self.root_cause,
            "automatic_extra_people_permitted": self.automatic_extra_people_permitted,
            "staffing_review_required": self.staffing_review_required,
            "explanation": list(self.explanation),
            "demand_snapshot_fingerprint": self.demand_snapshot_fingerprint,
            "capacity_snapshot_fingerprint": self.capacity_snapshot_fingerprint,
        }


def build_dpi_snapshot(request: DpiRequest) -> DpiSnapshot:
    gap = max(request.required_man_hours - request.effective_man_hours, ZERO)
    capacity_sufficient = gap <= request.capacity_tolerance_man_hours
    if request.required_man_hours == ZERO:
        dpi = ZERO
    elif request.effective_man_hours == ZERO:
        # Explicit bounded sentinel for total capacity outage; avoids Infinity in
        # persistence/API while remaining strictly greater than the pressure threshold.
        dpi = Decimal("999")
    else:
        dpi = request.required_man_hours / request.effective_man_hours

    bad_kpis = tuple(sorted(item.key for item in request.kpis if item.is_bad))
    kpi_bad = bool(bad_kpis)

    if not capacity_sufficient and request.skill_deficit_man_hours > request.capacity_tolerance_man_hours:
        root_cause = "skill_mix_constraint"
        manpower_shortage = False
        staffing_review_required = True
        explanation = (
            "effective skill-feasible capacity is below required demand",
            "skill deficit exists, so generic headcount shortage is not proven",
        )
    elif not capacity_sufficient:
        root_cause = "manpower_capacity_shortage"
        manpower_shortage = True
        staffing_review_required = True
        explanation = (
            "effective capacity is below required demand beyond tolerance",
            "no material skill deficit explains the capacity gap",
        )
    elif kpi_bad:
        root_cause = "execution_or_process"
        manpower_shortage = False
        staffing_review_required = False
        explanation = (
            "effective capacity is sufficient for governed demand",
            "one or more KPIs are outside target, so manpower shortage is not supported",
        )
    else:
        root_cause = "no_pressure_signal"
        manpower_shortage = False
        staffing_review_required = False
        explanation = (
            "effective capacity covers governed demand",
            "observed KPIs are within target",
        )

    # Automatic staffing changes are never authorized by the classifier. Item 14+
    # may create a governed optimizer proposal, but execution requires its own gate.
    automatic_extra_people_permitted = False

    input_payload = {
        "tenant_id": request.tenant_id,
        "location_id": request.location_id,
        "interval_start": request.interval_start.isoformat(),
        "model_version": request.model_version,
        "demand_snapshot_fingerprint": request.demand_snapshot_fingerprint,
        "capacity_snapshot_fingerprint": request.capacity_snapshot_fingerprint,
        "required_man_hours": _decimal_text(request.required_man_hours),
        "effective_man_hours": _decimal_text(request.effective_man_hours),
        "skill_deficit_man_hours": _decimal_text(request.skill_deficit_man_hours),
        "capacity_tolerance_man_hours": _decimal_text(request.capacity_tolerance_man_hours),
        "demand_source_ref": request.demand_source_ref,
        "capacity_source_ref": request.capacity_source_ref,
        "kpis": [item.canonical() for item in sorted(request.kpis, key=lambda item: item.key)],
    }
    input_fingerprint = _hash(input_payload)
    output_payload = {
        **input_payload,
        "input_fingerprint": input_fingerprint,
        "demand_pressure_index": _decimal_text(dpi),
        "capacity_gap_man_hours": _decimal_text(gap),
        "capacity_sufficient": capacity_sufficient,
        "bad_kpi_keys": list(bad_kpis),
        "manpower_shortage": manpower_shortage,
        "root_cause": root_cause,
        "automatic_extra_people_permitted": automatic_extra_people_permitted,
        "staffing_review_required": staffing_review_required,
    }
    snapshot_fingerprint = _hash(output_payload)

    return DpiSnapshot(
        tenant_id=request.tenant_id,
        location_id=request.location_id,
        interval_start=request.interval_start,
        model_version=request.model_version,
        input_fingerprint=input_fingerprint,
        snapshot_fingerprint=snapshot_fingerprint,
        demand_pressure_index=dpi,
        capacity_gap_man_hours=gap,
        capacity_sufficient=capacity_sufficient,
        kpi_bad=kpi_bad,
        bad_kpi_keys=bad_kpis,
        manpower_shortage=manpower_shortage,
        root_cause=root_cause,
        automatic_extra_people_permitted=automatic_extra_people_permitted,
        staffing_review_required=staffing_review_required,
        explanation=explanation,
        demand_snapshot_fingerprint=request.demand_snapshot_fingerprint,
        capacity_snapshot_fingerprint=request.capacity_snapshot_fingerprint,
    )
