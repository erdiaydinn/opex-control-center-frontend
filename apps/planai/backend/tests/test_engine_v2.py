import unittest

from engine import generate_planogram, make_shelves


def layout_with_shelves(shelves):
    return {
        "store_code": "TEST",
        "aisles": [{
            "aisle_id": "A",
            "row": 1,
            "position": 1,
            "modules": [{
                "module_id": 1,
                "side": "L",
                "module_type": "regular_shelf",
                "shelves": shelves,
            }],
        }],
    }


def product(sku, category="SNACK", sales=10, width=20):
    return {
        "sku": sku,
        "product_name": f"Product {sku}",
        "brand": "Test",
        "category_l1": category,
        "category_l2": category,
        "storage_type": "AMBIENT",
        "width_cm": width,
        "height_cm": 20,
        "depth_cm": 10,
        "weight_kg": 0.2,
        "sales_qty_7d": sales,
        "case_pack_qty": 1,
    }


class EngineV2Tests(unittest.TestCase):
    def test_preferred_facing_degrades_instead_of_rejecting(self):
        shelves = make_shelves(1, width_cm=100)
        result = generate_planogram([product("HOT", sales=200, width=30)], layout_with_shelves(shelves))
        self.assertEqual(result["summary"]["placed"], 1)
        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]
        self.assertEqual(placed["facing_count"], 3)
        self.assertLessEqual(placed["used_width_cm"], 100)

    def test_allowed_and_blocked_category_rules_are_strict(self):
        shelves = make_shelves(2, width_cm=100)
        shelves[0]["allowed_categories"] = ["BEVERAGE"]
        shelves[1]["blocked_categories"] = ["CLEANING"]
        result = generate_planogram(
            [product("DRINK", "BEVERAGE"), product("BLEACH", "CLEANING")],
            layout_with_shelves(shelves),
        )
        self.assertEqual(result["summary"]["placed"], 1)
        self.assertEqual(result["summary"]["unplaced"], 1)
        self.assertEqual(
            result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"][0]["sku"],
            "DRINK",
        )

    def test_allocator_consolidates_compatible_products(self):
        shelves = make_shelves(4, width_cm=100)
        result = generate_planogram(
            [product(f"S{i}", "SNACK", sales=20 - i, width=10) for i in range(4)],
            layout_with_shelves(shelves),
        )
        occupied = [
            shelf for shelf in result["planogram"]["aisles"][0]["modules"][0]["shelves"]
            if shelf["products"]
        ]
        self.assertLessEqual(len(occupied), 2)
        self.assertEqual(result["summary"]["placed"], 4)

    def test_no_strict_rule_violations(self):
        shelves = make_shelves(2, width_cm=80)
        shelves[0]["allowed_categories"] = ["SNACK"]
        shelves[1]["allowed_categories"] = ["BEVERAGE"]
        result = generate_planogram(
            [product("S", "SNACK", width=25), product("B", "BEVERAGE", width=25)],
            layout_with_shelves(shelves),
        )
        self.assertEqual(result["diagnostics"]["summary"]["strict_rule_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
