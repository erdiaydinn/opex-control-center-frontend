import unittest

from engine import enrich_product, generate_planogram


class FoundationEngineV4Tests(unittest.TestCase):
    def test_turkish_export_headers_are_normalized(self):
        product = enrich_product({
            "SKU": "BEP-6X200",
            "Urun": "Beypazarı Maden Suyu Sade 6 x 200 ml",
            "Marka": "Beypazarı",
            "Kategori": "Beverages",
            "Storage": "AMBIENT",
            "Onyuz": 1,
        })
        self.assertEqual(product["product_name"], "Beypazarı Maden Suyu Sade 6 x 200 ml")
        self.assertEqual(product["brand"], "Beypazarı")
        self.assertEqual(product["category_l1"], "Beverages")
        self.assertEqual(product["storage_type"], "AMBIENT")
        self.assertEqual(product["dimension_reason"], "beverage_multipack")
        self.assertEqual(product["source_facing"], 1)

    def test_superfresh_is_not_classified_as_water_or_bag(self):
        product = enrich_product({
            "SKU": "SF-001",
            "Urun": "SuperFresh Mini Baguette 300 g",
            "Marka": "SuperFresh",
            "Kategori": "Frozen",
            "Storage": "FROZEN",
        })
        self.assertEqual(product["dimension_reason"], "frozen_generic")
        self.assertEqual(product["storage_type"], "FROZEN")

    def test_summary_exposes_assortment_and_capacity_truth(self):
        result = generate_planogram([
            {"SKU": "BEP-1", "Urun": "Beypazarı Maden Suyu 6 x 200 ml", "Marka": "Beypazarı", "Kategori": "Beverages", "Storage": "AMBIENT", "sales_qty_7d": 250},
            {"SKU": "BEP-2", "Urun": "Beypazarı Natural Mineral Water 6 x 200 ml", "Marka": "Beypazarı", "Kategori": "Beverages", "Storage": "AMBIENT", "sales_qty_7d": 200},
        ], None)
        summary = result["summary"]
        self.assertEqual(summary["data_quality"]["missing_name"], 0)
        self.assertGreaterEqual(summary["requested_facing_total"], summary["placed_facing_total"])
        self.assertIn("AMBIENT", summary["capacity_by_storage"])
        self.assertEqual(result["diagnostics"]["summary"]["strict_rule_violation_count"], 0)


if __name__ == "__main__":
    unittest.main()
