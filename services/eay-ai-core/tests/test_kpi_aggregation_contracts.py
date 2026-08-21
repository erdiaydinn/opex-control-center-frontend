from decimal import Decimal

import pytest

from app.kpi_aggregation_contracts import (
    WeightedAverageContract,
    aggregate_duration,
    reject_unweighted_picker_day_average,
    validate_weighted_average_contract,
)


def test_order_grain_averages_directly():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="order",
        value_field="picking_seconds",
        weight_field=None,
        output_unit="seconds_per_order",
    )
    result = aggregate_duration(
        [{"picking_seconds": 60}, {"picking_seconds": 120}, {"picking_seconds": 180}],
        contract=contract,
    )
    assert result == Decimal("120")
    assert len(contract.fingerprint) == 64


def test_picker_day_requires_explicit_order_weight():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="picker_day",
        value_field="avg_picking_seconds",
        weight_field=None,
        output_unit="seconds_per_order",
    )
    with pytest.raises(ValueError, match="aggregation_weight_required_for_picker_day"):
        validate_weighted_average_contract(contract)


def test_picker_day_uses_weighted_average_not_average_of_averages():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="picker_day",
        value_field="avg_picking_seconds",
        weight_field="eligible_orders",
        output_unit="seconds_per_order",
    )
    rows = [
        {"avg_picking_seconds": 60, "eligible_orders": 100},
        {"avg_picking_seconds": 180, "eligible_orders": 10},
    ]
    result = aggregate_duration(rows, contract=contract)
    assert result == Decimal("7800") / Decimal("110")
    assert result != Decimal("120")


def test_zero_weight_picker_days_fail_closed():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="picker_day",
        value_field="avg_picking_seconds",
        weight_field="eligible_orders",
        output_unit="seconds_per_order",
    )
    with pytest.raises(ValueError, match="aggregation_zero_total_weight"):
        aggregate_duration(
            [{"avg_picking_seconds": 60, "eligible_orders": 0}],
            contract=contract,
        )


def test_unweighted_picker_day_path_is_explicitly_forbidden():
    with pytest.raises(ValueError, match="average_of_averages_forbidden"):
        reject_unweighted_picker_day_average([{"avg_picking_seconds": 100}])


def test_negative_weight_fails_closed():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="picker_day",
        value_field="avg_picking_seconds",
        weight_field="eligible_orders",
        output_unit="seconds_per_order",
    )
    with pytest.raises(ValueError, match="aggregation_negative:eligible_orders"):
        aggregate_duration(
            [{"avg_picking_seconds": 60, "eligible_orders": -1}],
            contract=contract,
        )


def test_event_grain_rejects_explicit_weight():
    contract = WeightedAverageContract(
        metric="picking",
        source_grain="event",
        value_field="duration_seconds",
        weight_field="count",
        output_unit="seconds_per_event",
    )
    with pytest.raises(ValueError, match="aggregation_event_weight_must_be_implicit"):
        validate_weighted_average_contract(contract)
