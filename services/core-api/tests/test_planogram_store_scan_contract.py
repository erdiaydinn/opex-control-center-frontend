from __future__ import annotations

from uuid import UUID

import pytest

from app.core.security import Principal
from app.modules.planogram.router import post_store_scan_normalize_preview
from app.modules.planogram.schemas import PlanogramStoreScanPreviewRequest
from app.modules.planogram.store_scan import normalize_store_scan

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="store-scan-test-user",
        tenant_id=TENANT,
        roles=("super_admin",),
        permissions=("module:planogram:view", "action:planogram:create"),
        auth_mode="development",
    )


def payload(*, wall_rotation: float = 0.0) -> PlanogramStoreScanPreviewRequest:
    return PlanogramStoreScanPreviewRequest(
        store_code="TEST-STORE",
        provider="apple_roomplan",
        source_ref="scan-session:test-001",
        floor_width_m=12,
        floor_depth_m=8,
        elements=[
            {
                "element_id": "wall-1",
                "element_type": "wall",
                "x_m": 0,
                "y_m": 0,
                "width_m": 12,
                "depth_m": 0.1,
                "rotation_deg": wall_rotation,
                "confidence": 0.99,
            },
            {
                "element_id": "door-1",
                "element_type": "door",
                "x_m": 1,
                "y_m": 0,
                "width_m": 1,
                "depth_m": 0.1,
                "rotation_deg": 0,
                "confidence": 0.94,
            },
            {
                "element_id": "fixture-1",
                "element_type": "fixture",
                "x_m": 4,
                "y_m": 3,
                "width_m": 1.2,
                "depth_m": 0.6,
                "rotation_deg": 0,
                "confidence": 0.88,
                "label": "gondola candidate",
            },
        ],
    )


def test_store_scan_preserves_truth_boundary_and_separates_fixture_evidence() -> None:
    result = normalize_store_scan(payload().model_dump(mode="python"))

    assert result["contract"] == "planogram-store-scan-v1"
    assert result["provider"] == "apple_roomplan"
    assert len(result["scan_fingerprint"]) == 64
    assert result["raw_media_persisted"] is False
    assert result["production_evidence"] is False
    assert result["promotable_to_store_dna"] is False
    assert result["recognized_fixture_count"] == 1
    assert result["architecture_preview"]["source"] == "lidar_scan"
    assert result["architecture_v2_preview"]["source"] == "lidar_scan"
    assert result["architecture_v2_preview_available"] is True
    assert {row["element_type"] for row in result["architecture_preview"]["elements"]} == {
        "wall",
        "door",
    }
    assert {row["element_type"] for row in result["architecture_v2_preview"]["elements"]} == {
        "wall",
        "door",
    }
    assert "picker_entry_annotation_required" in result["blockers"]
    assert "operational_zone_annotation_required" in result["blockers"]
    assert "human_scan_review_required" in result["blockers"]


def test_store_scan_fingerprint_is_deterministic_and_geometry_bound() -> None:
    baseline = normalize_store_scan(payload().model_dump(mode="python"))
    repeated = normalize_store_scan(payload().model_dump(mode="python"))
    rotated = normalize_store_scan(payload(wall_rotation=17).model_dump(mode="python"))

    assert baseline["scan_fingerprint"] == repeated["scan_fingerprint"]
    assert baseline["scan_fingerprint"] != rotated["scan_fingerprint"]


def test_non_orthogonal_scan_is_preserved_in_v2_without_fake_v1_authority() -> None:
    result = normalize_store_scan(payload(wall_rotation=17).model_dump(mode="python"))

    assert result["unsupported_rotation_count"] == 1
    assert "store_dna_v1_cannot_promote_non_orthogonal_geometry" in result["blockers"]
    assert result["architecture_v2_preview_available"] is True
    wall = next(
        row
        for row in result["architecture_v2_preview"]["elements"]
        if row["element_id"] == "wall-1"
    )
    assert wall["rotation_deg"] == 17
    assert wall["center_x_m"] == 6
    assert wall["center_y_m"] == pytest.approx(0.05)
    assert all(
        row["element_id"] != "wall-1"
        for row in result["architecture_preview"]["elements"]
    )
    assert any(
        warning == "scan_non_orthogonal_preserved_in_v2:wall-1"
        for warning in result["warnings"]
    )


@pytest.mark.asyncio
async def test_store_scan_route_is_preview_only_and_tenant_bound() -> None:
    response = await post_store_scan_normalize_preview(payload(), principal())

    assert response["tenant_id"] == str(TENANT)
    assert response["store_code"] == "TEST-STORE"
    assert response["preview_only"] is True
    assert response["input_authority"] == "request_supplied_measured_scan_unattested"
    assert response["production_release_allowed"] is False
    assert len(response["store_scan"]["scan_fingerprint"]) == 64
    assert response["store_scan"]["next_required_action"] == (
        "human_review_and_operational_annotation"
    )
