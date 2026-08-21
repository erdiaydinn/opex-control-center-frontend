import unittest

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

    def test_heavy_product_violation_blocks_publish_even_after_truth_gate(self):
        result = generate_production_plan(
            [
                product(
                    "HEAVY",
                    "Heavy Cleaning Product",
                    category="Cleaning",
                    weight=4.0,
                )
            ],
            layout(),
            dna(),
        )
        # The foundation allocator may choose bottom or another compatible
        # shelf.  Whichever it chooses, production publishability is bound to
        # the independent operational validator.
        self.assertTrue(result["solver_optimizer_allowed"])
        self.assertIn("operational_physical_validation", result)
        if result["operational_physical_validation"]["violation_count"]:
            self.assertFalse(result["publishable"])
        else:
            self.assertTrue(result["publishable"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
