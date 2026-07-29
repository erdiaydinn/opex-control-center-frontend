import unittest

from engine import (
    add_product_to_shelf,
    commit_block_studio,
    generate_planogram,
    generate_default_layout,
    find_product,
    make_shelves,
    normalize_storage,
    validate_planogram,
)


def product(sku, name, brand="Test", category="Beverage", storage="AMBIENT", width=8, height=20, depth=8, sales=10):
    return {
        "sku": sku,
        "product_name": name,
        "brand": brand,
        "category_l1": category,
        "category_l2": category,
        "storage_type": storage,
        "width_cm": width,
        "height_cm": height,
        "depth_cm": depth,
        "weight_kg": 0.2,
        "sales_qty_7d": sales,
    }


def one_aisle_layout(shelves, aisle_id="A"):
    return {
        "store_code": "TEST",
        "aisles": [{
            "aisle_id": aisle_id,
            "row": 1,
            "position": 1,
            "direction": "LTR",
            "modules": [{
                "module_id": 1,
                "side": "L",
                "module_type": "regular_shelf",
                "shelves": shelves,
            }],
        }],
    }


class EngineV3Tests(unittest.TestCase):
    def test_candidate_pool_is_not_truncated_to_first_40(self):
        shelves = make_shelves(45, "AMBIENT", 100, 35, 50, 45)
        for shelf in shelves:
            shelf["assignment_rule"] = {"brand": "OtherBrand"}
        shelves.append(make_shelves(1, "AMBIENT", 100, 35, 50, 45)[0])
        layout = one_aisle_layout(shelves, aisle_id="B")
        result = generate_planogram([product("SKU-1", "Test Drink")], layout, allow_ai_dimensions=False)
        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][-1]["products"]
        self.assertEqual(len(placed), 1)
        self.assertEqual(result["summary"]["unplaced_products"], 0)

    def test_facing_is_shrunk_to_physical_capacity(self):
        shelves = make_shelves(1, "AMBIENT", 20, 35, 50, 45)
        result = generate_planogram([
            product("SKU-2", "High Seller", sales=200, width=6),
        ], one_aisle_layout(shelves, aisle_id="B"), allow_ai_dimensions=False)
        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]
        self.assertEqual(placed["facing"], 3)
        self.assertTrue(placed["facing_reduced"])
        self.assertLessEqual(placed["used_width_cm"], 20)
        self.assertEqual(result["diagnostics"]["summary"]["overfilled_shelf_count"], 0)

    def test_category_rules_and_food_cleaning_shelf_separation(self):
        shelves = make_shelves(2, "AMBIENT", 100, 35, 50, 45)
        shelves[0]["allowed_categories"] = ["Beverage"]
        shelves[1]["blocked_categories"] = ["Beverage"]
        layout = one_aisle_layout(shelves, aisle_id="B")
        result = generate_planogram([
            product("SKU-3", "Cola", category="Beverage", sales=50),
            product("SKU-4", "Detergent", brand="Cleaner", category="Cleaning", sales=50, width=10),
        ], layout, allow_ai_dimensions=False)
        first, second = result["planogram"]["aisles"][0]["modules"][0]["shelves"]
        self.assertEqual([p["sku"] for p in first["products"]], ["SKU-3"])
        self.assertEqual([p["sku"] for p in second["products"]], ["SKU-4"])
        self.assertEqual(result["diagnostics"]["summary"]["strict_rule_violation_count"], 0)

    def test_a_corridor_rejects_non_food(self):
        result = generate_planogram([
            product("SKU-5", "Detergent", brand="Cleaner", category="Cleaning", sales=10),
        ], generate_default_layout(), allow_ai_dimensions=False)
        placed = [
            p for aisle in result["planogram"]["aisles"]
            for module in aisle.get("modules", [])
            for shelf in module.get("shelves", [])
            for p in shelf.get("products", [])
        ]
        self.assertEqual(len(placed), 1)
        self.assertNotEqual(placed[0]["aisle_id"], "A")

    def test_validation_catches_manual_food_cleaning_collision(self):
        layout = one_aisle_layout(make_shelves(1, "AMBIENT", 100, 35, 50, 45), aisle_id="B")
        shelf = layout["aisles"][0]["modules"][0]["shelves"][0]
        shelf["products"] = [
            {**product("SKU-6", "Food", category="Beverage"), "storage_type": "AMBIENT", "merch_group": "FOOD_AMBIENT", "facing": 1, "facing_count": 1},
            {**product("SKU-7", "Detergent", brand="Cleaner", category="Cleaning"), "storage_type": "AMBIENT", "merch_group": "NON_FOOD_ODOR", "facing": 1, "facing_count": 1},
        ]
        for p in shelf["products"]:
            p["used_width_cm"] = 8.8
        shelf["used_width_cm"] = 17.6
        diagnostics = validate_planogram(layout)
        self.assertTrue(any(v["type"] == "food_cleaning_same_shelf" for v in diagnostics["strict_rule_violations"]))

    def test_layout_storage_aliases_are_respected(self):
        layout = {
            "store_code": "TEST",
            "aisles": [{
                "aisle_id": "COLD-1",
                "row": 1,
                "position": 1,
                "modules": [{
                    "module_id": 1,
                    "module_type": "fridge",
                    "storage_type": "CHILLED",
                    "shelves": [{
                        "shelf_no": 1,
                        "storage_type": "CHILLED",
                        "shelf_width_cm": 100,
                        "shelf_height_cm": 35,
                        "shelf_depth_cm": 50,
                        "products": [],
                    }],
                }],
            }],
        }
        result = generate_planogram([
            product("SKU-COLD", "Yogurt", category="Dairy", storage="CHILLED"),
        ], layout, allow_ai_dimensions=False)
        self.assertEqual(result["summary"]["placed"], 1)
        self.assertEqual(result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["allowed_storage_type"], "CHILLED")
        self.assertEqual(normalize_storage("+4 cooler"), "CHILLED")

    def test_explicit_catalog_storage_wins_over_product_name(self):
        result = generate_planogram([
            product("SKU-EXPLICIT", "Frozen-style ambient snack", storage="AMBIENT"),
        ], one_aisle_layout(make_shelves(1, "AMBIENT", 100, 35, 50, 45), aisle_id="B"), allow_ai_dimensions=False)
        self.assertEqual(result["summary"]["placed"], 1)
        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]
        self.assertEqual(placed["storage_type"], "AMBIENT")

    def test_failed_add_to_invalid_target_preserves_existing_product(self):
        layout = generate_planogram([
            product("SKU-KEEP", "Existing Drink"),
        ], generate_default_layout(), allow_ai_dimensions=False)["planogram"]
        before = find_product(layout, "SKU-KEEP")
        before_location = (before["aisle_id"], before["module_id"], before["shelf_no"])

        result = add_product_to_shelf(
            layout,
            product("SKU-KEEP", "Existing Drink"),
            "NOT-FOUND",
            1,
            1,
        )
        after = find_product(result["planogram"], "SKU-KEEP")
        self.assertEqual(result["status"], "error")
        self.assertIsNotNone(after)
        self.assertEqual((after["aisle_id"], after["module_id"], after["shelf_no"]), before_location)

    def test_validation_reports_a_corridor_non_food_violation(self):
        layout = one_aisle_layout(make_shelves(1, "AMBIENT", 100, 35, 50, 45), aisle_id="A")
        shelf = layout["aisles"][0]["modules"][0]["shelves"][0]
        shelf["products"] = [{
            **product("SKU-CLEAN", "Detergent", brand="Cleaner", category="Cleaning"),
            "storage_type": "AMBIENT",
            "merch_group": "NON_FOOD_ODOR",
            "facing": 1,
            "facing_count": 1,
        }]
        shelf["used_width_cm"] = 11
        diagnostics = validate_planogram(layout)
        self.assertTrue(any(v["type"] == "aisle_merchandising_violation" for v in diagnostics["strict_rule_violations"]))

    def test_block_studio_rejects_hard_rule_violation_transactionally(self):
        layout = generate_planogram([
            product("SKU-KEEP", "Existing Drink"),
        ], generate_default_layout(), allow_ai_dimensions=False)["planogram"]
        before = find_product(layout, "SKU-KEEP")
        cleaning = product("SKU-CLEAN", "Detergent", brand="Cleaner", category="Cleaning")

        result = commit_block_studio(
            layout,
            "A",
            1,
            1,
            [{"name": "Invalid block", "width_pct": 100, "products": [cleaning]}],
        )
        self.assertEqual(result["status"], "error")
        self.assertFalse(result["committed"])
        self.assertIsNotNone(find_product(result["planogram"], "SKU-KEEP"))
        self.assertEqual(before["sku"], "SKU-KEEP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
