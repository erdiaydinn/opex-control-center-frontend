from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PlanogramPreviewRequest(BaseModel):
    """Unattested candidate input for deterministic preview only."""

    products: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    layout: dict[str, Any]
    store_dna: dict[str, Any]
    mode: Literal["HYBRID", "CATEGORY", "ABC", "BRAND"] = "HYBRID"
