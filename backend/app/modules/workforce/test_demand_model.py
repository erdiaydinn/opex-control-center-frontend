from decimal import Decimal

import pytest

from app.modules.workforce.demand_model import (
    DemandOverheads,
    PickerDemandComponents,
    compute_hourly_picker_demand,
    task_man_hours,
)


def test_composes_all_operational_demand_and_overheads() -> None:
    components = PickerDemandComponents(
        picking=Decimal("1.2"),
        packing=Decimal("0.5"),
        handoff=Decimal("0.2"),
        receiving_po=Decimal("0.3"),
        receiving_st=Decimal("0.1"),
        putaway=Decimal("0.4"),
        cycle_count=Decimal("0.2"),
        expiry_check=Decimal("0.1"),
        quality_check=Decimal("0.1"),
        replenishment=Decimal("0.3"),
    )
    result = compute_hourly_picker_demand(
        components,
        DemandOverheads(
            fatigue_factor=Decimal("0.05"),
            buffer_tasks=Decimal("0.10"),
            break_time=Decimal("0.05"),
        ),
    )

    assert result.base_man_hours == Decimal("3.4")
    assert result.overhead_man_hours == Decimal("0.680")
    assert result.total_man_hours == Decimal("4.080")


def test_receiving_style_formula_is_auditable() -> None:
    assert task_man_hours(
        volume=Decimal("120"),
        seconds_per_unit=Decimal("30"),
    ) == Decimal("1")


def test_negative_demand_fails_closed() -> None:
    with pytest.raises(ValueError, match="picking"):
        PickerDemandComponents(picking=Decimal("-0.1"))


def test_invalid_overhead_fails_closed() -> None:
    with pytest.raises(ValueError, match="break_time"):
        DemandOverheads(break_time=Decimal("1"))


def test_zero_or_negative_people_fails_closed() -> None:
    with pytest.raises(ValueError):
        task_man_hours(
            volume=Decimal("10"),
            seconds_per_unit=Decimal("30"),
            people=Decimal("0"),
        )
