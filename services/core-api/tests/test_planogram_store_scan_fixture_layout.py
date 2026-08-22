from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.store_scan import normalize_store_scan
from app.modules.planogram.store_scan_binding_schemas import (
    PlanogramStoreScanFixtureLayoutPreviewRequest,
)
from app.modules.planogram.store_scan_fixture_layout import (
    build_scanned_fixture_layout_preview,
)
from app.modules.planogram.store_scan_fixture_router import (
    post_store_scan_fixture_layout_preview,
)

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="fixture-binding-reviewer",
        tenant_id=TENANT,
        roles=("operator",),
        permissions=("action:planogram:create",),
        auth_mode="test",
    )


def scan() -> dict[str, object]:
    return {
        "store_code": "TEST-STORE",
        "provider": "apple_roomplan",
        "source_ref": "scan-session:fixture-001",
        "floor_width_m": 14,
        "floor_depth_m": 10,
        "elements": [
            {
                "element_id": "wall-1",
                "element_type": "wall",
                "x_m": 3,
                "y_m": 3,
                "width_m": 4,
                "depth_m": 0.1,
                "rotation_deg": 17,
                "confidence": 0.99,
            },
            {
                "element_id": "fixture-1",
                "element_type": "fixture",
                "x_m": 7,
                "y_m": 5,
                "width_m": 1.2,
                "depth_m": 0.6,
                "rotation_deg": 17,
                "confidence": 0.92,
                "label": "ambient gondola",
            },
        ],
    }


