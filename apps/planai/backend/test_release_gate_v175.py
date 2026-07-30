"""Plonagram V1.7.5 release gate tests.

These tests are intentionally small and deterministic. They prove the release
has decision traces, structured unplaced reasons, and physical capacity math.
"""
from services.physical_capacity_engine import generate_physics_first_planogram
from services.fixture_pool_builder import build_fixture_pools
from services.product_classifier import classify_product


def _store_dna(with_algida=True):
    fixtures = [
        {"fixture_key": "REGULAR_AMBIENT_RACK", "count": 1, "aisle_id": "A", "side": "L", "shelf_width_cm": 100, "shelf_depth_cm": 50, "shelf_height_cm": 35, "shelf_count": 1}
    ]
    if with_algida:
        fixtures.append({"fixture_key": "ALGIDA_FREEZER", "count": 1, "aisle_id": "ICE", "side": "L", "shelf_width_cm": 100, "shelf_depth_cm": 50, "shelf_height_cm": 35, "shelf_count": 1})
    return {"store_code": "TEST", "fixture_inventory": fixtures}


def test_decision_trace_for_placed_product():
    result = generate_physics_first_planogram([
        {"sku": "TEST-20CM", "product_name": "20cm Ambient Test", "storage_type": "AMBIENT", "width_cm": 20, "height_cm": 15, "depth_cm": 10, "weight_kg": 0.2, "sales_qty_7d": 200, "abc_class": "A"}
    ], _store_dna())
    assert result["summary"]["placed"] == 1
    p = result["placements"][0]
    assert p["facing_count"] <= 5
    assert result["trace_summary"]["total_traces"] == 1
    assert result["decision_traces"][0]["decision"] == "PLACED"
    assert result["decision_traces"][0]["capacity_math"]["final_facing"] == p["facing_count"]


def test_decision_trace_for_unplaced_product():
    result = generate_physics_first_planogram([
        {"sku": "TEST-130CM", "product_name": "130cm Ambient Test", "storage_type": "AMBIENT", "width_cm": 130, "height_cm": 15, "depth_cm": 10, "weight_kg": 0.2}
    ], _store_dna())
    assert result["summary"]["unplaced"] == 1
    assert result["unplaced"][0]["reason_code"] == "PRODUCT_TOO_WIDE_FOR_SHELF"
    assert result["decision_traces"][0]["decision"] == "UNPLACED"
    assert result["decision_traces"][0]["reason_code"] == "PRODUCT_TOO_WIDE_FOR_SHELF"
    assert result["decision_traces"][0]["human_action"]


def test_algida_classifier_and_fixture_gate():
    p = classify_product({"sku": "ALGIDA-001", "product_name": "Algida Magnum", "brand": "Algida", "storage_type": "FROZEN", "width_cm": 8, "height_cm": 10, "depth_cm": 5})
    assert p["storage_class"] == "ICE_CREAM"
    no_algida = generate_physics_first_planogram([p], _store_dna(with_algida=False))
    assert no_algida["unplaced"][0]["reason_code"] == "ICE_CREAM_FIXTURE_NOT_AVAILABLE"
    with_algida = generate_physics_first_planogram([p], _store_dna(with_algida=True))
    assert with_algida["summary"]["placed"] == 1
    assert with_algida["placements"][0]["fixture_key"] == "ALGIDA_FREEZER"


if __name__ == "__main__":
    test_decision_trace_for_placed_product()
    test_decision_trace_for_unplaced_product()
    test_algida_classifier_and_fixture_gate()
    print("✅ V1.7.5 release gate tests passed")
