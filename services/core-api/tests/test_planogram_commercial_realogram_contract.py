from app.modules.planogram.commercial_router import (
    CommercialSubstitutionEdge,
    PlanogramCommercialPreviewRequest,
)
from app.modules.planogram.realogram_router import (
    PlanogramTemporalRealogramRequest,
    TemporalRealogramEvent,
)


def test_commercial_contract_requires_explicit_space_capacity():
    try:
        PlanogramCommercialPreviewRequest(
            store_code="STORE-1",
            products=[{"sku": "A"}],
        )
    except ValueError as exc:
        assert "category_capacity_cm or total_shelf_width_cm is required" in str(exc)
    else:
        raise AssertionError("commercial preview accepted missing capacity")


def test_commercial_substitution_contract_has_no_identity_fields():
    properties = CommercialSubstitutionEdge.model_json_schema()["properties"]
    assert set(properties) == {
        "sku_a",
        "sku_b",
        "cross_elasticity",
        "source_ref",
    }
    for forbidden in ("customer_id", "order_id", "email", "phone"):
        assert forbidden not in properties


def test_temporal_event_contract_is_operational_not_customer_identity():
    properties = TemporalRealogramEvent.model_json_schema()["properties"]
    for forbidden in (
        "customer_id",
        "customer_name",
        "email",
        "phone",
        "address",
    ):
        assert forbidden not in properties
    assert {"event_type", "observed_at", "sku", "source_ref"} <= set(properties)


def test_temporal_request_caps_events_and_requires_store_scope_key():
    properties = PlanogramTemporalRealogramRequest.model_json_schema()["properties"]
    assert "store_code" in properties
    assert properties["events"]["maxItems"] == 100000
