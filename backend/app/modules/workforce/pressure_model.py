"""Auditable depot-pressure interpretation layered on canonical demand truth.

This model does not replace the supplied scheduling demand calculation. It consumes
required man-hours and compares them with effective capacity plus normalized
operational strain signals. Company-specific KPI definitions and thresholds belong
in tenant business semantics, not in this generic model.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

ZERO = Decimal("0")
ONE = Decimal("1")


class PressureBand(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class PressureCause(StrEnum):
    CAPACITY_DEFICIT = "capacity_deficit"
    PRODUCTIVITY_OR_PROCESS = "productivity_or_process"
    BACKLOG_CONGESTION = "backlog_congestion"
    MIXED = "mixed"
    STABLE = "stable"


@dataclass(frozen=True, slots=True)
class EffectiveCapacityInput:
    scheduled_man_hours: Decimal
    absence_man_hours: Decimal = ZERO
    unavailable_man_hours: Decimal = ZERO
    productivity_factor: Decimal = ONE

    def __post_init__(self) -> None:
        if self.scheduled_man_hours < ZERO:
            raise ValueError("scheduled_man_hours cannot be negative")
        if self.absence_man_hours < ZERO or self.unavailable_man_hours < ZERO:
            raise ValueError("capacity deductions cannot be negative")
        if not (ZERO < self.productivity_factor <= Decimal("1.5")):
            raise ValueError("productivity_factor must be in (0, 1.5]")
        if self.absence_man_hours + self.unavailable_man_hours > self.scheduled_man_hours:
            raise ValueError("capacity deductions cannot exceed scheduled capacity")

    @property
    def effective_man_hours(self) -> Decimal:
        available = self.scheduled_man_hours - self.absence_man_hours - self.unavailable_man_hours
        return available * self.productivity_factor


@dataclass(frozen=True, slots=True)
class OperationalStrain:
    backlog: Decimal = ZERO
    kpi: Decimal = ZERO

    def __post_init__(self) -> None:
        for name, value in (("backlog", self.backlog), ("kpi", self.kpi)):
            if value < ZERO or value > ONE:
                raise ValueError(f"{name} strain must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class DepotPressureResult:
    required_man_hours: Decimal
    effective_man_hours: Decimal
    capacity_gap_man_hours: Decimal
    coverage_ratio: Decimal
    pressure_score: Decimal
    band: PressureBand
    primary_cause: PressureCause
    manpower_shortage_detected: bool
    commentary_code: str


def _clamp(value: Decimal, minimum: Decimal = ZERO, maximum: Decimal = ONE) -> Decimal:
    return max(minimum, min(maximum, value))


def _pressure_band(score: Decimal) -> PressureBand:
    if score >= Decimal("85"):
        return PressureBand.CRITICAL
    if score >= Decimal("65"):
        return PressureBand.HIGH
    if score >= Decimal("40"):
        return PressureBand.MODERATE
    return PressureBand.LOW


def evaluate_depot_pressure(
    *,
    required_man_hours: Decimal,
    capacity: EffectiveCapacityInput,
    strain: OperationalStrain | None = None,
) -> DepotPressureResult:
    if required_man_hours < ZERO:
        raise ValueError("required_man_hours cannot be negative")
    strain = strain or OperationalStrain()
    effective = capacity.effective_man_hours
    gap = required_man_hours - effective
    shortage = gap > ZERO

    if required_man_hours == ZERO:
        coverage = ONE if effective >= ZERO else ZERO
        deficit_ratio = ZERO
    else:
        coverage = effective / required_man_hours
        deficit_ratio = _clamp(gap / required_man_hours)

    score_fraction = (
        Decimal("0.60") * deficit_ratio
        + Decimal("0.20") * strain.backlog
        + Decimal("0.20") * strain.kpi
    )
    score = (score_fraction * Decimal("100")).quantize(Decimal("0.1"))

    if shortage and (strain.backlog >= Decimal("0.5") or strain.kpi >= Decimal("0.5")):
        cause = PressureCause.MIXED
        commentary = "capacity_deficit_with_operational_strain"
    elif shortage:
        cause = PressureCause.CAPACITY_DEFICIT
        commentary = "capacity_deficit_detected"
    elif strain.backlog >= Decimal("0.6") and strain.kpi >= Decimal("0.6"):
        cause = PressureCause.MIXED
        commentary = "capacity_sufficient_investigate_backlog_and_process"
    elif strain.backlog >= Decimal("0.6"):
        cause = PressureCause.BACKLOG_CONGESTION
        commentary = "capacity_sufficient_backlog_congestion_detected"
    elif strain.kpi >= Decimal("0.6"):
        cause = PressureCause.PRODUCTIVITY_OR_PROCESS
        commentary = "capacity_sufficient_do_not_add_labor_investigate_process"
    else:
        cause = PressureCause.STABLE
        commentary = "capacity_and_operational_signals_stable"

    return DepotPressureResult(
        required_man_hours=required_man_hours,
        effective_man_hours=effective,
        capacity_gap_man_hours=gap,
        coverage_ratio=coverage,
        pressure_score=score,
        band=_pressure_band(score),
        primary_cause=cause,
        manpower_shortage_detected=shortage,
        commentary_code=commentary,
    )