def operational_elements() -> list[dict[str, object]]:
    return [
        {
            "element_id": "picker-entry-1",
            "element_type": "picker_entry",
            "center_x_m": 1,
            "center_y_m": 1,
            "width_m": 0.4,
            "depth_m": 0.4,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
        {
            "element_id": "inbound-1",
            "element_type": "inbound",
            "center_x_m": 2,
            "center_y_m": 8,
            "width_m": 2,
            "depth_m": 1.5,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
        {
            "element_id": "dispatch-1",
            "element_type": "dispatch",
            "center_x_m": 12,
            "center_y_m": 2,
            "width_m": 1.5,
            "depth_m": 1.5,
            "rotation_deg": 0,
            "clearance_m": 0,
        },
    ]


def binding(**overrides) -> dict[str, object]:
    row: dict[str, object] = {
        "scan_fixture_element_id": "fixture-1",
        "fixture_id": "GONDOLA-001",
        "aisle_id": "A01",
        "side": "L",
        "position": 1,
        "fixture_type": "steel_rack",
        "storage_type": "AMBIENT",
        "shelf_count": 3,
        "fixture_width_cm": 120,
        "fixture_height_cm": 180,
        "fixture_depth_cm": 60,
        "shelf_width_cm": 110,
        "shelf_height_cm": 50,
        "shelf_depth_cm": 50,
        "shelf_max_weight_kg": 45,
        "shelf_zone_types": ["bottom", "eye", "top"],
        "source_ref": "fixture-master://GONDOLA-001/v2",
        "attested": True,
    }
    row.update(overrides)
    return row


def request(**binding_overrides) -> PlanogramStoreScanFixtureLayoutPreviewRequest:
    fingerprint = normalize_store_scan(scan())["scan_fingerprint"]
    return PlanogramStoreScanFixtureLayoutPreviewRequest(
        scan=scan(),
        expected_scan_fingerprint=fingerprint,
        classifications=[],
        operational_elements=operational_elements(),
        fixture_bindings=[binding(**binding_overrides)],
        review_note="Fixture bound against measured catalog record.",
    )


def build(
    request: PlanogramStoreScanFixtureLayoutPreviewRequest,
) -> dict[str, object]:
    return build_scanned_fixture_layout_preview(
        scan_payload=request.scan.model_dump(mode="python"),
        expected_scan_fingerprint=request.expected_scan_fingerprint,
        classifications=[
            row.model_dump(mode="python") for row in request.classifications
        ],
        operational_elements=[
            row.model_dump(mode="python") for row in request.operational_elements
        ],
        fixture_bindings=[
            row.model_dump(mode="python") for row in request.fixture_bindings
        ],
        review_note=request.review_note,
        uncertainty_resolutions=[
            row.model_dump(mode="python") for row in request.uncertainty_resolutions
        ],
    )


def test_attested_binding_builds_physical_capacity_layout_without_move_authority() -> None:
    result = build(request())
    assert result["available"] is True
    assert result["layout_draft_ready"] is True
    assert result["fixture_binding_coverage_pct"] == 100.0
    assert result["physical_layout_authority"] is False
    assert result["store_dna_authority"] is False
    assert result["v4_v5_production_eligible"] is False
    assert result["architecture_v2_optimizer_bridge_required"] is True
    assert result["relocation_execution_allowed"] is False
    module = result["physical_layout_preview"]["aisles"][0]["modules"][0]
    assert module["module_id"] == "GONDOLA-001"
    assert module["x_m"] == pytest.approx(7.6)
    assert module["y_m"] == pytest.approx(5.3)
    assert module["rotation_deg"] == 17
    assert module["relocatable"] is False
    assert module["utility_relocation_attested"] is False
    assert len(module["shelves"]) == 3
    assert module["shelves"][0]["zone_type"] == "bottom"
    assert module["shelves"][1]["allowed_storage_type"] == "AMBIENT"
    assert module["shelves"][2]["max_weight_kg"] == 45


def test_confirmed_uncertain_fixture_flows_into_catalog_binding_without_authority() -> None:
    raw_scan = deepcopy(scan())
    raw_scan["elements"][1]["confidence"] = 0.4
    fingerprint = normalize_store_scan(raw_scan)["scan_fingerprint"]
    uncertain_request = PlanogramStoreScanFixtureLayoutPreviewRequest(
        scan=raw_scan,
        expected_scan_fingerprint=fingerprint,
        classifications=[],
        operational_elements=operational_elements(),
        uncertainty_resolutions=[
            {
                "element_id": "fixture-1",
                "decision": "confirm",
                "classified_type": "fixture",
            }
        ],
        fixture_bindings=[binding()],
    )
    result = build(uncertain_request)
    assert result["layout_draft_ready"] is True
    assert result["uncertainty_review"]["confirmed"] == 1
    module = result["physical_layout_preview"]["aisles"][0]["modules"][0]
    assert module["scan_uncertainty_human_confirmed"] is True
    assert module["scan_confidence"] == pytest.approx(0.4)
    assert result["physical_layout_authority"] is False
    assert result["store_dna_authority"] is False


def test_unresolved_uncertainty_blocks_fixture_layout_reconstruction() -> None:
    raw_scan = deepcopy(scan())
    raw_scan["elements"][1]["confidence"] = 0.4
    fingerprint = normalize_store_scan(raw_scan)["scan_fingerprint"]
    result = build_scanned_fixture_layout_preview(
        scan_payload=raw_scan,
        expected_scan_fingerprint=fingerprint,
        classifications=[],
        operational_elements=operational_elements(),
        fixture_bindings=[binding()],
    )
    assert result["layout_draft_ready"] is False
    assert "scan_uncertainty_unresolved:fixture-1" in result["review_blockers"]


def test_missing_or_unattested_fixture_binding_fails_closed() -> None:
    base = request()
    missing = build_scanned_fixture_layout_preview(
        scan_payload=base.scan.model_dump(mode="python"),
        expected_scan_fingerprint=base.expected_scan_fingerprint,
        classifications=[],
        operational_elements=[
            row.model_dump(mode="python") for row in base.operational_elements
        ],
        fixture_bindings=[],
    )
    assert missing["layout_draft_ready"] is False
    assert "scan_fixture_binding_missing:fixture-1" in missing["blockers"]

    unattested = build(request(attested=False))
    assert unattested["layout_draft_ready"] is False
    assert "scan_fixture_binding_not_attested:fixture-1" in unattested["blockers"]


def test_scan_vs_catalog_dimension_drift_is_a_hard_binding_blocker() -> None:
    result = build(request(fixture_width_cm=200, fixture_depth_cm=120))
    assert result["layout_draft_ready"] is False
    assert "scan_fixture_width_mismatch:fixture-1" in result["blockers"]
    assert "scan_fixture_depth_mismatch:fixture-1" in result["blockers"]


def test_binding_schema_rejects_duplicate_slots_and_client_authority() -> None:
    raw = request().model_dump(mode="python")
    duplicate = {
        **raw,
        "fixture_bindings": [
            binding(),
            binding(fixture_id="GONDOLA-002"),
        ],
    }
    with pytest.raises(ValidationError):
        PlanogramStoreScanFixtureLayoutPreviewRequest(**duplicate)
    for field in (
        "physical_layout_authority",
        "store_dna_authority",
        "v4_v5_production_eligible",
        "installation_approval_allowed",
    ):
        with pytest.raises(ValidationError):
            PlanogramStoreScanFixtureLayoutPreviewRequest(**{**raw, field: True})


@pytest.mark.asyncio
async def test_fixture_layout_route_is_mounted_and_never_grants_release_authority(
) -> None:
    assert "/v1/planogram/store-scan/fixture-layout-preview" in app.openapi()["paths"]
    response = await post_store_scan_fixture_layout_preview(request(), principal())
    assert response["tenant_id"] == str(TENANT)
    assert response["preview_only"] is True
    assert response["input_authority"] == (
        "fingerprint_bound_human_fixture_binding_unattested"
    )
    assert response["store_dna_approval_allowed"] is False
    assert response["physical_layout_release_allowed"] is False
    assert response["production_release_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["capex_approval_allowed"] is False
    assert response["result"]["layout_draft_ready"] is True
    assert response["result"]["physical_layout_authority"] is False
