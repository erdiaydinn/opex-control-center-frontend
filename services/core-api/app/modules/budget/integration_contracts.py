from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

ExternalSource = Literal["ARIBA", "SAP", "BIGQUERY", "MANUAL"]


class EmployeeFinanceBoundaryRecord(BaseModel):
    """Future boundary only; Budget Core does not persist employee-finance entities."""

    source_event_id: str = Field(min_length=1, max_length=160)
    source_system: str = Field(min_length=1, max_length=80)
    budget_line_id: UUID
    fiscal_period_id: UUID
    cost_center_id: UUID
    approved_base_amount: Decimal = Field(max_digits=18, decimal_places=2)
    accounting_date: date


def validate_external_identity(
    source_system: ExternalSource,
    entity_type: str,
    normalized: dict[str, str],
) -> str | None:
    if source_system == "MANUAL":
        return None
    required_by_entity = {
        "purchase_request": ("external_ref",),
        "purchase_order": ("external_id",),
        "invoice": ("supplier_id", "invoice_number"),
    }
    required = required_by_entity.get(entity_type, ())
    missing = [field for field in required if not normalized.get(field)]
    if missing:
        return (
            f"{source_system} {entity_type} requires canonical external identity: "
            + ", ".join(missing)
        )
    return None
