from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.field_promotion_routes import PromotionCreate
from app.modules.field_intelligence.planogram_compliance_promotion import _candidate
from app.modules.planogram.execution import (
    PlanogramExecutionError,
    evaluate_compliance,
    plan_fingerprint,
    validate_plan_payload,
)
from app.modules.planogram.execution_schemas import PlanogramPlanDraftRequest

PLAN_ID = "11111111-1111-4111-8111-111111111111"
DNA_ID = UUID("22222222-2222-4222-8222-222222222222")


def plan() -> dict[str, object]:
    return {
        "store_code": "FULYA",
        "aisles": [
            {
                "aisle_id": "A01",
                "modules": [
                    {
                        "module_id": "A01-L01",
                        "side": "L",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "products": [
                                    {"sku": "SKU-1", "facing_count": 3},
                                    {"sku": "SKU-2", "facing_count": 1},
                                ],
                            }
                        ],
                    }
                ],
            }
        ],
    }


def candidate(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "plan_version_id": PLAN_ID,
        "sku": "SKU-1",
        "actual_aisle_id": "A01",
        "actual_module_id": "A01-L01",
        "actual_shelf_no": "1",
        "actual_facing_count": 3,
    }
    payload.update(overrides)
    return payload


def test_plan_fingerprint_is_deterministic_and_requires_real_placements() -> None:
    assert validate_plan_payload(plan()) == plan()
    assert plan_fingerprint(plan()) == plan_fingerprint(plan())
    with pytest.raises(PlanogramExecutionError, match="plan_payload_requires_aisles"):
        plan_fingerprint({"aisles": []})


def test_exact_location_and_facing_is_compliant() -> None:
    result = evaluate_compliance(plan(), candidate())
    assert result["result"] == "compliant"
    assert result["deviation_codes"] == []
    assert result["expected_locations"] == [
        {
            "aisle_id": "A01",
            "module_id": "A01-L01",
            "shelf_no": "1",
            "facing_count": 3,
        }
    ]


def test_location_and_facing_deviations_are_explicit() -> None:
    result = evaluate_compliance(
        plan(),
        candidate(
            actual_module_id="A01-R02",
            actual_shelf_no="3",
            actual_facing_count=1,
        ),
    )
    assert result["result"] == "deviation"
    assert set(result["deviation_codes"]) == {
        "module_mismatch",
        "shelf_mismatch",
        "facing_mismatch",
    }


def test_unknown_sku_is_deviation_not_new_truth() -> None:
    result = evaluate_compliance(plan(), candidate(sku="UNEXPECTED"))
    assert result["result"] == "deviation"
    assert result["deviation_codes"] == ["sku_not_in_approved_plan"]


def test_field_compliance_candidate_remains_non_truth_handoff() -> None:
    field_candidate = _candidate(candidate(), "FULYA")
    assert field_candidate["candidate_type"] == "planogram_compliance_observation"
    assert field_candidate["location_id"] == "FULYA"
    assert field_candidate["planogram_truth_write_permitted"] is False
    assert field_candidate["requires_planogram_assignment_validation"] is True


def test_field_promotion_contract_accepts_compliance_adapter() -> None:
    payload = PromotionCreate(
        evidence_id=UUID("33333333-3333-4333-8333-333333333333"),
        adapter_key="planogram.compliance_observation.v1",
    )
    assert payload.adapter_key == "planogram.compliance_observation.v1"


def test_plan_draft_api_does_not_expose_physical_truth_attestation() -> None:
    schema = PlanogramPlanDraftRequest.model_json_schema()
    assert "physical_truth_attested" not in schema["properties"]
    request = PlanogramPlanDraftRequest(
        store_dna_version_id=DNA_ID,
        store_code="FULYA",
        plan_payload=plan(),
    )
    assert not hasattr(request, "physical_truth_attested")
    with pytest.raises(ValidationError):
        PlanogramPlanDraftRequest(
            store_dna_version_id=DNA_ID,
            store_code="FULYA",
            plan_payload=plan(),
            optimizer_fingerprint="not-a-sha",
        )


def test_execution_routes_are_in_canonical_core_contract() -> None:
    paths = set(app.openapi()["paths"])
    required = {
        "/v1/planogram/execution/plans",
        "/v1/planogram/execution/plans/{plan_version_id}",
        "/v1/planogram/execution/plans/{plan_version_id}/submit",
        "/v1/planogram/execution/plans/{plan_version_id}/approve",
        "/v1/planogram/execution/plans/{plan_version_id}/reject",
        "/v1/planogram/execution/assignments",
        "/v1/planogram/execution/assignments/{assignment_id}/acknowledge",
        "/v1/planogram/execution/assignments/{assignment_id}/close",
        "/v1/planogram/execution/assignments/{assignment_id}/compliance",
    }
    assert required <= paths
