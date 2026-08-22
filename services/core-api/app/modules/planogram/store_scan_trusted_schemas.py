from __future__ import annotations

from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator, model_validator

from app.modules.planogram.fixture_catalog_schemas import PlanogramTrustedFixtureBinding
from app.modules.planogram.schemas import (
    PlanogramOrderBasket,
    PlanogramStoreScanAnnotationPreviewRequest,
)


class PlanogramStoreScanTrustedFixtureLayoutPreviewRequest(
    PlanogramStoreScanAnnotationPreviewRequest
):
    """Topology-only binding request; fixture physical truth is server-resolved."""

    model_config = ConfigDict(extra="forbid")

    fixture_bindings: list[PlanogramTrustedFixtureBinding] = Field(
        default_factory=list,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_binding_uniqueness(
        self,
    ) -> PlanogramStoreScanTrustedFixtureLayoutPreviewRequest:
        target_ids = [row.scan_fixture_element_id for row in self.fixture_bindings]
        slots = [(row.aisle_id, row.side, row.position) for row in self.fixture_bindings]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Duplicate scan fixture binding target")
        if len(slots) != len(set(slots)):
            raise ValueError("Duplicate aisle/side/position binding slot")
        return self


class PlanogramStoreScanTrustedOptimizePreviewRequest(
    PlanogramStoreScanTrustedFixtureLayoutPreviewRequest
):
    """V6 input whose fixture authority is server-side only."""

    model_config = ConfigDict(extra="forbid")

    products: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    order_baskets: list[PlanogramOrderBasket] = Field(min_length=1, max_length=5000)
    mode: Literal["HYBRID", "CATEGORY", "ABC", "BRAND"] = "HYBRID"

    @field_validator("products")
    @classmethod
    def unique_product_skus(cls, value: list[dict[str, Any]]) -> list[dict[str, Any]]:
        skus = [
            str(row.get("sku") or row.get("SKU") or "").strip().upper()
            for row in value
        ]
        if any(not sku for sku in skus):
            raise ValueError("Every scanned optimizer product requires sku")
        if len(skus) != len(set(skus)):
            raise ValueError("Duplicate scanned optimizer product sku")
        return value
