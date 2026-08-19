from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.schemas import PlanogramStoreScanAnnotationPreviewRequest
from app.modules.planogram.store_scan import normalize_store_scan
from app.modules.planogram.store_scan_annotation import build_reviewed_store_scan_draft
from app.modules.planogram.store_scan_review_router import post_store_scan_annotation_preview

TENANT = UUID("11111111-1111-4111-8111-111111111111")


def principal() -> Principal:
    return Principal(
        subject="scan-reviewer",
        tenant_id=TENANT,
        roles=("operator",),
        permissions=("action:planogram:create",),
        auth_mode="test",
    )


def scan() -> dict[str, object]:
    return {
        "store_code": "TEST-STORE",
        "provider": "apple_roomplan",
        "source_ref": "scan-session:review-001",
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
                "element_id": "opening-1",
                "element_type": "opening",
                "x_m": 5,
                "y_m": 3,
                "width_m": 1.1,
                "depth_m": 0.1,
                "rotation_deg": 17,
                "confidence": 0.96,
            },
            {
                "element_id": "fixture-1",
                "element_type": "fixture",
                "x_m": 7,
                "y_m": 5,
                "width_m": 1.2,
                "depth_m": 0.6,
                "rotation_deg": 17,
                "confidence": 0.9,
            },
        ],
    }


def annotations() -> list[dict[str, object]]:
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


def payload() -> PlanogramStoreScanAnnotationPreviewRequest:
    normalized = normalize_store_scan(scan())
    return PlanogramStoreScanAnnotationPreviewRequest(
        scan=scan(),
        expected_scan_fingerprint=normalized["scan_fingerprint"],
        classifications=[
            {
                "element_id": "opening-1",
                "classified_type": "door",
                "clearance_m": 0,
            }
        ],
        operational_elements=annotations(),
        review_note="Measured capture reviewed against floor walk.",
    )


def test_reviewed_scan_preserves_angle_and_produces_non_authoritative_v2_draft() -> None:
    request = payload()
    result = build_reviewed_store_scan_draft(
        scan_payload=request.scan.model_dump(mode="python"),
        expected_scan_fingerprint=request.expected_scan_fingerprint,
        classifications=[row.model_dump(mode="python") for row in request.classifications],
        operational_elements=[
            row.model_dump(mode="python") for row in request.operational_elements
        ],
        review_note=request.review_note,
    )

    assert result["available"] is True
    assert result["reviewed_draft_ready"] is True
    assert result["store_dna_authority"] is False
    assert result["maker_checker_approved"] is False
    assert result["production_authority"] is False
    assert result["installation_approval_allowed"] is False
    assert result["auto_store_dna_promotion_allowed"] is False
    assert len(result["reviewed_draft_fingerprint"]) == 64
    architecture = result["reviewed_store_dna_v2_preview"]["architecture"]
    wall = next(row for row in architecture["elements"] if row["element_id"] == "wall-1")
    opening = next(
        row for row in architecture["elements"] if row["element_id"] == "opening-1"
    )
    assert wall["rotation_deg"] == 17
    assert opening["element_type"] == "door"
    assert result["architecture_truth_v2"]["valid"] is True


def test_review_fails_closed_when_scan_changes_after_fingerprint() -> None:
    request = payload()
    changed = request.scan.model_dump(mode="python")
    changed["elements"][0]["rotation_deg"] = 18
    result = build_reviewed_store_scan_draft(
        scan_payload=changed,
        expected_scan_fingerprint=request.expected_scan_fingerprint,
        classifications=[],
        operational_elements=annotations(),
    )
    assert result["available"] is False
    assert result["reason"] == "scan_fingerprint_mismatch"
    assert result["store_dna_authority"] is False


def test_review_requires_opening_classification_and_operational_anchors() -> None:
    request = payload()
    result = build_reviewed_store_scan_draft(
        scan_payload=request.scan.model_dump(mode="python"),
        expected_scan_fingerprint=request.expected_scan_fingerprint,
        classifications=[],
        operational_elements=[],
    )
    assert result["reviewed_draft_ready"] is False
    assert "scan_opening_unclassified:opening-1" in result["blockers"]
    assert "scan_picker_entry_annotation_required" in result["blockers"]
    assert "scan_inbound_annotation_required" in result["blockers"]
    assert "scan_dispatch_annotation_required" in result["blockers"]


def test_annotation_schema_rejects_client_authority_fields() -> None:
    raw = payload().model_dump(mode="python")
    for key in (
        "store_dna_approved",
        "maker_checker_approved",
        "production_authority",
        "installation_approval_allowed",
    ):
        with pytest.raises(ValidationError):
            PlanogramStoreScanAnnotationPreviewRequest(**{**raw, key: True})


@pytest.mark.asyncio
async def test_annotation_route_is_mounted_and_never_grants_store_dna_authority() -> None:
    assert "/v1/planogram/store-scan/annotate-preview" in app.openapi()["paths"]
    response = await post_store_scan_annotation_preview(payload(), principal())
    assert response["tenant_id"] == str(TENANT)
    assert response["preview_only"] is True
    assert response["input_authority"] == "fingerprint_bound_human_review_unattested"
    assert response["store_dna_approval_allowed"] is False
    assert response["production_release_allowed"] is False
    assert response["installation_approval_allowed"] is False
    assert response["result"]["reviewed_draft_ready"] is True
    assert response["result"]["store_dna_authority"] is False
