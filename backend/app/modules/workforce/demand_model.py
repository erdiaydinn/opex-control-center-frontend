"""Canonical picker man-hour demand composition for Workforce scheduling.

This module intentionally models demand truth separately from employee assignment.
It preserves the supplied global scheduling rule set: operational activities are
converted to hourly man-hours first; shift optimization consumes that demand later.
No employee, legal, preference, skill, cost, or availability constraint is inferred here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping


ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PickerDemandComponents:
    """Hourly man-hours by canonical picker activity.

    Values are hours of labor required in the target hour. Negative values are
    invalid because demand components are workload, not adjustments.
    """

    picking: Decimal = ZERO
    packing: Decimal = ZERO
    handoff: Decimal = ZERO
    receiving_po: Decimal = ZERO
    receiving_st: Decimal = ZERO
    putaway: Decimal = ZERO
    cycle_count: Decimal = ZERO
    expiry_check: Decimal = ZERO
    quality_check: Decimal = ZERO
    replenishment: Decimal = ZERO
    outbound_transfer: Decimal = ZERO
    returned_order_putaway: Decimal = ZERO

    def __post_init__(self) -> None:
        for name, value in self.as_mapping().items():
            if value < ZERO:
                raise ValueError(f"{name} demand cannot be negative")

    def as_mapping(self) -> Mapping[str, Decimal]:
        return {
            "picking": self.picking,
            "packing": self.packing,
            "handoff": self.handoff,
            "receiving_po": self.receiving_po,
            "receiving_st": self.receiving_st,
            "putaway": self.putaway,
            "cycle_count": self.cycle_count,
            "expiry_check": self.expiry_check,
            "quality_check": self.quality_check,
            "replenishment": self.replenishment,
            "outbound_transfer": self.outbound_transfer,
            "returned_order_putaway": self.returned_order_putaway,
        }

    @property
    def base_man_hours(self) -> Decimal:
        return sum(self.as_mapping().values(), ZERO)


@dataclass(frozen=True, slots=True)
class DemandOverheads:
    """Non-task labor overheads applied to base operational demand.

    The supplied source separates fatigue, buffer tasks and break time from daily
    activity MHS. Percentages are represented as fractions: 0.10 == 10%.
    """

    fatigue_factor: Decimal = ZERO
    buffer_tasks: Decimal = ZERO
    break_time: Decimal = ZERO

    def __post_init__(self) -> None:
        for name, value in (
            ("fatigue_factor", self.fatigue_factor),
            ("buffer_tasks", self.buffer_tasks),
            ("break_time", self.break_time),
        ):
            if value < ZERO or value >= Decimal("1"):
                raise ValueError(f"{name} must be in [0, 1)")

    @property
    def combined_fraction(self) -> Decimal:
        return self.fatigue_factor + self.buffer_tasks + self.break_time


@dataclass(frozen=True, slots=True)
class HourlyPickerDemand:
    base_man_hours: Decimal
    overhead_man_hours: Decimal
    total_man_hours: Decimal


def compute_hourly_picker_demand(
    components: PickerDemandComponents,
    overheads: DemandOverheads | None = None,
) -> HourlyPickerDemand:
    """Return the auditable hourly demand consumed by shift optimization.

    Overheads are additive percentages of base workload. The calculation remains
    deliberately deterministic and contains no forecasting or optimization logic.
    """

    overheads = overheads or DemandOverheads()
    base = components.base_man_hours
    extra = base * overheads.combined_fraction
    return HourlyPickerDemand(
        base_man_hours=base,
        overhead_man_hours=extra,
        total_man_hours=base + extra,
    )


def task_man_hours(*, volume: Decimal, seconds_per_unit: Decimal, people: Decimal = Decimal("1")) -> Decimal:
    """Convert volume × effort × people into man-hours.

    Mirrors receiving/putaway/cycle-count style formulas without embedding a
    particular data source or market assumption.
    """

    if volume < ZERO or seconds_per_unit < ZERO or people <= ZERO:
        raise ValueError("volume/effort must be non-negative and people must be positive")
    return (volume * seconds_per_unit * people) / Decimal("3600")
