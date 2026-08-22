from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.modules.planogram.schemas import PlanogramOrderBasket
from app.modules.planogram.store_scan_review_schemas import (
    PlanogramStoreScanAnnotationPreviewRequest,
)


class PlanogramScannedFixtureBinding(BaseModel):
    """Human-confirmed catalog truth for one recognized scan fixture."""

    model_config = ConfigDict(extra="forbid")

    scan_fixture_element_id: str = Field(min_length=1, max_length=120)
    fixture_id: str = Field(min_length=2, max_length=120, pattern=r"^[A-Za-z0-9._:-]+$")
    aisle_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._:-]+$")
    side: Literal["L", "R"]
    position: int = Field(ge=1, le=500)
    fixture_type: str = Field(min_length=2, max_length=120)
    storage_type: Literal["AMBIENT", "CHILLED", "FROZEN", "PALLET"]
    shelf_count: int = Field(ge=1, le=30)
    fixture_width_cm: float = Field(gt=0, le=2000)
    fixture_height_cm: float = Field(gt=0, le=2000)
    fixture_depth_cm: float = Field(gt=0, le=2000)
    shelf_width_cm: float = Field(gt=0, le=2000)
    shelf_height_cm: float = Field(gt=0, le=1000)
    shelf_depth_cm: float = Field(gt=0, le=2000)
    shelf_max_weight_kg: float = Field(gt=0, le=5000)
    shelf_zone_types: list[
        Literal["bottom", "lower", "eye", "upper", "top"]
    ] = Field(min_length=1, max_length=30)
    source_ref: str = Field(min_length=3, max_length=500)
    attested: bool

    @model_validator(mode="after")
    def validate_shelf_contract(self) -> PlanogramScannedFixtureBinding:
        if len(self.shelf_zone_types) != self.shelf_count:
            raise ValueError("shelf_zone_types length must equal shelf_count")
        if self.shelf_width_cm > self.fixture_width_cm * 1.05:
            raise ValueError("Shelf width cannot exceed attested fixture width")
        if self.shelf_depth_cm > self.fixture_depth_cm * 1.05:
            raise ValueError("Shelf depth cannot exceed attested fixture depth")
        if self.shelf_height_cm * self.shelf_count > self.fixture_height_cm * 1.25:
            raise ValueError("Shelf vertical geometry exceeds attested fixture height")
        return self


class PlanogramStoreScanFixtureLayoutPreviewRequest(
    PlanogramStoreScanAnnotationPreviewRequest
):
    """Recompute reviewed scan and bind recognized fixtures to attested catalog truth."""

    model_config = ConfigDict(extra="forbid")

    fixture_bindings: list[PlanogramScannedFixtureBinding] = Field(
        default_factory=list,
        max_length=1000,
    )

    @model_validator(mode="after")
    def validate_fixture_binding_uniqueness(
        self,
    ) -> PlanogramStoreScanFixtureLayoutPreviewRequest:
        target_ids = [row.scan_fixture_element_id for row in self.fixture_bindings]
        fixture_ids = [row.fixture_id for row in self.fixture_bindings]
        slots = [(row.aisle_id, row.side, row.position) for row in self.fixture_bindings]
        if len(target_ids) != len(set(target_ids)):
            raise ValueError("Duplicate scan fixture binding target")
        if len(fixture_ids) != len(set(fixture_ids)):
            raise ValueError("Duplicate fixture_id in scan fixture bindings")
        if len(slots) != len(set(slots)):
            raise ValueError("Duplicate aisle/side/position binding slot")
        return self


class PlanogramStoreScanOptimizePreviewRequest(
    PlanogramStoreScanFixtureLayoutPreviewRequest
):
    """Server-recomputed V6 optimization input; client layout authority is forbidden."""

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
