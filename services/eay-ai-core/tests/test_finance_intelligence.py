import pytest

from app.finance_intelligence import (
    InvestmentCaseInput,
    ScenarioInput,
    UnitEconomicsInput,
    calculate_investment_case,
    calculate_unit_economics,
    compound_scenario,
)


def test_unit_economics_calculates_margin_contribution_and_break_even():
    result = calculate_unit_economics(
        UnitEconomicsInput(
            revenue=1000,
            cost_of_goods=600,
            variable_operating_cost=100,
            fixed_operating_cost=150,
            units=100,
        )
    )

    assert result.gross_profit == 400
    assert result.gross_margin_pct == 40.0
    assert result.contribution_profit == 300
    assert result.contribution_margin_pct == 30.0
    assert result.operating_profit_before_other_items == 150
    assert result.operating_margin_pct == 15.0
    assert result.revenue_per_unit == 10.0
    assert result.variable_cost_per_unit == 7.0
    assert result.contribution_per_unit == 3.0
    assert result.break_even_units == 50.0
    assert result.break_even_revenue == 500.0


def test_non_positive_unit_contribution_has_no_economic_break_even():
    result = calculate_unit_economics(
        UnitEconomicsInput(
            revenue=1000,
            cost_of_goods=900,
            variable_operating_cost=150,
            fixed_operating_cost=100,
            units=100,
        )
    )

    assert result.contribution_per_unit == -0.5
    assert result.break_even_units is None
    assert result.break_even_revenue is None


def test_investment_case_calculates_npv_irr_and_payback_deterministically():
    result = calculate_investment_case(
        InvestmentCaseInput(
            initial_investment=100,
            cash_flows=(60, 60),
            discount_rate=0.10,
        )
    )

    assert result.npv == pytest.approx(4.132231, abs=1e-6)
    assert result.irr == pytest.approx(0.1306623863, abs=1e-9)
    assert result.irr_pct == pytest.approx(13.066239, abs=1e-6)
    assert result.simple_payback_period == pytest.approx(1.666667, abs=1e-6)
    assert result.discounted_payback_period is not None
    assert result.discounted_payback_period > result.simple_payback_period


def test_multiple_sign_change_cash_flows_do_not_claim_unique_irr():
    result = calculate_investment_case(
        InvestmentCaseInput(
            initial_investment=100,
            cash_flows=(230, -132),
            discount_rate=0.10,
        )
    )

    assert result.irr is None
    assert result.irr_pct is None


def test_compound_scenario_applies_shocks_in_sequence():
    result = compound_scenario(
        ScenarioInput(
            baseline=1000,
            shocks_pct={
                "wage_inflation": 20,
                "productivity_offset": -10,
            },
        )
    )

    assert result.ending_value == 1080.0
    assert result.absolute_change == 80.0
    assert result.total_change_pct == 8.0


def test_zero_revenue_or_zero_baseline_never_invents_percentage():
    unit = calculate_unit_economics(
        UnitEconomicsInput(
            revenue=0,
            cost_of_goods=0,
            variable_operating_cost=0,
            fixed_operating_cost=10,
            units=1,
        )
    )
    scenario = compound_scenario(ScenarioInput(baseline=0, shocks_pct={"change": 20}))

    assert unit.gross_margin_pct is None
    assert unit.contribution_margin_pct is None
    assert unit.operating_margin_pct is None
    assert scenario.total_change_pct is None
