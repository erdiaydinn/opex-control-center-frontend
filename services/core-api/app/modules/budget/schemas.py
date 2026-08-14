from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _currency(value: str) -> str:
    normalized = value.strip().upper()
    if len(normalized) != 3 or not normalized.isalpha():
        raise ValueError("currency must be a 3-letter code")
    return normalized


class PlanCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    fiscal_year: int = Field(ge=2020, le=2200)
    base_currency: str = "TRY"
    _currency = field_validator("base_currency")(_currency)


class PeriodCreate(BaseModel):
    plan_id: UUID
    code: str = Field(min_length=1, max_length=40)
    starts_on: date
    ends_on: date


class CostCenterCreate(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=200)
    store_code: str | None = Field(default=None, max_length=80)


class BudgetLineCreate(BaseModel):
    plan_id: UUID
    fiscal_period_id: UUID
    cost_center_id: UUID
    category: str = Field(min_length=1, max_length=160)
    supplier_id: str | None = Field(default=None, max_length=120)
    supplier_name: str | None = Field(default=None, max_length=240)
    store_code: str | None = Field(default=None, max_length=80)
    budget_base_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)


class PurchaseRequestCreate(BaseModel):
    budget_line_id: UUID
    fiscal_period_id: UUID
    cost_center_id: UUID
    external_ref: str | None = Field(default=None, max_length=160)
    supplier_id: str | None = Field(default=None, max_length=120)
    supplier_name: str | None = Field(default=None, max_length=240)
    category: str = Field(min_length=1, max_length=160)
    store_code: str | None = Field(default=None, max_length=80)
    description: str = Field(min_length=3, max_length=2000)
    requested_base_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class ApprovalDecision(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3, max_length=2000)


class PurchaseOrderCreate(BaseModel):
    purchase_request_id: UUID
    external_id: str = Field(min_length=1, max_length=160)
    supplier_id: str = Field(min_length=1, max_length=120)
    supplier_name: str | None = Field(default=None, max_length=240)
    category: str = Field(min_length=1, max_length=160)
    store_code: str | None = Field(default=None, max_length=80)
    base_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class InvoiceCreate(BaseModel):
    purchase_order_id: UUID
    invoice_number: str = Field(min_length=1, max_length=160)
    supplier_id: str = Field(min_length=1, max_length=120)
    supplier_name: str | None = Field(default=None, max_length=240)
    category: str = Field(min_length=1, max_length=160)
    store_code: str | None = Field(default=None, max_length=80)
    invoice_date: date
    base_amount: Decimal = Field(gt=0, max_digits=18, decimal_places=2)


class ForecastCreate(BaseModel):
    budget_line_id: UUID
    fiscal_period_id: UUID
    cost_center_id: UUID
    forecast_base_amount: Decimal = Field(ge=0, max_digits=18, decimal_places=2)
    as_of: date


class ImportStage(BaseModel):
    source_system: Literal["ARIBA", "SAP", "BIGQUERY", "MANUAL"]
    entity_type: Literal["purchase_request", "purchase_order", "invoice", "forecast"]
    rows: list[dict[str, object]] = Field(min_length=1, max_length=5000)


class ReconciliationResolve(BaseModel):
    decision: Literal["ACCEPT_OBSERVED", "REJECT"]
    reason: str = Field(min_length=3, max_length=2000)
