from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.core.security import Principal
from app.modules.planogram.shelf_scan_router import post_planogram_shelf_scan_preview
from app.modules.planogram.shelf_scan_schemas import PlanogramShelfScanPreviewRequest

TENANT_ID = UUID("11111111-1111-4111-8111-111111111111")


def plan() -> dict[str, object]:
    return {
        "aisles": [
            {
                "aisle_id": "A",
                "modules": [
                    {
                        "module_id": "1",
                        "shelves": [
                            {
                                "shelf_no": "1",
                                "products": [
                                    {"sku": "MILK", "facing_count": 2},
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }


def payload() -> PlanogramShelfScanPreviewRequest:
    return PlanogramShelfScanPreviewRequest(
        plan_payload=plan(),
        shelves=[
            {
                "aisle_id": "A",
                "module_id": "1",
                "shelf_no": "1",
                "source_ref": "image://scan-1",
                "coverage_complete": True,
                "image_quality_score": 0.95,
                "occlusion_pct": 5.0,
            }
        ],
        observations=[
            {
                "sku": "milk",
                "aisle_id": "A",
                "module_id": "1",
                "shelf_no": "1",
                "facing_count": 2,
                "confidence": 0.99,
                "source_ref": "detector://scan-1/milk",
            }
        ],
    )


def principal() -> Principal:
    return Principal(
        subject="planogram-reviewer",
        tenant_id=TENANT_ID,
        roles=("planogram_editor",),
        permissions=("action:planogram:edit",),
        auth_mode="test",
    )


def test_shelf_scan_route_is_mounted_in_production_asgi_composition() -> None:
    paths = app.openapi()["paths"]
    assert "/v1/planogram/shelf-scan-preview" in paths
    assert "post" in paths["/v1/planogram/shelf-scan-preview"]


def test_shelf_scan_request_rejects_client_authority_escalation_fields() -> None:
    base = payload().model_dump(mode="python")
    for field, value in (
        ("production_evidence", True),
        ("field_truth", True),
        ("field_truth_write_allowed", True),
        ("auto_accept_allowed", True),
        ("auto_correct_allowed", True),
        ("finance_approved", True),
    ):
        with pytest.raises(ValidationError):
            PlanogramShelfScanPreviewRequest(**{**base, field: value})


def test_nested_scan_evidence_rejects_unknown_truth_fields() -> None:
    base = payload().model_dump(mode="python")
    base["shelves"][0]["field_truth"] = True
    with pytest.raises(ValidationError):
        PlanogramShelfScanPreviewRequest(**base)


@pytest.mark.asyncio
async def test_shelf_scan_route_hardcodes_non_truth_authority() -> None:
    response = await post_planogram_shelf_scan_preview(payload(), principal())

    assert response["tenant_id"] == str(TENANT_ID)
    assert response["preview_only"] is True
    assert response["production_evidence"] is False
    assert response["field_truth_write_allowed"] is False
    assert response["auto_accept_allowed"] is False
    assert response["auto_correct_allowed"] is False
    assert response["human_review_required_for_deviation_action"] is True
    assert response["result"]["field_truth"] is False
    assert response["result"]["auto_accept_allowed"] is False
    assert response["result"]["auto_correct_allowed"] is False
    assert response["result"]["compliant_count"] == 1


def test_openapi_request_schema_does_not_expose_truth_or_approval_inputs() -> None:
    schema = PlanogramShelfScanPreviewRequest.model_json_schema()
    properties = schema["properties"]
    forbidden = {
        "production_evidence",
        "field_truth",
        "field_truth_write_allowed",
        "auto_accept_allowed",
        "auto_correct_allowed",
        "finance_approved",
        "installation_approval_allowed",
        "capex_approval_allowed",
    }
    assert forbidden.isdisjoint(properties)
