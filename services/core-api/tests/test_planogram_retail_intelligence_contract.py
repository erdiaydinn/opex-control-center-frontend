import pytest
from pydantic import ValidationError

from app.budget_main import app
from app.modules.planogram.retail_intelligence_router import (
    PlanogramRetailIntelligenceRequest,
    RetailRealogramEvent,
)


def _request(**overrides):
    payload = {
        "store_code": "STORE-1",
        "products": [{"sku": "A"}],
        "layout": {"store_code": "STORE-1"},
        "store_dna": {"store_code": "STORE-1"},
        "total_shelf_width_cm": 100,
    }
    payload.update(overrides)
    return payload


def test_retail_intelligence_route_is_preview_only_surface():
    paths = app.openapi()["paths"]
    assert "/v1/planogram/retail-intelligence-preview" in paths
    operation = paths["/v1/planogram/retail-intelligence-preview"]["post"]
    assert operation["tags"] == ["planogram"]


def test_request_contract_forbids_unmodeled_event_identity_fields():
    event_schema = RetailRealogramEvent.model_json_schema()
    assert event_schema["additionalProperties"] is False
    for forbidden in ("customer_id", "email", "phone", "order_id"):
        assert forbidden not in event_schema["properties"]


def test_request_exposes_real_repository_evidence_inputs():
    schema = PlanogramRetailIntelligenceRequest.model_json_schema()
    properties = schema["properties"]
    for field in (
        "products",
        "historical_pairs",
        "realogram_events",
        "order_baskets",
        "blind_candidate_a",
        "blind_candidate_b",
        "shelf_scan_shelves",
        "shelf_scan_observations",
    ):
        assert field in properties


def test_blind_candidates_require_pair_and_anonymous_baskets():
    candidate = {"planogram": {"aisles": [{}]}}
    with pytest.raises(ValidationError):
        PlanogramRetailIntelligenceRequest.model_validate(
            _request(blind_candidate_a=candidate)
        )
    with pytest.raises(ValidationError):
        PlanogramRetailIntelligenceRequest.model_validate(
            _request(
                blind_candidate_a=candidate,
                blind_candidate_b=candidate,
            )
        )


def test_shelf_scan_observations_require_shelf_evidence():
    with pytest.raises(ValidationError):
        PlanogramRetailIntelligenceRequest.model_validate(
            _request(
                shelf_scan_observations=[
                    {
                        "sku": "A",
                        "aisle_id": "A",
                        "module_id": "1",
                        "shelf_no": "1",
                        "facing_count": 1,
                        "confidence": 0.99,
                    }
                ]
            )
        )


def test_embedded_store_mismatch_is_not_representable_as_silent_success():
    schema = PlanogramRetailIntelligenceRequest.model_json_schema()
    store = schema["properties"]["store_code"]
    assert store["pattern"] == "^[A-Za-z0-9._-]+$"
