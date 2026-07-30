from services.physical_capacity_engine import generate_physics_first_planogram
from services.fixture_pool_builder import build_fixture_pools
from services.product_classifier import classify_product


def base_dna(**extra):
    return {
        "store_code": "TEST",
        "layout_objects": [],
        "aisles": [
            {
                "aisle_id": "A",
                "left_modules": [
                    {
                        "module_id": "A-L1",
                        "fixture_type": "steel_rack",
                        "side": "L",
                        "dimensions": {"width": 100, "depth": 50, "height": 210},
                        "shelves": [
                            {"shelf_no": 1, "dimensions": {"width_cm": 100, "depth_cm": 50, "height_cm": 35}, "max_weight_kg": 45, "zone_type": "eye", "products": []}
                        ],
                    }
                ],
                "right_modules": [],
            }
        ],
        **extra,
    }


def test_100cm_shelf_8cm_product_max_12_facing():
    dna = base_dna()
    product = {"sku": "P8", "product_name": "Biskuvi", "brand": "Test", "storage_type": "AMBIENT", "width_cm": 8, "depth_cm": 5, "height_cm": 12, "sales_qty_7d": 999}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 1
    placed = result["placements"][0]
    assert placed["facing"] <= 12, placed
    assert placed["used_width_cm"] <= 100


def test_100cm_shelf_20cm_product_max_5_facing():
    dna = base_dna()
    product = {"sku": "P20", "product_name": "Kutu Ürün", "brand": "Test", "storage_type": "AMBIENT", "width_cm": 20, "depth_cm": 10, "height_cm": 20, "sales_qty_7d": 999}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 1
    placed = result["placements"][0]
    assert placed["facing"] <= 5
    assert placed["used_width_cm"] <= 100


def test_too_wide_product_unplaced():
    dna = base_dna()
    product = {"sku": "P130", "product_name": "Çok Geniş Ürün", "brand": "Test", "storage_type": "AMBIENT", "width_cm": 130, "depth_cm": 10, "height_cm": 20}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["unplaced"] == 1
    assert result["unplaced"][0]["reason_code"] == "PRODUCT_TOO_WIDE_FOR_SHELF"


def test_algida_never_goes_to_ambient_without_ice_cream_fixture():
    dna = base_dna()
    product = {"sku": "ALG1", "product_name": "Algida Magnum", "brand": "Algida", "storage_type": "FROZEN", "width_cm": 8, "depth_cm": 5, "height_cm": 12}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 0
    assert result["unplaced"][0]["reason_code"] == "ICE_CREAM_FIXTURE_NOT_AVAILABLE"


def test_algida_goes_to_algida_fixture():
    dna = base_dna(fixture_instances=[{"id": "ALGIDA_1", "fixture_type": "algida_freezer", "count": 1, "width_cm": 120, "depth_cm": 70, "height_cm": 190, "shelf_count": 4}])
    product = {"sku": "ALG1", "product_name": "Algida Magnum", "brand": "Algida", "width_cm": 8, "depth_cm": 5, "height_cm": 12}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 1
    assert result["placements"][0]["fixture_key"] == "ALGIDA_FREEZER"


def test_chilled_never_goes_to_frozen_or_ambient():
    dna = base_dna(fixture_instances=[{"id": "FROZEN_1", "fixture_type": "martek_frozen_minus18", "count": 1, "width_cm": 120, "depth_cm": 70, "height_cm": 190, "shelf_count": 4}])
    product = {"sku": "MILK1", "product_name": "Süt 1L", "brand": "Pınar", "storage_type": "CHILLED", "width_cm": 8, "depth_cm": 8, "height_cm": 20}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 0
    assert result["unplaced"][0]["reason_code"] == "FIXTURE_NOT_AVAILABLE"


def test_deterjan_ambient_but_not_next_to_food_same_shelf():
    dna = base_dna()
    products = [
        {"sku": "FOOD1", "product_name": "Eti Burçak", "brand": "Eti", "storage_type": "AMBIENT", "width_cm": 10, "depth_cm": 5, "height_cm": 12, "sales_qty_7d": 10},
        {"sku": "DET1", "product_name": "Domestos Çamaşır Suyu", "brand": "Domestos", "storage_type": "AMBIENT", "width_cm": 10, "depth_cm": 5, "height_cm": 20, "sales_qty_7d": 5},
    ]
    result = generate_physics_first_planogram(products, dna)
    assert result["summary"]["placed"] == 1
    assert result["summary"]["unplaced"] == 1
    assert result["unplaced"][0]["reason_code"] in {"FOOD_ODOR_ADJACENCY_BLOCKED", "CAPACITY_NOT_ENOUGH"}


def test_produce_needs_produce_fixture():
    dna = base_dna()
    product = {"sku": "PATATES", "product_name": "Patates Kg", "brand": "Fresh", "width_cm": 20, "depth_cm": 20, "height_cm": 15}
    result = generate_physics_first_planogram([product], dna)
    assert result["summary"]["placed"] == 0
    assert result["unplaced"][0]["reason_code"] == "FRESH_PRODUCE_FIXTURE_MISSING"


if __name__ == "__main__":
    tests = [name for name in sorted(globals()) if name.startswith("test_")]
    for name in tests:
        globals()[name]()
        print(f"✓ {name}")
    print("✅ V1.7.4 physics-first engine tests passed")
