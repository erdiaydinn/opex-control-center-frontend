"""Deterministic finance primitives for EAY Jarvis.

Financial arithmetic must not be invented by an LLM. This module provides a
small, auditable calculation boundary for executive analysis. It performs no
data fetching and accepts only explicit numeric inputs supplied through a
governed caller. The model may explain results but must not replace them.
"""

from __future__ import annotations

from math import isfinite

from pydantic import BaseModel, Field, model_validator

FINANCE_INTELLIGENCE_CONTRACT = "eay-finance-intelligence-v1"


class FinanceCalculationError(ValueError):
    pass


def _finite(value: float, *, field: str) -> float:
    number = float(value)
    if not isfinite(number):
        raise FinanceCalculationError(f"{field}_must_be_finite")
    return number


def _pct(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator * 100.0 / denominator, 6)


class UnitEconomicsInput(BaseModel):
    revenue: float
    cost_of_goods: float
    variable_operating_cost: float = 0.0
    fixed_operating_cost: float = 0.0
    units: float = Field(gt=0)

    @model_validator(mode="after")
    def validate_finite(self) -> "UnitEconomicsInput":
        for field in (
            "revenue",
            "cost_of_goods",
            "variable_operating_cost",
            "fixed_operating_cost",
            "units",
        ):
            _finite(getattr(self, field), field=field)
        return self


class UnitEconomicsResult(BaseModel):
    contract: str = FINANCE_INTELLIGENCE_CONTRACT
    revenue: float
    gross_profit: float
    gross_margin_pct: float | None
    contribution_profit: float
    contribution_margin_pct: float | None
    operating_profit_before_other_items: float
    operating_margin_pct: float | None
    revenue_per_unit: float
    variable_cost_per_unit: float
    contribution_per_unit: float
    break_even_units: float | None
    break_even_revenue: float | None


def calculate_unit_economics(payload: UnitEconomicsInput) -> UnitEconomicsResult:
    gross_profit = payload.revenue - payload.cost_of_goods
    contribution_profit = gross_profit - payload.variable_operating_cost
    operating_profit = contribution_profit - payload.fixed_operating_cost
    revenue_per_unit = payload.revenue / payload.units
    variable_cost_per_unit = (
        payload.cost_of_goods + payload.variable_operating_cost
    ) / payload.units
    contribution_per_unit = revenue_per_unit - variable_cost_per_unit

    if contribution_per_unit <= 0:
        break_even_units = None
        break_even_revenue = None
    else:
        break_even_units = payload.fixed_operating_cost / contribution_per_unit
        break_even_revenue = break_even_units * revenue_per_unit

    return UnitEconomicsResult(
        revenue=round(payload.revenue, 6),
        gross_profit=round(gross_profit, 6),
        gross_margin_pct=_pct(gross_profit, payload.revenue),
        contribution_profit=round(contribution_profit, 6),
        contribution_margin_pct=_pct(contribution_profit, payload.revenue),
        operating_profit_before_other_items=round(operating_profit, 6),
        operating_margin_pct=_pct(operating_profit, payload.revenue),
        revenue_per_unit=round(revenue_per_unit, 6),
        variable_cost_per_unit=round(variable_cost_per_unit, 6),
        contribution_per_unit=round(contribution_per_unit, 6),
        break_even_units=round(break_even_units, 6) if break_even_units is not None else None,
        break_even_revenue=round(break_even_revenue, 6) if break_even_revenue is not None else None,
    )


class InvestmentCaseInput(BaseModel):
    initial_investment: float = Field(gt=0)
    cash_flows: tuple[float, ...] = Field(min_length=1)
    discount_rate: float = Field(gt=-1.0)

    @model_validator(mode="after")
    def validate_finite(self) -> "InvestmentCaseInput":
        _finite(self.initial_investment, field="initial_investment")
        _finite(self.discount_rate, field="discount_rate")
        for index, value in enumerate(self.cash_flows, start=1):
            _finite(value, field=f"cash_flow_{index}")
        return self


class InvestmentCaseResult(BaseModel):
    contract: str = FINANCE_INTELLIGENCE_CONTRACT
    npv: float
    irr: float | None
    irr_pct: float | None
    simple_payback_period: float | None
    discounted_payback_period: float | None
    total_undiscounted_cash_flow: float
    value_creation_vs_initial_investment: float


def _npv(initial_investment: float, cash_flows: tuple[float, ...], rate: float) -> float:
    if rate <= -1.0:
        raise FinanceCalculationError("discount_rate_must_be_greater_than_minus_one")
    return -initial_investment + sum(
        cash_flow / ((1.0 + rate) ** period)
        for period, cash_flow in enumerate(cash_flows, start=1)
    )


