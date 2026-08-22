from __future__ import annotations

from copy import deepcopy
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.store_scan import normalize_store_scan
from app.modules.planogram.store_scan_annotation import build_reviewed_store_scan_draft
from app.modules.planogram.store_scan_review_router import post_store_scan_annotation_preview
from app.modules.planogram.store_scan_review_schemas import (
    PlanogramStoreScanAnnotationPreviewRequest,
)

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


def build(request: PlanogramStoreScanAnnotationPreviewRequest) -> dict[str, object]:
    return build_reviewed_store_scan_draft(
        scan_payload=request.scan.model_dump(mode="python"),
        expected_scan_fingerprint=request.expected_scan_fingerprint,
        classifications=[row.model_dump(mode="python") for row in request.classifications],
        operational_elements=[
            row.model_dump(mode="python") for row in request.operational_elements
        ],
        review_note=request.review_note,
        uncertainty_resolutions=[
            row.model_dump(mode="python") for row in request.uncertainty_resolutions
        ],
    )


def test_reviewed_scan_preserves_angle_and_produces_non_authoritative_v2_draft() -> None:
    result = build(payload())

    assert result["available"] is True
    assert result["reviewed_draft_ready"] is True
    assert result["store_dna_authority"] is False
    assert result["maker_checker_approved"] is False
    assert result["production_authority"] is False
    assert result["installation_approval_allowed"] is False
    assert result["auto_store_dna_promotion_allowed"] is False
    assert result["uncertainty_review"]["total"] == 0
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


def test_uncertain_scan_requires_explicit_resolution_and_can_confirm_fixture() -> None:
    raw = deepcopy(scan())
    raw["elements"].append(
        {
            "element_id": "uncertain-fixture",
            "element_type": "fixture",
            "x_m": 9,
            "y_m": 6,
            "width_m": 1.0,
            "depth_m": 0.5,
            "rotation_deg": 11,
            "confidence": 0.4,
        }
    )
    fingerprint = normalize_store_scan(raw)["scan_fingerprint"]
    unresolved = build_reviewed_store_scan_draft(
        scan_payload=raw,
        expected_scan_fingerprint=fingerprint,
        classifications=[{"element_id": "opening-1", "classified_type": "door", "clearance_m": 0}],
        operational_elements=annotations(),
    )
    assert unresolved["reviewed_draft_ready"] is False
    assert "scan_uncertainty_unresolved:uncertain-fixture" in unresolved["blockers"]
    assert unresolved["uncertainty_review"]["unresolved"] == 1

    confirmed = build_reviewed_store_scan_draft(
        scan_payload=raw,
        expected_scan_fingerprint=fingerprint,
        classifications=[{"element_id": "opening-1", "classified_type": "door", "clearance_m": 0}],
        operational_elements=annotations(),
        uncertainty_resolutions=[
            {
                "element_id": "uncertain-fixture",
                "decision": "confirm",
                "classified_type": "fixture",
            }
        ],
    )
    assert confirmed["reviewed_draft_ready"] is True
    assert confirmed["uncertainty_review"]["confirmed"] == 1
    fixture = next(
        row
        for row in confirmed["reviewed_recognized_fixtures"]
        if row["element_id"] == "uncertain-fixture"
    )
    assert fixture["human_uncertainty_confirmed"] is True
    assert fixture["confidence"] == pytest.approx(0.4)
    assert confirmed["store_dna_authority"] is False
    assert confirmed["production_authority"] is False


def test_unknown_uncertainty_confirm_requires_explicit_type_and_reject_is_safe() -> None:
    raw = deepcopy(scan())
    raw["elements"].append(
        {
            "element_id": "unknown-1",
            "element_type": "unknown",
            "x_m": 10,
            "y_m": 7,
            "width_m": 0.8,
            "depth_m": 0.4,
            "rotation_deg": 0,
            "confidence": 0.97,
        }
    )
    fingerprint = normalize_store_scan(raw)["scan_fingerprint"]
    missing_type = build_reviewed_store_scan_draft(
        scan_payload=raw,
        expected_scan_fingerprint=fingerprint,
        classifications=[{"element_id": "opening-1", "classified_type": "door", "clearance_m": 0}],
        operational_elements=annotations(),
        uncertainty_resolutions=[{"element_id": "unknown-1", "decision": "confirm"}],
    )
    assert missing_type["reviewed_draft_ready"] is False
    assert "scan_uncertainty_type_required:unknown-1" in missing_type["blockers"]

    rejected = build_reviewed_store_scan_draft(
        scan_payload=raw,
        expected_scan_fingerprint=fingerprint,
        classifications=[{"element_id": "opening-1", "classified_type": "door", "clearance_m": 0}],
        operational_elements=annotations(),
        uncertainty_resolutions=[{"element_id": "unknown-1", "decision": "reject"}],
    )
    assert rejected["reviewed_draft_ready"] is True
    assert rejected["uncertainty_review"]["rejected"] == 1
    assert all(
        row["element_id"] != "unknown-1"
        for row in rejected["reviewed_store_dna_v2_preview"]["architecture"]["elements"]
    )


def test_annotation_schema_rejects_duplicate_or_forged_uncertainty_authority() -> None:
    raw = payload().model_dump(mode="python")
    for key in (
        "store_dna_approved",
        "maker_checker_approved",
        "production_authority",
        "installation_approval_allowed",
    ):
        with pytest.raises(ValidationError):
            PlanogramStoreScanAnnotationPreviewRequest(**{**raw, key: True})
    with pytest.raises(ValidationError):
        PlanogramStoreScanAnnotationPreviewRequest(
            **{
                **raw,
                "uncertainty_resolutions": [
                    {"element_id": "x", "decision": "reject"},
                    {"element_id": "x", "decision": "reject"},
                ],
            }
        )
    with pytest.raises(ValidationError):
        PlanogramStoreScanAnnotationPreviewRequest(
            **{
                **raw,
                "uncertainty_resolutions": [
                    {"element_id": "x", "decision": "reject", "classified_type": "fixture"}
                ],
            }
        )


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
