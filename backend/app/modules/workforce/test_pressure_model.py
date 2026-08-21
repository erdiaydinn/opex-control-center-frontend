from decimal import Decimal

import pytest

from app.modules.workforce.pressure_model import (
    EffectiveCapacityInput,
    OperationalStrain,
    PressureCause,
    evaluate_depot_pressure,
)


def test_capacity_shortage_is_explicit_and_auditable():
    result = evaluate_depot_pressure(
        required_man_hours=Decimal("12"),
        capacity=EffectiveCapacityInput(
            scheduled_man_hours=Decimal("12"),
            absence_man_hours=Decimal("2"),
            productivity_factor=Decimal("0.95"),
        ),
        strain=OperationalStrain(backlog=Decimal("0.2"), kpi=Decimal("0.2")),
    )
    assert result.manpower_shortage_detected is True
    assert result.capacity_gap_man_hours == Decimal("2.50")
    assert result.primary_cause is PressureCause.CAPACITY_DEFICIT


def test_bad_kpi_with_sufficient_capacity_does_not_recommend_more_labor():
    result = evaluate_depot_pressure(
        required_man_hours=Decimal("10"),
        capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("12")),
        strain=OperationalStrain(backlog=Decimal("0.2"), kpi=Decimal("0.9")),
    )
    assert result.manpower_shortage_detected is False
    assert result.primary_cause is PressureCause.PRODUCTIVITY_OR_PROCESS
    assert result.commentary_code == "capacity_sufficient_do_not_add_labor_investigate_process"


def test_backlog_pressure_is_distinct_from_capacity_shortage():
    result = evaluate_depot_pressure(
        required_man_hours=Decimal("8"),
        capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("9")),
        strain=OperationalStrain(backlog=Decimal("0.8"), kpi=Decimal("0.2")),
    )
    assert result.manpower_shortage_detected is False
    assert result.primary_cause is PressureCause.BACKLOG_CONGESTION


def test_capacity_and_kpi_strain_can_be_mixed():
    result = evaluate_depot_pressure(
        required_man_hours=Decimal("15"),
        capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("10")),
        strain=OperationalStrain(backlog=Decimal("0.8"), kpi=Decimal("0.8")),
    )
    assert result.primary_cause is PressureCause.MIXED
    assert result.manpower_shortage_detected is True


def test_invalid_capacity_deductions_fail_closed():
    with pytest.raises(ValueError, match="cannot exceed"):
        EffectiveCapacityInput(
            scheduled_man_hours=Decimal("8"),
            absence_man_hours=Decimal("9"),
        )


def test_company_kpi_signal_is_normalized_not_hardcoded_to_specific_metric():
    with pytest.raises(ValueError, match="kpi strain"):
        OperationalStrain(kpi=Decimal("1.1"))
