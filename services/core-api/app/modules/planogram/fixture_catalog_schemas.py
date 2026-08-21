from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlanogramFixtureCatalogDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_code: str = Field(min_length=2, max_length=80)
    fixture_name: str = Field(min_length=1, max_length=160)
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
    measured_source: Literal[
        "manual_survey",
        "cad_import",
        "floorplan_import",
        "lidar_scan",
        "surveyed_fixture_catalog",
    ]
    source_ref: str = Field(min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_geometry(self) -> PlanogramFixtureCatalogDraftRequest:
        if len(self.shelf_zone_types) != self.shelf_count:
            raise ValueError("shelf_zone_types length must equal shelf_count")
        if self.shelf_width_cm > self.fixture_width_cm * 1.05:
            raise ValueError("shelf_width_cm exceeds fixture width")
        if self.shelf_depth_cm > self.fixture_depth_cm * 1.05:
            raise ValueError("shelf_depth_cm exceeds fixture depth")
        if self.shelf_height_cm * self.shelf_count > self.fixture_height_cm * 1.25:
            raise ValueError("shelf vertical geometry exceeds fixture height")
        return self


class PlanogramFixtureCatalogDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str | None = Field(default=None, max_length=500)


class PlanogramFixtureCatalogRejectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


class PlanogramFixtureCatalogRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reason: str = Field(min_length=3, max_length=500)


class PlanogramTrustedFixtureBinding(BaseModel):
    """Human topology + server-approved fixture identity only.

    Geometry, storage, capacity, measured source and attestation are intentionally
    absent so the browser cannot mint physical authority.
    """

    model_config = ConfigDict(extra="forbid")

    scan_fixture_element_id: str = Field(min_length=1, max_length=120)
    approved_catalog_version_id: UUID
    aisle_id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9._:-]+$")
    side: Literal["L", "R"]
    position: int = Field(ge=1, le=500)
    expected_record_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
