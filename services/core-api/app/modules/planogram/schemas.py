from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class PlanogramPreviewRequest(BaseModel):
    """Unattested candidate input for deterministic preview only."""

    products: list[dict[str, Any]] = Field(min_length=1, max_length=5000)
    layout: dict[str, Any]
    store_dna: dict[str, Any]
    mode: Literal["HYBRID", "CATEGORY", "ABC", "BRAND"] = "HYBRID"


class FixtureInventorySeed(BaseModel):
    fixture_type: str = Field(min_length=1, max_length=80)
    count: int = Field(ge=0, le=1000)
    source_ref: str | None = Field(default=None, max_length=160)


class FixtureMeasurement(BaseModel):
    fixture_id: str = Field(min_length=2, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    width_cm: float | None = Field(default=None, gt=0, le=1000)
    height_cm: float | None = Field(default=None, gt=0, le=1000)
    depth_cm: float | None = Field(default=None, gt=0, le=1000)
    max_weight_kg: float | None = Field(default=None, gt=0, le=5000)


class PlanogramArchitectureElement(BaseModel):
    """Measured orthogonal architectural primitive in metres.

    V1 deliberately uses deterministic rectangular primitives. This is enough to
    represent walls, columns, doors, exits and operational no-go zones today and
    creates a stable import target for CAD/floor-plan/LiDAR adapters later.
    """

    element_id: str = Field(min_length=2, max_length=80, pattern=r"^[A-Za-z0-9._:-]+$")
    element_type: Literal[
        "wall",
        "column",
        "door",
        "emergency_exit",
        "no_go",
        "technical",
        "inbound",
        "dispatch",
        "picker_entry",
        "picker_exit",
        "chiller",
        "freezer",
    ]
    x_m: float = Field(ge=0, le=500)
    y_m: float = Field(ge=0, le=500)
    width_m: float = Field(gt=0, le=500)
    depth_m: float = Field(gt=0, le=500)
    rotation_deg: Literal[0, 90, 180, 270] = 0
    clearance_m: float = Field(default=0, ge=0, le=20)
    label: str | None = Field(default=None, max_length=160)


class PlanogramArchitectureDraft(BaseModel):
    """Measured store architecture carried inside versioned Store DNA."""

    schema_version: Literal[1] = 1
    coordinate_system: Literal["cartesian_m"] = "cartesian_m"
    source: Literal["manual_survey", "cad_import", "floorplan_import", "lidar_scan"]
    source_ref: str = Field(min_length=3, max_length=500)
    floor_width_m: float = Field(gt=0, le=500)
    floor_depth_m: float = Field(gt=0, le=500)
    elements: list[PlanogramArchitectureElement] = Field(min_length=1, max_length=2000)

    @field_validator("elements")
    @classmethod
    def validate_architecture_elements(
        cls, value: list[PlanogramArchitectureElement]
    ) -> list[PlanogramArchitectureElement]:
        ids = [item.element_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate architecture element id")
        picker_entries = [item for item in value if item.element_type == "picker_entry"]
        if len(picker_entries) != 1:
            raise ValueError("Architecture requires exactly one picker_entry")
        return value


class PlanogramStoreDnaDraftRequest(BaseModel):
    store_code: str = Field(min_length=1, max_length=80, pattern=r"^[A-Za-z0-9._-]+$")
    store_name: str | None = Field(default=None, min_length=1, max_length=160)
    source: Literal["warehouse_bootstrap", "warehouse_revision", "inventory_seed"] = (
        "warehouse_bootstrap"
    )
    aisle_count: int = Field(default=11, ge=1, le=40)
    modules_per_side: int = Field(default=6, ge=1, le=20)
    shelves_per_module: int = Field(default=6, ge=1, le=20)
    pallet_count: int = Field(default=6, ge=0, le=50)
    aisle_widths_m: dict[str, float] = Field(default_factory=dict)
    fixture_measurements: list[FixtureMeasurement] = Field(default_factory=list, max_length=2000)
    fixture_inventory: list[FixtureInventorySeed] = Field(default_factory=list, max_length=200)
    architecture: PlanogramArchitectureDraft | None = None
    notes: str | None = Field(default=None, max_length=2000)

    @field_validator("aisle_widths_m")
    @classmethod
    def validate_aisle_widths(cls, value: dict[str, float]) -> dict[str, float]:
        for aisle_id, width in value.items():
            if not aisle_id or len(aisle_id) > 20:
                raise ValueError("Invalid aisle id")
            if width < 0.5 or width > 10:
                raise ValueError("Aisle width must be between 0.5m and 10m")
        return value

    @field_validator("fixture_measurements")
    @classmethod
    def unique_fixture_measurements(
        cls, value: list[FixtureMeasurement]
    ) -> list[FixtureMeasurement]:
        ids = [item.fixture_id for item in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate fixture measurement id")
        return value


class PlanogramStoreDnaApproveRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class PlanogramStoreDnaRejectRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PlanogramStoreDnaRevisionRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class PlanogramStoreDnaVersionRef(BaseModel):
    id: UUID
    store_code: str
    version_number: int
    status: Literal["draft", "submitted", "approved", "rejected", "superseded"]
