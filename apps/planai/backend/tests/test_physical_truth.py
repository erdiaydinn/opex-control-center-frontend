import unittest

from physical_truth import (
    clone_with_physical_truth,
    parse_pack_metrics,
    physical_constraint_reason,
    physical_scale_eligible,
    production_acceptance_report,
    required_fixture_class,
    requires_bottom_shelf,
    requires_pallet_fixture,
    store_dna_truth_report,
)


def product(
    sku,
    name,
    *,
    brand="Test",
    category="Beverages",
    storage="RAF",
    width=8,
    height=20,
    depth=8,
    weight=0.5,
    dimension_source="master",
    image=True,
):
    return {
        "sku": sku,
        "product_name": name,
        "brand": brand,
        "category_l1": category,
        "category_l2": category,
        "catalog_storage_condition_raw": storage,
        "width_cm": width,
        "height_cm": height,
        "depth_cm": depth,
        "weight_kg": weight,
        "dimension_source": dimension_source,
        "image_url": f"https://example.test/{sku}.jpg" if image else "",
        "catalog_global_product_id": f"CAT-{sku}",
    }


def physical_layout(include_pallet=True):
    aisles = [
        {
            "aisle_id": "A",
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
    ]
    if include_pallet:
        aisles.append(
            {
                "aisle_id": "PALLET",
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
            }
        )
    return {"store_code": "TEST", "aisles": aisles}


def measured_dna(width=1.2):
    return {
        "source": "user_approved_store_dna",
        "store_code": "TEST",
        "picker_aisle_width_m": width,
        "aisle_module_config": [
            {
                "aisle_id": "A",
                "left_modules": [
                    {
                        "module_id": 1,
                        "side": "L",
                        "fixture_type": "steel_rack",
                        "shelf_count": 2,
                    }
                ],
                "right_modules": [
                    {
                        "module_id": 2,
                        "side": "R",
                        "fixture_type": "steel_rack",
                        "shelf_count": 2,
                    }
                ],
            }
        ],
    }


class PhysicalTruthTests(unittest.TestCase):
    def test_large_beverage_multipacks_require_pallet(self):
        cases = [
            ("Water 6 x 1.5 L", 9.0),
            ("Water 12 x 500 ml", 6.0),
            ("Cola 4x1 L", 4.0),
            ("Water 5 L", 5.0),
        ]
        for name, liters in cases:
            with self.subTest(name=name):
                row = product("X", name)
                self.assertEqual(parse_pack_metrics(row)["total_pack_liters"], liters)
                self.assertTrue(requires_pallet_fixture(row))
                self.assertEqual(required_fixture_class(row), "PALLET")

    def test_small_six_by_200ml_beverage_can_use_regular_shelf(self):
        row = product("BEP", "Beypazarı Maden Suyu 6 x 200 ml")
        self.assertEqual(parse_pack_metrics(row)["total_pack_liters"], 1.2)
        self.assertFalse(requires_pallet_fixture(row))
        self.assertEqual(required_fixture_class(row), "REGULAR_SHELF")

    def test_five_litre_detergent_is_not_pallet_just_for_volume(self):
        row = product(
            "DET-5L",
            "Çamaşır Deterjanı 5 L",
            category="Cleaning",
            weight=5.2,
        )
        self.assertFalse(requires_pallet_fixture(row))
        self.assertEqual(required_fixture_class(row), "REGULAR_SHELF")
        self.assertTrue(requires_bottom_shelf(row))

    def test_heavy_product_is_hard_bottom_constraint(self):
        row = product("HEAVY", "Heavy Cleaning Product", category="Cleaning", weight=4.0)
        module = {"module_type": "regular_shelf", "storage_type": "AMBIENT"}
        eye = {"zone_type": "eye", "allowed_storage_type": "AMBIENT"}
        bottom = {"zone_type": "bottom", "allowed_storage_type": "AMBIENT"}
        self.assertEqual(
            physical_constraint_reason(row, module, eye),
            "heavy_product_requires_bottom_shelf",
        )
        self.assertIsNone(physical_constraint_reason(row, module, bottom))

    def test_chilled_and_frozen_require_temperature_fixture_classes(self):
        chilled = product("C", "Yogurt", storage="DOLAP")
        frozen = product("F", "Frozen Peas", storage="-18")
        self.assertEqual(required_fixture_class(chilled), "CHILLED")
        self.assertEqual(required_fixture_class(frozen), "FROZEN")

    def test_estimated_dimensions_are_not_physical_scale_eligible(self):
        row = product("EST", "Estimated", dimension_source="ai_estimated")
        self.assertFalse(physical_scale_eligible(row))
        enriched = clone_with_physical_truth(row)
        self.assertFalse(enriched["physical_scale_eligible"])

    def test_production_gate_blocks_estimated_dimensions(self):
        rows = [
            product(
                f"EST-{index}",
                f"Estimated Product {index}",
                dimension_source="ai_estimated",
            )
            for index in range(10)
        ]
        report = production_acceptance_report(
            rows,
            physical_layout(),
            measured_dna(),
        )
        self.assertEqual(report["dataset"]["dataset_rows"], 10)
        self.assertEqual(report["dataset"]["approved_dimension_coverage_pct"], 0.0)
        self.assertEqual(report["dataset"]["estimated_dimension_pct"], 100.0)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["solver_optimizer_allowed"])
        self.assertIn("approved_dimension_coverage_below_100_pct", report["blockers"])

    def test_production_gate_allows_fully_approved_truth(self):
        rows = [
            product("REG", "Regular Snack", category="Snacks"),
            product("WATER", "Water 6 x 1.5 L"),
        ]
        report = production_acceptance_report(
            rows,
            physical_layout(include_pallet=True),
            measured_dna(1.2),
        )
        self.assertTrue(report["production_ready"], report["blockers"])
        self.assertTrue(report["solver_optimizer_allowed"])
        self.assertEqual(report["dataset"]["approved_dimension_coverage_pct"], 100.0)
        self.assertEqual(report["dataset"]["image_link_coverage_pct"], 100.0)

    def test_missing_pallet_fixture_is_a_production_blocker(self):
        rows = [product("WATER", "Water 12 x 500 ml")]
        report = production_acceptance_report(
            rows,
            physical_layout(include_pallet=False),
            measured_dna(),
        )
        self.assertFalse(report["production_ready"])
        self.assertIn("PALLET", report["fixture_requirements"]["missing_fixture_classes"])
        self.assertIn("required_fixture_class_missing", report["blockers"])

    def test_picker_center_aisle_requires_one_to_one_point_five_meters(self):
        self.assertTrue(store_dna_truth_report(measured_dna(1.2))["picker_aisle_width_valid"])
        low = store_dna_truth_report(measured_dna(0.8))
        high = store_dna_truth_report(measured_dna(1.8))
        self.assertFalse(low["picker_aisle_width_valid"])
        self.assertFalse(high["picker_aisle_width_valid"])
        self.assertIn("picker_center_aisle_width_outside_1_0_to_1_5m", low["blockers"])
        self.assertIn("picker_center_aisle_width_outside_1_0_to_1_5m", high["blockers"])

    def test_default_master_dna_is_not_treated_as_measured_truth(self):
        dna = measured_dna()
        dna["source"] = "approved_store_master"
        report = store_dna_truth_report(dna)
        self.assertFalse(report["measured"])
        self.assertIn("store_dna_not_measured_or_user_approved", report["blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
