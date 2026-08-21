import csv
import json
import tempfile
import unittest
from pathlib import Path

from physical_truth_audit import build_audit, load_master_csv


class PhysicalTruthAuditTests(unittest.TestCase):
    def write_master(self, root: Path) -> Path:
        path = root / "master_products.csv"
        fields = [
            "sku", "product_name", "brand_name", "frontend_category_local",
            "storage_type", "product_width_in_cm", "product_height_in_cm",
            "product_length_in_cm", "product_weight_value", "image_url",
            "catalog_global_product_id",
        ]
        rows = [
            {"sku": "A", "product_name": "Snack", "brand_name": "X", "frontend_category_local": "Snacks", "storage_type": "RAF", "product_width_in_cm": "8", "product_height_in_cm": "12", "product_length_in_cm": "5", "product_weight_value": "0.1", "image_url": "https://example.test/a.jpg", "catalog_global_product_id": "CAT-A"},
            {"sku": "B", "product_name": "Water 6 x 1.5 L", "brand_name": "Y", "frontend_category_local": "Beverages", "storage_type": "RAF", "product_width_in_cm": "", "product_height_in_cm": "", "product_length_in_cm": "", "product_weight_value": "9", "image_url": "https://example.test/b.jpg", "catalog_global_product_id": "CAT-B"},
            {"sku": "C", "product_name": "Detergent 5 L", "brand_name": "Z", "frontend_category_local": "Cleaning", "storage_type": "RAF", "product_width_in_cm": "10", "product_height_in_cm": "30", "product_length_in_cm": "10", "product_weight_value": "5", "image_url": "", "catalog_global_product_id": "CAT-C"},
        ]
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(rows)
        return path

    def test_raw_master_does_not_default_missing_dimensions(self):
        with tempfile.TemporaryDirectory() as tmp:
            rows = load_master_csv(self.write_master(Path(tmp)))
        self.assertEqual(rows[0]["dimension_source"], "master")
        self.assertEqual(rows[1]["dimension_source"], "missing")
        self.assertEqual(rows[1]["width_cm"], 0)
        self.assertEqual(rows[1]["height_cm"], 0)
        self.assertEqual(rows[1]["depth_cm"], 0)

    def test_audit_reports_exact_master_coverage_without_store_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = build_audit(self.write_master(Path(tmp)))
        dataset = report["dataset"]
        self.assertEqual(dataset["dataset_rows"], 3)
        self.assertEqual(dataset["approved_dimension_count"], 2)
        self.assertEqual(dataset["approved_dimension_coverage_pct"], 66.67)
        self.assertEqual(dataset["image_link_count"], 2)
        self.assertEqual(dataset["image_link_coverage_pct"], 66.67)
        self.assertFalse(report["production_ready"])
        self.assertFalse(report["solver_optimizer_allowed"])
        self.assertIn("approved_dimension_coverage_below_100_pct", report["blockers"])
        self.assertIn("image_link_coverage_below_100_pct", report["blockers"])
        self.assertIn("store_dna_missing", report["blockers"])
        self.assertIn("physical_layout_missing", report["blockers"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
