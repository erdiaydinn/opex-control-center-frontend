from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class PlanningScenarioCreate(BaseModel):
    plan_id: UUID
    name: str = Field(min_length=2, max_length=200)
    scenario_type: Literal["DRIVER_PLAN", "ROLLING_FORECAST", "WHAT_IF"]
    as_of: date
    parent_scenario_id: UUID | None = None
    version: int = Field(default=1, ge=1)


class PlanningAssumptionCreate(BaseModel):
    assumption_key: str = Field(min_length=1, max_length=160)
    assumption_value: str | int | float | bool
    unit: str | None = Field(default=None, max_length=40)
    source: str = Field(min_length=1, max_length=255)
    effective_on: date | None = None


class PlanningDriverLineCreate(BaseModel):
    budget_line_id: UUID
    fiscal_period_id: UUID
    cost_center_id: UUID
    driver_key: str = Field(min_length=1, max_length=160)
    quantity: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    rate: Decimal = Field(ge=0, max_digits=18, decimal_places=4)
    unit: str | None = Field(default=None, max_length=40)
    provenance: dict[str, object] = Field(default_factory=dict)


class PlanningAllocationCreate(BaseModel):
    source_budget_line_id: UUID
    target_budget_line_id: UUID
    target_fiscal_period_id: UUID
    target_cost_center_id: UUID
    weight: Decimal = Field(gt=0, le=1, max_digits=9, decimal_places=6)
    basis: str = Field(min_length=1, max_length=160)
    provenance: dict[str, object] = Field(default_factory=dict)
