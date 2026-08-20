from app.budget_main import app
from app.modules.planogram.retail_intelligence_router import (
    PlanogramRetailIntelligenceRequest,
    RetailRealogramEvent,
)


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


def test_request_requires_commercial_capacity():
    schema = PlanogramRetailIntelligenceRequest.model_json_schema()
    assert "products" in schema["properties"]
    assert "historical_pairs" in schema["properties"]
    assert "realogram_events" in schema["properties"]


def test_embedded_store_mismatch_is_not_representable_as_silent_success():
    schema = PlanogramRetailIntelligenceRequest.model_json_schema()
    store = schema["properties"]["store_code"]
    assert store["pattern"] == "^[A-Za-z0-9._-]+$"