def _payback(initial_investment: float, cash_flows: tuple[float, ...]) -> float | None:
    recovered = 0.0
    for period, cash_flow in enumerate(cash_flows, start=1):
        prior = recovered
        recovered += cash_flow
        if recovered >= initial_investment and cash_flow > 0:
            remaining_before_period = initial_investment - prior
            fraction = max(0.0, min(remaining_before_period / cash_flow, 1.0))
            return (period - 1) + fraction
    return None


def _discounted_payback(
    initial_investment: float,
    cash_flows: tuple[float, ...],
    rate: float,
) -> float | None:
    discounted = tuple(
        cash_flow / ((1.0 + rate) ** period)
        for period, cash_flow in enumerate(cash_flows, start=1)
    )
    return _payback(initial_investment, discounted)


def _irr(
    initial_investment: float,
    cash_flows: tuple[float, ...],
    *,
    low: float = -0.9999,
    high: float = 10.0,
    tolerance: float = 1e-10,
    iterations: int = 256,
) -> float | None:
    """Return one economically meaningful IRR root when a bracket exists.

    Multiple-sign-change cash-flow streams can have multiple IRRs. To avoid
    pretending a unique answer exists, this boundary returns None when the full
    cash-flow sequence changes sign more than once.
    """

    stream = (-initial_investment, *cash_flows)
    non_zero = [value for value in stream if value != 0]
    sign_changes = sum(
        1 for left, right in zip(non_zero, non_zero[1:]) if (left > 0) != (right > 0)
    )
    if sign_changes != 1:
        return None

    f_low = _npv(initial_investment, cash_flows, low)
    f_high = _npv(initial_investment, cash_flows, high)
    while f_low * f_high > 0 and high < 1_000_000:
        high *= 2.0
        f_high = _npv(initial_investment, cash_flows, high)
    if f_low == 0:
        return low
    if f_high == 0:
        return high
    if f_low * f_high > 0:
        return None

    for _ in range(iterations):
        mid = (low + high) / 2.0
        f_mid = _npv(initial_investment, cash_flows, mid)
        if abs(f_mid) <= tolerance:
            return mid
        if f_low * f_mid <= 0:
            high = mid
            f_high = f_mid
        else:
            low = mid
            f_low = f_mid
    return (low + high) / 2.0


def calculate_investment_case(payload: InvestmentCaseInput) -> InvestmentCaseResult:
    npv = _npv(payload.initial_investment, payload.cash_flows, payload.discount_rate)
    irr = _irr(payload.initial_investment, payload.cash_flows)
    payback = _payback(payload.initial_investment, payload.cash_flows)
    discounted_payback = _discounted_payback(
        payload.initial_investment,
        payload.cash_flows,
        payload.discount_rate,
    )
    total_cash = sum(payload.cash_flows)

    return InvestmentCaseResult(
        npv=round(npv, 6),
        irr=round(irr, 10) if irr is not None else None,
        irr_pct=round(irr * 100.0, 6) if irr is not None else None,
        simple_payback_period=round(payback, 6) if payback is not None else None,
        discounted_payback_period=(
            round(discounted_payback, 6) if discounted_payback is not None else None
        ),
        total_undiscounted_cash_flow=round(total_cash, 6),
        value_creation_vs_initial_investment=round(total_cash - payload.initial_investment, 6),
    )


class ScenarioInput(BaseModel):
    baseline: float
    shocks_pct: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_finite(self) -> "ScenarioInput":
        _finite(self.baseline, field="baseline")
        for key, value in self.shocks_pct.items():
            if not key.strip():
                raise FinanceCalculationError("scenario_shock_name_required")
            _finite(value, field=f"shock_{key}")
        return self


class ScenarioResult(BaseModel):
    contract: str = FINANCE_INTELLIGENCE_CONTRACT
    baseline: float
    ending_value: float
    absolute_change: float
    total_change_pct: float | None
    applied_shocks_pct: dict[str, float]


def compound_scenario(payload: ScenarioInput) -> ScenarioResult:
    value = payload.baseline
    for shock in payload.shocks_pct.values():
        value *= 1.0 + (shock / 100.0)
    absolute_change = value - payload.baseline
    return ScenarioResult(
        baseline=round(payload.baseline, 6),
        ending_value=round(value, 6),
        absolute_change=round(absolute_change, 6),
        total_change_pct=_pct(absolute_change, payload.baseline),
        applied_shocks_pct=dict(payload.shocks_pct),
    )
