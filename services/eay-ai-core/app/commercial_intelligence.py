"""Deterministic sales/commercial primitives for EAY Jarvis.

Commercial answers should separate arithmetic from narrative. This module
calculates net revenue/unit economics and matched-control promotion lift without
allowing the LLM to invent ratios or causal proof.
"""

from __future__ import annotations

from math import isfinite

from pydantic import BaseModel, Field, model_validator

COMMERCIAL_INTELLIGENCE_CONTRACT = "eay-commercial-intelligence-v1"


def _finite_nonnegative(value: float, field: str) -> float:
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError(f"{field}_must_be_finite_nonnegative")
    return number


def _ratio(numerator: float, denominator: float) -> float | None:
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


class CommercialPerformanceInput(BaseModel):
    orders: float = Field(ge=0.0)
    gross_sales: float = Field(ge=0.0)
    discounts: float = Field(default=0.0, ge=0.0)
    refunds: float = Field(default=0.0, ge=0.0)
    variable_cost: float = Field(default=0.0, ge=0.0)
    customers: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_values(self) -> "CommercialPerformanceInput":
        for field in (
            "orders",
            "gross_sales",
            "discounts",
            "refunds",
            "variable_cost",
            "customers",
        ):
            _finite_nonnegative(getattr(self, field), field)
        if self.discounts + self.refunds > self.gross_sales:
            raise ValueError("commercial_deductions_exceed_gross_sales")
        return self


class CommercialPerformanceResult(BaseModel):
    contract: str = COMMERCIAL_INTELLIGENCE_CONTRACT
    net_revenue: float
    average_order_value: float | None
    net_revenue_per_customer: float | None
    discount_rate: float | None
    refund_value_rate: float | None
    contribution_profit: float
    contribution_margin: float | None


def calculate_commercial_performance(payload: CommercialPerformanceInput) -> CommercialPerformanceResult:
    net_revenue = payload.gross_sales - payload.discounts - payload.refunds
    contribution_profit = net_revenue - payload.variable_cost
    return CommercialPerformanceResult(
        net_revenue=round(net_revenue, 6),
        average_order_value=(round(net_revenue / payload.orders, 6) if payload.orders else None),
        net_revenue_per_customer=(
            round(net_revenue / payload.customers, 6) if payload.customers else None
        ),
        discount_rate=_ratio(payload.discounts, payload.gross_sales),
        refund_value_rate=_ratio(payload.refunds, payload.gross_sales),
        contribution_profit=round(contribution_profit, 6),
        contribution_margin=_ratio(contribution_profit, net_revenue),
    )


class PromotionIncrementalityInput(BaseModel):
    treatment_orders_before: float = Field(ge=0.0)
    treatment_orders_during: float = Field(ge=0.0)
    control_orders_before: float = Field(ge=0.0)
    control_orders_during: float = Field(ge=0.0)
    treatment_revenue_before: float = Field(ge=0.0)
    treatment_revenue_during: float = Field(ge=0.0)
    control_revenue_before: float = Field(ge=0.0)
    control_revenue_during: float = Field(ge=0.0)
    promotion_cost: float = Field(default=0.0, ge=0.0)
    evidence_refs: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_finite(self) -> "PromotionIncrementalityInput":
        for field in (
            "treatment_orders_before",
            "treatment_orders_during",
            "control_orders_before",
            "control_orders_during",
            "treatment_revenue_before",
            "treatment_revenue_during",
            "control_revenue_before",
            "control_revenue_during",
            "promotion_cost",
        ):
            _finite_nonnegative(getattr(self, field), field)
        return self


class PromotionIncrementalityResult(BaseModel):
    contract: str = COMMERCIAL_INTELLIGENCE_CONTRACT
    incremental_orders: float
    incremental_orders_pct_vs_treatment_baseline: float | None
    incremental_revenue: float
    incremental_revenue_pct_vs_treatment_baseline: float | None
    net_incremental_value_after_promotion_cost: float
    promotion_roi: float | None
    causality_proven: bool = False
    evidence_refs: tuple[str, ...]
    warnings: tuple[str, ...] = ("matched_control_incrementality_is_not_randomized_causal_proof",)


def calculate_promotion_incrementality(
    payload: PromotionIncrementalityInput,
) -> PromotionIncrementalityResult:
    treatment_order_change = payload.treatment_orders_during - payload.treatment_orders_before
    control_order_change = payload.control_orders_during - payload.control_orders_before
    incremental_orders = treatment_order_change - control_order_change

    treatment_revenue_change = payload.treatment_revenue_during - payload.treatment_revenue_before
    control_revenue_change = payload.control_revenue_during - payload.control_revenue_before
    incremental_revenue = treatment_revenue_change - control_revenue_change
    net_incremental_value = incremental_revenue - payload.promotion_cost

    return PromotionIncrementalityResult(
        incremental_orders=round(incremental_orders, 6),
        incremental_orders_pct_vs_treatment_baseline=(
            round(incremental_orders * 100.0 / payload.treatment_orders_before, 6)
            if payload.treatment_orders_before
            else None
        ),
        incremental_revenue=round(incremental_revenue, 6),
        incremental_revenue_pct_vs_treatment_baseline=(
            round(incremental_revenue * 100.0 / payload.treatment_revenue_before, 6)
            if payload.treatment_revenue_before
            else None
        ),
        net_incremental_value_after_promotion_cost=round(net_incremental_value, 6),
        promotion_roi=(
            round(net_incremental_value / payload.promotion_cost, 6)
            if payload.promotion_cost
            else None
        ),
        evidence_refs=payload.evidence_refs,
    )
