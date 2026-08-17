from __future__ import annotations

import pytest

from app.budget_main import app
from app.core.permission_catalog import ALL_PERMISSION_KEYS
from app.modules.planogram.schemas import (
    FixtureMeasurement,
    PlanogramArchitectureDraft,
    PlanogramArchitectureElement,
    PlanogramStoreDnaDraftRequest,
)
from app.modules.planogram.store_dna import (
    approved_store_dna_to_engine_contract,
    architecture_attested,
    build_store_dna_configuration,
    clone_configuration,
    configuration_fingerprint,
    geometry_attested,
    summarize_store_dna,
)


def request(**overrides: object) -> PlanogramStoreDnaDraftRequest:
    payload: dict[str, object] = {"store_code": "fulya", "store_name": "Fulya"}
    payload.update(overrides)
    return PlanogramStoreDnaDraftRequest(**payload)


def full_measurements() -> list[FixtureMeasurement]:
    items: list[FixtureMeasurement] = []
    for aisle in range(1, 12):
        for side in ("L", "R"):
            for module in range(1, 7):
                items.append(FixtureMeasurement(
                    fixture_id=f"A{aisle:02d}-{side}{module:02d}",
                    width_cm=100,
                    height_cm=210,
                    depth_cm=50,
                    max_weight_kg=270,
                ))
    for pallet in range(1, 7):
        items.append(FixtureMeasurement(
            fixture_id=f"P{pallet:02d}",
            width_cm=120,
            depth_cm=100,
            max_weight_kg=800,
        ))
    return items


def measured_architecture() -> PlanogramArchitectureDraft:
    return PlanogramArchitectureDraft(
        source="manual_survey",
        source_ref="survey://FULYA/2026-08-17",
        floor_width_m=25,
        floor_depth_m=18,
        elements=[
            PlanogramArchitectureElement(
                element_id="ENTRY-1",
                element_type="picker_entry",
                x_m=0.5,
                y_m=0.5,
                width_m=1,
                depth_m=1,
            ),
            PlanogramArchitectureElement(
                element_id="COL-1",
                element_type="column",
                x_m=8,
                y_m=6,
                width_m=0.6,
                depth_m=0.6,
            ),
            PlanogramArchitectureElement(
                element_id="EXIT-1",
                element_type="emergency_exit",
                x_m=23,
                y_m=16,
                width_m=1,
                depth_m=1,
                clearance_m=1,
            ),
        ],
    )


def test_default_bootstrap_is_topology_only_and_matches_warehouse_assumption() -> None:
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
        "architecture_elements": 0,
    }
    assert geometry_attested(configuration) is False
    assert architecture_attested(configuration) is False
    first = configuration["aisles"][0]["left_modules"][0]
    assert first["module_id"] == "A01-L01"
    assert first["shelf_geometry"] == {
        "width_cm": None,
        "height_cm": None,
        "depth_cm": None,
        "max_weight_kg": None,
    }
    assert configuration["pallets"][5]["pallet_id"] == "P06"


def test_complete_measurements_can_attest_geometry_without_inventing_values() -> None:
    widths = {f"A{aisle:02d}": 1.2 for aisle in range(1, 12)}
    configuration = build_store_dna_configuration(request(
        aisle_widths_m=widths,
        fixture_measurements=full_measurements(),
    ))
    assert geometry_attested(configuration) is True
    assert summarize_store_dna(configuration)["shelves"] == 792


def test_measured_architecture_is_versioned_and_reaches_engine_contract() -> None:
    configuration = build_store_dna_configuration(
        request(architecture=measured_architecture())
    )
    assert architecture_attested(configuration) is True
    assert summarize_store_dna(configuration)["architecture_elements"] == 3
    assert configuration["architecture"]["coordinate_system"] == "cartesian_m"
    engine_contract = approved_store_dna_to_engine_contract(configuration)
    assert engine_contract["architecture"] == configuration["architecture"]
    assert engine_contract["architecture"] is not configuration["architecture"]


def test_architecture_requires_exactly_one_picker_entry() -> None:
    with pytest.raises(ValueError, match="exactly one picker_entry"):
        PlanogramArchitectureDraft(
            source="manual_survey",
            source_ref="survey://FULYA/bad",
            floor_width_m=25,
            floor_depth_m=18,
            elements=[
                PlanogramArchitectureElement(
                    element_id="COL-1",
                    element_type="column",
                    x_m=8,
                    y_m=6,
                    width_m=0.6,
                    depth_m=0.6,
                )
            ],
        )


def test_unknown_fixture_or_aisle_measurement_fails_closed() -> None:
    with pytest.raises(ValueError, match="Unknown fixture measurement ids"):
        build_store_dna_configuration(request(fixture_measurements=[FixtureMeasurement(
            fixture_id="A99-L01", width_cm=100, height_cm=200, depth_cm=50, max_weight_kg=200,
        )]))
    with pytest.raises(ValueError, match="Unknown aisle width ids"):
        build_store_dna_configuration(request(aisle_widths_m={"A99": 1.2}))


def test_fingerprint_is_stable_and_revision_is_new_history() -> None:
    configuration = build_store_dna_configuration(request())
    fingerprint = configuration_fingerprint(configuration)
    assert configuration_fingerprint(configuration) == fingerprint
    revision = clone_configuration(configuration)
    assert revision["source"] == "warehouse_revision"
    assert configuration_fingerprint(revision) != fingerprint
    assert configuration["source"] == "warehouse_bootstrap"


def test_canonical_permission_catalog_has_separate_edit_and_approve_authority() -> None:
    assert "action:planogram:edit" in ALL_PERMISSION_KEYS
    assert "action:planogram:approve" in ALL_PERMISSION_KEYS
    assert "module:planogram:admin" in ALL_PERMISSION_KEYS


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
