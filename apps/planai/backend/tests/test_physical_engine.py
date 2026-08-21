import unittest
from copy import deepcopy

from physical_engine import generate_production_plan, prepare_production_products


def product(
    sku,
    name,
    *,
    category="Beverages",
    storage="RAF",
    weight=0.5,
    dimensions=True,
    image=True,
):
    row = {
        "sku": sku,
        "product_name": name,
        "brand": "Test",
        "category_l1": category,
        "category_l2": category,
        "storage_type": storage,
        "weight_kg": weight,
        "sales_qty_7d": 20,
        "image_url": f"https://example.test/{sku}.jpg" if image else "",
    }
    if dimensions:
        row.update({"width_cm": 8, "height_cm": 20, "depth_cm": 8})
    return row


def layout():
    return {
        "store_code": "TEST",
        "aisles": [
            {
                "aisle_id": "A",
                "row": 1,
                "position": 1,
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "bottom",
                                "allowed_storage_type": "AMBIENT",
                                "products": [],
                            },
                            {
                                "shelf_no": 2,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "eye",
                                "allowed_storage_type": "AMBIENT",
                                "products": [],
                            },
                        ],
                    },
                    {
                        "module_id": 2,
                        "side": "R",
                        "module_type": "regular_shelf",
                        "storage_type": "AMBIENT",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 100,
                                "shelf_height_cm": 35,
                                "shelf_depth_cm": 50,
                                "max_weight_kg": 45,
                                "zone_type": "bottom",
                                "allowed_storage_type": "AMBIENT",
                                "products": [],
                            }
                        ],
                    },
                ],
            },
            {
                "aisle_id": "PALLET",
                "row": 2,
                "position": 1,
                "modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "module_type": "pallet",
                        "fixture_type": "pallet",
                        "storage_type": "PALLET",
                        "shelves": [
                            {
                                "shelf_no": 1,
                                "shelf_width_cm": 120,
                                "shelf_height_cm": 120,
                                "shelf_depth_cm": 100,
                                "max_weight_kg": 800,
                                "zone_type": "bottom",
                                "allowed_storage_type": "PALLET",
                                "products": [],
                            }
                        ],
                    }
                ],
            },
        ],
    }


def dna(width=1.2):
    return {
        "source": "user_approved_store_dna",
        "store_code": "TEST",
        "picker_aisle_width_m": width,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [{"module_id": 1, "side": "L", "shelf_count": 2}],
                "right_modules": [{"module_id": 2, "side": "R", "shelf_count": 1}],
            }
        ],
    }


class PhysicalEngineTests(unittest.TestCase):
    def test_production_gate_never_uses_ai_dimensions(self):
        result = generate_production_plan(
            [product("MISSING", "Product without dimensions", dimensions=False)],
            layout(),
            dna(),
        )
        self.assertFalse(result["production_ready"])
        self.assertFalse(result["solver_optimizer_allowed"])
        self.assertEqual(result["summary"]["placed"], 0)
        self.assertEqual(result["unplaced"][0]["reason"], "approved_dimensions_missing")
        self.assertIn(
            "approved_dimension_coverage_below_100_pct",
            result["physical_truth"]["blockers"],
        )

    def test_large_water_is_adapted_to_pallet_without_changing_temperature_truth(self):
        prepared = prepare_production_products(
            [product("WATER", "Water 6 x 1.5 L")]
        )[0]
        self.assertEqual(prepared["temperature_zone"], "AMBIENT")
        self.assertEqual(prepared["required_fixture_class"], "PALLET")
        self.assertEqual(prepared["storage_type"], "PALLET")

    def test_five_litre_detergent_stays_regular_fixture(self):
        prepared = prepare_production_products(
            [
                product(
                    "DET",
                    "Çamaşır Deterjanı 5 L",
                    category="Cleaning",
                    weight=5.0,
                )
            ]
        )[0]
        self.assertEqual(prepared["required_fixture_class"], "REGULAR_SHELF")
        self.assertEqual(prepared["storage_type"], "AMBIENT")
        self.assertTrue(prepared["requires_bottom_shelf"])

    def test_truth_ready_allows_deterministic_allocator(self):
        result = generate_production_plan(
            [
                product("SNACK", "Ambient Snack", category="Snacks"),
                product("WATER", "Water 6 x 1.5 L"),
            ],
            layout(),
            dna(),
        )
        self.assertTrue(result["solver_optimizer_allowed"])
        self.assertEqual(result["physical_truth"]["blockers"], [])
        self.assertEqual(result["summary"]["placed"], 2)
        water = None
        for aisle in result["planogram"]["aisles"]:
            for module in aisle.get("modules", []):
                for shelf in module.get("shelves", []):
                    for placed in shelf.get("products", []):
                        if placed.get("sku") == "WATER":
                            water = (aisle, module, shelf, placed)
        self.assertIsNotNone(water)
        self.assertEqual(water[0]["aisle_id"], "PALLET")
        self.assertEqual(water[3]["storage_type"], "PALLET")
        self.assertTrue(result["production_capacity_reconciliation"]["valid"])

    def test_heavy_product_is_placed_on_bottom_before_scoring(self):
        # A is deliberately a food/front-zone aisle in the merchandising rules.
        # Use an approved non-food aisle so this test isolates the heavy-bottom
        # physical invariant instead of trying to bypass food/chemical separation.
        heavy_layout = deepcopy(layout())
        heavy_layout["aisles"][0]["aisle_id"] = "I"
        heavy_dna = deepcopy(dna())
        heavy_dna["aisle_module_config"][0]["aisle_id"] = "I"

        result = generate_production_plan(
            [
                product(
                    "HEAVY",
                    "Heavy Cleaning Product",
                    category="Cleaning",
                    weight=4.0,
                )
            ],
            heavy_layout,
            heavy_dna,
        )
        self.assertTrue(
            result["publishable"],
            result["operational_physical_validation"],
        )
        placed = [
            (shelf, row)
            for aisle in result["planogram"]["aisles"]
            for module in aisle.get("modules", [])
            for shelf in module.get("shelves", [])
            for row in shelf.get("products", [])
            if row.get("sku") == "HEAVY"
        ]
        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0][0]["zone_type"], "bottom")
        self.assertEqual(
            result["operational_physical_validation"]["violation_count"],
            0,
        )
        self.assertTrue(result["production_capacity_reconciliation"]["valid"])

    def test_500g_product_does_not_become_500kg(self):
        row = product("GRAM", "Snack", category="Snacks")
        row.pop("weight_kg")
        row.update(
            {
                "product_weight_value": 500,
                "product_weight_unit": "g",
            }
        )
        prepared = prepare_production_products([row])[0]
        self.assertEqual(prepared["weight_kg"], 0.5)
        self.assertFalse(prepared["requires_bottom_shelf"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
