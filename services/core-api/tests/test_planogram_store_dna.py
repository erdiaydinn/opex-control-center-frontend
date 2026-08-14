from __future__ import annotations

import pytest

from app.budget_main import app
from app.core.permission_catalog import (
    PLANOGRAM_ADMIN_PERMISSIONS,
    PLANOGRAM_EDITOR_PERMISSIONS,
)
from app.modules.planogram.schemas import (
    FixtureMeasurement,
    PlanogramStoreDnaDraftRequest,
)
from app.modules.planogram.store_dna import (
    build_store_dna_configuration,
    clone_configuration,
    configuration_fingerprint,
    geometry_attested,
    summarize_store_dna,
)


def request(**overrides: object) -> PlanogramStoreDnaDraftRequest:
    payload: dict[str, object] = {
        "store_code": "fulya",
        "store_name": "Fulya",
    }
    payload.update(overrides)
    return PlanogramStoreDnaDraftRequest(**payload)


def full_measurements() -> list[FixtureMeasurement]:
    items: list[FixtureMeasurement] = []
    for aisle in range(1, 12):
        for side in ("L", "R"):
            for module in range(1, 7):
                items.append(
                    FixtureMeasurement(
                        fixture_id=f"A{aisle:02d}-{side}{module:02d}",
                        width_cm=100,
                        height_cm=210,
                        depth_cm=50,
                        max_weight_kg=270,
                    )
                )
    for pallet in range(1, 7):
        items.append(
            FixtureMeasurement(
                fixture_id=f"P{pallet:02d}",
                width_cm=120,
                depth_cm=100,
                max_weight_kg=800,
            )
        )
    return items


def test_default_bootstrap_matches_warehouse_assumption() -> None:
    configuration = build_store_dna_configuration(request())
    assert configuration["store_code"] == "FULYA"
    assert configuration["template"] == {
        "aisle_count": 11,
        "modules_per_side": 6,
        "shelves_per_module": 6,
        "pallet_count": 6,
    }
    assert summarize_store_dna(configuration) == {
        "aisles": 11,
        "modules": 132,
        "shelves": 792,
        "pallets": 6,
    }
    assert configuration["aisles"][0]["left_modules"][0]["module_id"] == "A01-L01"
    assert configuration["aisles"][10]["right_modules"][5]["module_id"] == "A11-R06"
    assert configuration["pallets"][5]["pallet_id"] == "P06"


def test_default_topology_does_not_invent_physical_geometry() -> None:
    configuration = build_store_dna_configuration(request())
    assert geometry_attested(configuration) is False
    first = configuration["aisles"][0]["left_modules"][0]
    assert first["shelf_count"] == 6
    assert first["shelf_geometry"] == {
        "width_cm": None,
        "height_cm": None,
        "depth_cm": None,
        "max_weight_kg": None,
    }


def test_complete_measurements_can_attest_geometry() -> None:
    widths = {f"A{aisle:02d}": 1.2 for aisle in range(1, 12)}
    configuration = build_store_dna_configuration(
        request(
            aisle_widths_m=widths,
            fixture_measurements=full_measurements(),
        )
    )
    assert geometry_attested(configuration) is True
    assert summarize_store_dna(configuration)["shelves"] == 792


def test_unknown_fixture_or_aisle_measurement_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown fixture measurement ids"):
        build_store_dna_configuration(
            request(
                fixture_measurements=[
                    FixtureMeasurement(
                        fixture_id="A99-L01",
                        width_cm=100,
                        height_cm=200,
                        depth_cm=50,
                        max_weight_kg=200,
                    )
                ]
            )
        )

    with pytest.raises(ValueError, match="Unknown aisle width ids"):
        build_store_dna_configuration(request(aisle_widths_m={"A99": 1.2}))


def test_fingerprint_is_stable_and_revision_source_is_bound() -> None:
    configuration = build_store_dna_configuration(request())
    fingerprint = configuration_fingerprint(configuration)
    assert configuration_fingerprint(configuration) == fingerprint

    revision = clone_configuration(configuration)
    assert revision["source"] == "warehouse_revision"
    assert configuration_fingerprint(revision) != fingerprint
    assert configuration["source"] == "warehouse_bootstrap"


def test_planogram_editor_cannot_approve_but_admin_can() -> None:
    assert "action:planogram:approve" not in PLANOGRAM_EDITOR_PERMISSIONS
    assert "action:planogram:approve" in PLANOGRAM_ADMIN_PERMISSIONS
    assert "module:planogram:admin" in PLANOGRAM_ADMIN_PERMISSIONS


def test_store_dna_routes_are_part_of_canonical_core_contract() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/v1/planogram/store-dna/workspace",
        "/v1/planogram/store-dna/bootstrap",
        "/v1/planogram/store-dna/{version_id}",
        "/v1/planogram/store-dna/{version_id}/submit",
        "/v1/planogram/store-dna/{version_id}/approve",
        "/v1/planogram/store-dna/{version_id}/reject",
        "/v1/planogram/store-dna/{version_id}/revise",
        "/v1/planogram/store-dna/{store_code}/readiness",
    }
    assert required <= paths
