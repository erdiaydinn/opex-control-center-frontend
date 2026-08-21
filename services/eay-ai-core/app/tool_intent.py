from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

ToolName = Literal["ops_kpi_query", "regulatory_impact_query", "catalog_query", "none"]


class ToolIntentRequest(BaseModel):
    message: str = Field(min_length=2, max_length=4000)


class ToolIntentResponse(BaseModel):
    tool: ToolName
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str
    required_scope: list[str] = Field(default_factory=list)
    execution_allowed: bool = False


_RULES: list[tuple[ToolName, re.Pattern[str], list[str], float]] = [
    (
        "regulatory_impact_query",
        re.compile(
            r"\b(mevzuat|yasa|yönetmelik|tebliğ|kodeks|resm[iî]\s*gazete|hukuk|regulation|law|legal|"
            r"etkilenen\s+(?:sku|ürün|kategori|depo|tedarikçi))\b",
            re.IGNORECASE,
        ),
        ["legal:read", "catalog:read"],
        0.92,
    ),
    (
        "catalog_query",
        re.compile(
            r"\b(sku|ürün|product|barcode|barkod|kategori|category|tedarikçi|supplier|catalog|katalog)\b",
            re.IGNORECASE,
        ),
        ["catalog:read"],
        0.86,
    ),
    (
        "ops_kpi_query",
        re.compile(
            r"\b(nsfr|pfr|refund|cancel|iptal|prep|picking|putaway|cycle\s*count|sayım|otp|defect|"
            r"kpi|performans|performance|depo|warehouse|store|sipariş|order)\b",
            re.IGNORECASE,
        ),
        ["ops:read"],
        0.84,
    ),
]


def select_tool(message: str) -> ToolIntentResponse:
    text = message.strip()
    matches: list[tuple[ToolName, list[str], float]] = []
    for tool, pattern, scope, confidence in _RULES:
        if pattern.search(text):
            matches.append((tool, scope, confidence))

    if not matches:
        return ToolIntentResponse(
            tool="none",
            confidence=0.65,
            rationale="No deterministic read-only operational, regulatory or catalog intent matched.",
            required_scope=[],
            execution_allowed=False,
        )

    # Regulatory intent wins when legal language is present because its downstream
    # path requires stricter source/provenance controls. Catalog wins over generic
    # ops when the user clearly names product-level entities.
    priority = {"regulatory_impact_query": 3, "catalog_query": 2, "ops_kpi_query": 1}
    tool, scope, confidence = sorted(matches, key=lambda item: (priority[item[0]], item[2]), reverse=True)[0]
    return ToolIntentResponse(
        tool=tool,
        confidence=confidence,
        rationale=f"Deterministic keyword/risk routing selected {tool}; model execution is not trusted by this selector.",
        required_scope=scope,
        execution_allowed=False,
    )


router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.post("/select", response_model=ToolIntentResponse)
def select_tool_endpoint(payload: ToolIntentRequest):
    return select_tool(payload.message)
