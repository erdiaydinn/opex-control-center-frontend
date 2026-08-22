import pytest

from app.commercial_intelligence import (
    CommercialPerformanceInput,
    PromotionIncrementalityInput,
    calculate_commercial_performance,
    calculate_promotion_incrementality,
)


def test_commercial_performance_separates_gross_sales_from_net_revenue():
    result = calculate_commercial_performance(
        CommercialPerformanceInput(
            orders=100,
            gross_sales=10_000,
            discounts=1_000,
            refunds=500,
            variable_cost=5_000,
            customers=80,
        )
    )

    assert result.net_revenue == 8_500
    assert result.average_order_value == 85
    assert result.net_revenue_per_customer == 106.25
    assert result.discount_rate == 0.10
    assert result.refund_value_rate == 0.05
    assert result.contribution_profit == 3_500


def test_zero_orders_or_customers_return_unknown_ratios_not_fabricated_values():
    result = calculate_commercial_performance(
        CommercialPerformanceInput(
            orders=0,
            gross_sales=0,
            customers=0,
        )
    )

    assert result.average_order_value is None
    assert result.net_revenue_per_customer is None
    assert result.discount_rate is None
    assert result.contribution_margin is None


def test_commercial_deductions_cannot_exceed_gross_sales():
    with pytest.raises(ValueError, match="commercial_deductions_exceed_gross_sales"):
        CommercialPerformanceInput(
            orders=10,
            gross_sales=100,
            discounts=80,
            refunds=30,
        )


def test_matched_control_promo_incrementality_is_deterministic_and_non_causal():
    result = calculate_promotion_incrementality(
        PromotionIncrementalityInput(
            treatment_orders_before=1_000,
            treatment_orders_during=1_300,
            control_orders_before=1_000,
            control_orders_during=1_050,
            treatment_revenue_before=100_000,
            treatment_revenue_during=132_000,
            control_revenue_before=100_000,
            control_revenue_during=104_000,
            promotion_cost=10_000,
            evidence_refs=("commercial://campaign", "ops://matched-control"),
        )
    )

    assert result.incremental_orders == 250
    assert result.incremental_orders_pct_vs_treatment_baseline == 25
    assert result.incremental_revenue == 28_000
    assert result.net_incremental_value_after_promotion_cost == 18_000
    assert result.promotion_roi == 1.8
    assert result.causality_proven is False
