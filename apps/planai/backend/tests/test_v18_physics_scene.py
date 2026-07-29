import os
import sys

# Allow running this file directly with:
#   python .\tests\test_v18_physics_scene.py
BACKEND_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_ROOT not in sys.path:
    sys.path.insert(0, BACKEND_ROOT)

from services.physical_capacity_engine import can_place_physical, generate_physics_first_planogram
from services.scene_payload_builder import build_scene_payload


def shelf(storage="AMBIENT", width=100, depth=50, height=35):
    return {"allowed_storage_type": storage, "shelf_width_cm": width, "shelf_depth_cm": depth, "shelf_height_cm": height, "max_weight_kg": 45, "used_width_cm": 0, "used_weight_kg": 0, "products": []}


def product(storage="AMBIENT", width=10, depth=10, height=10, facing=1, name="Test"):
    return {"sku": "SKU1", "product_name": name, "storage_type": storage, "width_cm": width, "depth_cm": depth, "height_cm": height, "facing_count": facing, "weight_kg": 0.2}


def test_100cm_shelf_20cm_product_max_5_facing():
    ok, info = can_place_physical(product(width=20, facing=99), shelf(width=100))
    assert ok
    assert info["final_facing"] == 5


def test_storage_mismatch_rejected():
    ok, info = can_place_physical(product(storage="CHILLED"), shelf(storage="FROZEN"))
    assert not ok
    assert info["reason_code"] == "STORAGE_MISMATCH"


def test_algida_not_ambient():
    ok, info = can_place_physical(product(storage="AMBIENT", name="Algida Magnum"), shelf(storage="AMBIENT"))
    assert not ok
    assert info["reason_code"] == "STORAGE_MISMATCH"


def test_odor_nonfood_not_with_food():
    s = shelf()
    s["products"] = [product(name="Eti Bisküvi")]
    ok, info = can_place_physical(product(name="Domestos Çamaşır Suyu"), s)
    assert not ok
    assert info["reason_code"] == "ODOR_NONFOOD_WITH_FOOD_SAME_SHELF"


def test_scene_payload_builder():
    plan = {"store_code": "TEST", "aisles": [{"aisle_id": "A", "modules": [{"module_id": 1, "module_type": "regular_shelf", "module_width_cm": 100, "module_depth_cm": 50, "module_height_cm": 210, "shelves": [{**shelf(), "shelf_no": 1, "products": [product(name="Eti Burçak")]}]}]}]}
    payload = build_scene_payload(plan)
    assert payload["summary"]["fixture_count"] == 1
    assert payload["summary"]["product_tile_count"] == 1


def test_generate_physics_first_contract_still_exists():
    dna = {"store_code": "TEST", "fixture_inventory": [{"fixture_key": "REGULAR_AMBIENT_RACK", "count": 1, "aisle_id": "A", "side": "L", "shelf_width_cm": 100, "shelf_depth_cm": 50, "shelf_height_cm": 35, "shelf_count": 1}]}
    result = generate_physics_first_planogram([product(width=20, facing=99)], dna)
    assert result["summary"]["placed"] == 1
    assert result["placements"][0]["facing_count"] <= 5


if __name__ == "__main__":
    tests = [name for name in sorted(globals()) if name.startswith("test_")]
    for name in tests:
        globals()[name]()
        print(f"✓ {name}")
    print("✅ V1.8 physics / scene compatibility tests passed")
