from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .kpi_registry import require_executable_kpi

ToolName = Literal["ops_kpi_query", "regulatory_impact_query", "catalog_query"]
OpsMetric = Literal["orders", "cancel_rate", "nsfr", "pfr", "refund", "prep", "picking", "putaway", "otp", "defect"]
ImpactEntity = Literal["sku", "category", "store", "supplier"]


class StrictArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OpsKpiArgs(StrictArgs):
    metric: OpsMetric
    start_date: date
    end_date: date
    stores: list[str] = Field(default_factory=list, max_length=200)
    limit: int = Field(default=50, ge=1, le=500)

    @model_validator(mode="after")
    def valid_window(self):
        if self.end_date < self.start_date:
            raise ValueError("end_date_before_start_date")
        if (self.end_date - self.start_date).days > 366:
            raise ValueError("date_window_too_large")
        return self


class CatalogArgs(StrictArgs):
    query: str = Field(min_length=1, max_length=300)
    field: Literal["sku", "barcode", "product", "category", "supplier"] = "product"
    limit: int = Field(default=50, ge=1, le=500)


class RegulatoryImpactArgs(StrictArgs):
    instrument_id: str = Field(min_length=3, max_length=180)
    as_of: date
    entities: list[ImpactEntity] = Field(default_factory=lambda: ["sku", "category"], min_length=1, max_length=4)
    limit: int = Field(default=100, ge=1, le=500)


class ToolPlan(BaseModel):
    tool: ToolName
    query_id: str
    required_scope: list[str]
    arguments: dict
    read_only: bool = True
    model_authored_sql_allowed: bool = False
    requires_human_review: bool = False


QUERY_IDS = {
    "catalog_query": "catalog.lookup.v1",
    "regulatory_impact_query": "regulatory.impact.v1",
}

SCOPES = {
    "ops_kpi_query": ["ops:read"],
    "catalog_query": ["catalog:read"],
    "regulatory_impact_query": ["legal:read", "catalog:read"],
}


def build_tool_plan(tool: ToolName, arguments: dict) -> ToolPlan:
    if tool == "ops_kpi_query":
        parsed = OpsKpiArgs(**arguments)
        kpi = require_executable_kpi(parsed.metric)
        query_id = kpi.query_id
        if query_id is None:
            raise ValueError(f"metric_template_not_implemented:{parsed.metric}")
    elif tool == "catalog_query":
        parsed = CatalogArgs(**arguments)
        query_id = QUERY_IDS[tool]
    elif tool == "regulatory_impact_query":
        parsed = RegulatoryImpactArgs(**arguments)
        query_id = QUERY_IDS[tool]
    else:
        raise ValueError("unsupported_tool")
    return ToolPlan(
        tool=tool,
        query_id=query_id,
        required_scope=SCOPES[tool],
        arguments=parsed.model_dump(mode="json"),
        read_only=True,
        model_authored_sql_allowed=False,
        requires_human_review=False,
    )


class ToolPlanRequest(BaseModel):
    tool: ToolName
    arguments: dict


router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.post("/plan", response_model=ToolPlan)
def plan_tool(payload: ToolPlanRequest):
    try:
        return build_tool_plan(payload.tool, payload.arguments)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
