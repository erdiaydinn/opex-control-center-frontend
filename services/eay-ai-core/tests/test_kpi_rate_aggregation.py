from decimal import Decimal

import pytest

from app.kpi_rate_aggregation import (
    RateAggregationContract,
    aggregate_rate,
    reject_average_of_preaggregated_rates,
)


def otp_contract(**kwargs):
    data = {
        "metric": "otp",
        "numerator_field": "late_prep_orders",
        "denominator_field": "eligible_orders",
        "aggregation_kind": "complement_ratio_of_sums",
    }
    data.update(kwargs)
    return RateAggregationContract(**data)


def test_otp_uses_global_denominator_not_average_of_store_percentages():
    rows = [
        {"late_prep_orders": 1, "eligible_orders": 10},
        {"late_prep_orders": 50, "eligible_orders": 100},
    ]
    result = aggregate_rate(rows, contract=otp_contract())
    assert result == Decimal("100") - (Decimal("51") * Decimal("100") / Decimal("110"))
    assert result != Decimal("70")


def test_ratio_of_sums_supports_direct_rate_metrics():
    result = aggregate_rate(
        [
            {"defect_orders": 2, "eligible_orders": 20},
            {"defect_orders": 3, "eligible_orders": 80},
        ],
        contract=RateAggregationContract(
            metric="defect_rate",
            numerator_field="defect_orders",
            denominator_field="eligible_orders",
            aggregation_kind="ratio_of_sums",
        ),
    )
    assert result == Decimal("5")


def test_rate_aggregation_rejects_zero_denominator():
    with pytest.raises(ValueError, match="rate_aggregation_zero_denominator"):
        aggregate_rate(
            [{"late_prep_orders": 0, "eligible_orders": 0}],
            contract=otp_contract(),
        )


def test_rate_aggregation_rejects_impossible_row_counts():
    with pytest.raises(ValueError, match="rate_aggregation_numerator_exceeds_denominator"):
        aggregate_rate(
            [{"late_prep_orders": 11, "eligible_orders": 10}],
            contract=otp_contract(),
        )


def test_rate_aggregation_rejects_same_lineage_field():
    with pytest.raises(ValueError, match="numerator_denominator_must_differ"):
        aggregate_rate(
            [{"eligible_orders": 10}],
            contract=otp_contract(numerator_field="eligible_orders"),
        )


def test_average_of_preaggregated_rates_is_explicitly_forbidden():
    with pytest.raises(ValueError, match="average_of_rates_forbidden"):
        reject_average_of_preaggregated_rates([{"otp": 99.0}, {"otp": 70.0}])


def test_contract_fingerprint_changes_when_denominator_lineage_changes():
    a = otp_contract()
    b = otp_contract(denominator_field="completed_orders")
    assert len(a.fingerprint) == 64
    assert a.fingerprint != b.fingerprint
