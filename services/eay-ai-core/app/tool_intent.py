from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .company_context_boundary import (
    CompanyContextPlane,
    CompanyContextSnapshot,
    has_company_artifact,
)
from .ys_tr_cycle_count_intelligence import is_cycle_count_question

ToolName = Literal["ops_kpi_query", "regulatory_impact_query", "catalog_query", "none"]

YS_TR_CYCLE_COUNT_SEMANTIC_REF = (
    "company-semantic://ys-tr/cycle-count-weekly-compliance/v1"
)


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
    """Select only globally safe/generic tool intent.

    Public callers never activate a company-specific semantic profile merely by
    naming company-like terms in the prompt.
    """

    return _select_tool(message=message, company_context=None)


def select_company_tool(
    message: str,
    *,
    company_context: CompanyContextSnapshot,
) -> ToolIntentResponse:
    """Select with a trusted, integrity-checked company context."""

    context = CompanyContextSnapshot.model_validate(
        company_context.model_dump(mode="json")
    )
    return _select_tool(message=message, company_context=context)


def _select_tool(
    *,
    message: str,
    company_context: CompanyContextSnapshot | None,
) -> ToolIntentResponse:
    text = message.strip()

    # YS_TR cycle-count interpretation is company knowledge, not global truth.
    # It is enabled only when the trusted company snapshot contains the exact
    # reviewed semantic artifact. The public /select endpoint cannot supply or
    # self-assert this context.
    if (
        company_context is not None
        and has_company_artifact(
            snapshot=company_context,
            plane=CompanyContextPlane.KNOWLEDGE,
            artifact_ref=YS_TR_CYCLE_COUNT_SEMANTIC_REF,
        )
        and is_cycle_count_question(text)
    ):
        return ToolIntentResponse(
            tool="ops_kpi_query",
            confidence=0.97,
            rationale=(
                "Reviewed company-bound YS_TR cycle-count semantics matched; "
                "route to governed operational KPI handling. Assignment-week "
                "and late-completion meaning remain defined by the exact "
                "company semantic profile."
            ),
            required_scope=["ops:read"],
            execution_allowed=False,
        )

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
    tool, scope, confidence = sorted(
        matches,
        key=lambda item: (priority[item[0]], item[2]),
        reverse=True,
    )[0]
    return ToolIntentResponse(
        tool=tool,
        confidence=confidence,
        rationale=(
            f"Deterministic keyword/risk routing selected {tool}; "
            "model execution is not trusted by this selector."
        ),
        required_scope=scope,
        execution_allowed=False,
    )


router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.post("/select", response_model=ToolIntentResponse)
def select_tool_endpoint(payload: ToolIntentRequest):
    # Intentionally generic: company identity must come from a trusted
    # authenticated runtime boundary, never from user-supplied request text.
    return select_tool(payload.message)
