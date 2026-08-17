from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from app.modules.planogram.schemas import (
    FixtureInventorySeed,
    FixtureMeasurement,
    PlanogramStoreDnaDraftRequest,
)

DEFAULT_AISLE_COUNT = 11
DEFAULT_MODULES_PER_SIDE = 6
DEFAULT_SHELVES_PER_MODULE = 6
DEFAULT_PALLET_COUNT = 6


class StoreDnaStateError(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def normalize_store_code(value: str) -> str:
    return value.strip().upper()


def _measurement_map(
    measurements: list[FixtureMeasurement],
) -> dict[str, FixtureMeasurement]:
    return {item.fixture_id: item for item in measurements}


def _inventory_rows(items: list[FixtureInventorySeed]) -> list[dict[str, Any]]:
    return [item.model_dump(exclude_none=True) for item in items]


def build_store_dna_configuration(
    payload: PlanogramStoreDnaDraftRequest,
) -> dict[str, Any]:
    store_code = normalize_store_code(payload.store_code)
    measurements = _measurement_map(payload.fixture_measurements)
    known_fixture_ids: set[str] = set()
    known_aisle_ids: set[str] = set()
    aisles: list[dict[str, Any]] = []

    for aisle_number in range(1, payload.aisle_count + 1):
        aisle_id = f"A{aisle_number:02d}"
        known_aisle_ids.add(aisle_id)
        aisle_width = payload.aisle_widths_m.get(aisle_id)
        left_modules: list[dict[str, Any]] = []
        right_modules: list[dict[str, Any]] = []

        for side, target in (("L", left_modules), ("R", right_modules)):
            for position in range(1, payload.modules_per_side + 1):
                fixture_id = f"{aisle_id}-{side}{position:02d}"
                known_fixture_ids.add(fixture_id)
                measured = measurements.get(fixture_id)
                target.append(
                    {
                        "module_id": fixture_id,
                        "side": side,
                        "position": position,
                        "fixture_type": "regular_shelf",
                        "shelf_count": payload.shelves_per_module,
                        "shelf_geometry": {
                            "width_cm": measured.width_cm if measured else None,
                            "height_cm": measured.height_cm if measured else None,
                            "depth_cm": measured.depth_cm if measured else None,
                            "max_weight_kg": measured.max_weight_kg if measured else None,
                        },
                    }
                )

        aisles.append(
            {
                "aisle_id": aisle_id,
                "sequence": aisle_number,
                "width_m": aisle_width,
                "left_modules": left_modules,
                "right_modules": right_modules,
            }
        )

    pallets: list[dict[str, Any]] = []
    for pallet_number in range(1, payload.pallet_count + 1):
        fixture_id = f"P{pallet_number:02d}"
        known_fixture_ids.add(fixture_id)
        measured = measurements.get(fixture_id)
        pallets.append(
            {
                "pallet_id": fixture_id,
                "sequence": pallet_number,
                "width_cm": measured.width_cm if measured else None,
                "depth_cm": measured.depth_cm if measured else None,
                "max_weight_kg": measured.max_weight_kg if measured else None,
            }
        )

    unknown_measurements = sorted(set(measurements) - known_fixture_ids)
    if unknown_measurements:
        raise ValueError(
            "Unknown fixture measurement ids: " + ", ".join(unknown_measurements[:10])
        )

    unknown_aisle_widths = sorted(set(payload.aisle_widths_m) - known_aisle_ids)
    if unknown_aisle_widths:
        raise ValueError(
            "Unknown aisle width ids: " + ", ".join(unknown_aisle_widths[:10])
        )

    return {
        "schema_version": 1,
        "source": payload.source,
        "store_code": store_code,
        "store_name": payload.store_name,
        "template": {
            "aisle_count": payload.aisle_count,
            "modules_per_side": payload.modules_per_side,
            "shelves_per_module": payload.shelves_per_module,
            "pallet_count": payload.pallet_count,
        },
        "aisles": aisles,
        "pallets": pallets,
        "fixture_inventory": _inventory_rows(payload.fixture_inventory),
        "architecture": (
            payload.architecture.model_dump(exclude_none=True)
            if payload.architecture is not None
            else None
        ),
        "notes": payload.notes,
    }


def summarize_store_dna(configuration: dict[str, Any]) -> dict[str, int]:
    aisles = configuration.get("aisles", [])
    modules = [
        module
        for aisle in aisles
        for side in ("left_modules", "right_modules")
        for module in aisle.get(side, [])
    ]
    architecture = configuration.get("architecture") or {}
    return {
        "aisles": len(aisles),
        "modules": len(modules),
        "shelves": sum(int(module.get("shelf_count", 0)) for module in modules),
        "pallets": len(configuration.get("pallets", [])),
        "architecture_elements": len(architecture.get("elements") or []),
    }


def geometry_attested(configuration: dict[str, Any]) -> bool:
    aisles = configuration.get("aisles", [])
    if not aisles:
        return False

    for aisle in aisles:
        if aisle.get("width_m") is None:
            return False
        for side in ("left_modules", "right_modules"):
            for module in aisle.get(side, []):
                geometry = module.get("shelf_geometry") or {}
                if any(
                    geometry.get(key) is None
                    for key in ("width_cm", "height_cm", "depth_cm", "max_weight_kg")
                ):
                    return False

    for pallet in configuration.get("pallets", []):
        if any(
            pallet.get(key) is None
            for key in ("width_cm", "depth_cm", "max_weight_kg")
        ):
            return False

    return True


def architecture_attested(configuration: dict[str, Any]) -> bool:
    """Return whether versioned Store DNA carries measured architecture truth."""
    architecture = configuration.get("architecture") or {}
    if not architecture:
        return False
    if architecture.get("coordinate_system") != "cartesian_m":
        return False
    if not architecture.get("source_ref"):
        return False
    if architecture.get("source") not in {
        "manual_survey",
        "cad_import",
        "floorplan_import",
        "lidar_scan",
    }:
        return False
    if not architecture.get("floor_width_m") or not architecture.get("floor_depth_m"):
        return False
    entries = [
        row
        for row in architecture.get("elements") or []
        if row.get("element_type") == "picker_entry"
    ]
    return len(entries) == 1


def configuration_fingerprint(configuration: dict[str, Any]) -> str:
    payload = json.dumps(
        configuration,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def clone_configuration(configuration: dict[str, Any]) -> dict[str, Any]:
    cloned = deepcopy(configuration)
    cloned["source"] = "warehouse_revision"
    return cloned


def approved_store_dna_to_engine_contract(
    configuration: dict[str, Any],
) -> dict[str, Any]:
    """Translate only server-approved topology into the canonical engine contract.

    This helper intentionally does not invent missing geometry. The caller must
    still check geometry_attested before treating the result as physical truth.
    Measured architecture, when present, is preserved verbatim so the canonical
    engine can validate collisions and real walk distance against the same
    versioned Store DNA fingerprint.
    """
    widths = [aisle.get("width_m") for aisle in configuration.get("aisles", [])]
    measured_widths = [float(width) for width in widths if width is not None]
    picker_width = min(measured_widths) if measured_widths else None

    return {
        # Must match the canonical physical_truth approved-source vocabulary.
        # Server-side approval is the authority that permits this translation.
        "source": "approved_store_dna",
        "store_code": configuration.get("store_code"),
        "picker_aisle_width_m": picker_width,
        "aisle_module_config": [
            {
                "aisle_id": aisle.get("aisle_id"),
                "left_modules": [
                    {
                        "module_id": module.get("module_id"),
                        "side": "L",
                        "shelf_count": module.get("shelf_count"),
                    }
                    for module in aisle.get("left_modules", [])
                ],
                "right_modules": [
                    {
                        "module_id": module.get("module_id"),
                        "side": "R",
                        "shelf_count": module.get("shelf_count"),
                    }
                    for module in aisle.get("right_modules", [])
                ],
            }
            for aisle in configuration.get("aisles", [])
        ],
        "pallet_fixture_ids": [
            pallet.get("pallet_id") for pallet in configuration.get("pallets", [])
        ],
        "architecture": deepcopy(configuration.get("architecture")),
    }
