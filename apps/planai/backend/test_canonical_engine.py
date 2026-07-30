import csv
import importlib.util
import tempfile
import unittest
from pathlib import Path


ENGINE_PATH = Path(__file__).with_name("engine.py")


def load_engine():
    spec = importlib.util.spec_from_file_location("planai_test_engine", ENGINE_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CanonicalEngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self.tmp.name)
        self.engine = load_engine()

        self.engine.DATA_DIR = self.data_dir
        self.engine.MASTER_CSV = self.data_dir / "master_products.csv"
        self.engine.LEGACY_MASTER_CSV = self.data_dir / "catalog.csv"
        self.engine.MASTER_XLSX = self.data_dir / "master_products.xlsx"
        self.engine.AFFINITY_CSV = self.data_dir / "basket_affinity_top.csv"
        self.engine.AFFINITY_PARQUET = self.data_dir / "basket_affinity_top.parquet"
        self.engine.MASTER_CACHE.update({
            "loaded": False,
            "rows": [],
            "by_sku": {},
            "by_barcode": {},
            "by_catalog": {},
            "by_pim": {},
            "by_key": {},
            "source_path": None,
            "dimension_rows": 0,
        })
        self.engine.AFFINITY_CACHE.update({
            "loaded": False,
            "source_path": None,
            "rows": 0,
            "pairs": 0,
            "by_sku": {},
            "columns": [],
        })

        headers = [
            "Ürün Kodu (Global)", "Ürün Adı", "Koli İçi Adedi",
            "Ürün Brüt Ağırlık (Gr)", "Ürün En (cm)", "Ürün Boy (CM)",
            "Ürün Yükseklik (cm)", "Ürün Segmenti", "Saklama Koşulu (Raf/ +4/-18)",
        ]
        rows = [
            ["3AF716", "Beypazarı Sade Gazoz", "6", "1000", "3.2", "6.5", "22", "A", "Raf"],
            ["YS2002", "Viking Toz Soda", "12", "500", "7", "7", "20", "B", "Raf"],
            ["YS2806", "Ernet Çamaşır Sodası", "12", "500", "8", "8", "20", "B", "Raf"],
            ["WIDE", "Geniş Test Ürünü", "12", "1000", "30", "10", "20", "A", "Raf"],
        ]
        with self.engine.MASTER_CSV.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)

        with self.engine.AFFINITY_CSV.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["source_sku", "target_sku", "affinity_score"])
            writer.writerow(["3AF716", "YS2002", "0.9"])

    def tearDown(self):
        self.tmp.cleanup()

    def test_turkish_master_is_used_without_ai(self):
        product = self.engine.enrich_product({"sku": "3AF716"}, allow_ai_dimensions=False)

        self.assertEqual(product["dimension_source"], "master")
        self.assertEqual(product["dimension_reason"], "master_dimensions")
        self.assertAlmostEqual(product["width_cm"], 3.2)
        self.assertAlmostEqual(product["depth_cm"], 6.5)
        self.assertAlmostEqual(product["height_cm"], 22)
        self.assertEqual(product["storage_type"], "AMBIENT")
        self.assertEqual(product["case_pack_qty"], 6)

    def test_affinity_is_loaded_as_two_way_soft_signal(self):
        affinity = self.engine.load_affinity(force=True)
        self.assertEqual(affinity["pairs"], 2)
        self.assertAlmostEqual(affinity["by_sku"]["3af716"]["ys2002"], 0.9)
        self.assertAlmostEqual(affinity["by_sku"]["ys2002"]["3af716"], 0.9)

        shelf = {"products": [{"sku": "3AF716"}]}
        module = {"shelves": [shelf]}
        aisle = {"modules": [module]}
        product = self.engine.enrich_product({"sku": "YS2002"}, allow_ai_dimensions=False)
        self.assertGreater(self.engine.basket_affinity_score(product, aisle, module, shelf), 0)

    def test_facing_is_reduced_to_physical_shelf_capacity(self):
        shelf = self.engine.make_shelves(1, "AMBIENT", 100, 35, 50, 45)[0]
        layout = {
            "aisles": [{
                "aisle_id": "A",
                "row": 1,
                "position": 1,
                "direction": "LTR",
                "modules": [{
                    "module_id": 1,
                    "module_type": "regular_shelf",
                    "side": "L",
                    "shelves": [shelf],
                }],
            }]
        }

        result = self.engine.generate_planogram(
            [{"sku": "WIDE", "sales_qty_7d": 200}],
            layout,
            allow_ai_dimensions=False,
        )
        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][0]["products"]

        self.assertEqual(len(placed), 1)
        self.assertEqual(placed[0]["facing_count"], 3)
        self.assertLessEqual(placed[0]["used_width_cm"], 100)
        self.assertEqual(result["diagnostics"]["summary"]["overfilled_shelf_count"], 0)

    def test_candidate_search_is_not_limited_to_first_forty_shelves(self):
        shelves = self.engine.make_shelves(41, "AMBIENT", 100, 10, 50, 45)
        shelves[-1]["shelf_height_cm"] = 35
        layout = {
            "aisles": [{
                "aisle_id": "A",
                "row": 1,
                "position": 1,
                "direction": "LTR",
                "modules": [{
                    "module_id": 1,
                    "module_type": "regular_shelf",
                    "side": "L",
                    "shelves": shelves,
                }],
            }]
        }
        result = self.engine.generate_planogram(
            [{"sku": "WIDE"}],
            layout,
            allow_ai_dimensions=False,
        )

        placed = result["planogram"]["aisles"][0]["modules"][0]["shelves"][-1]["products"]
        self.assertEqual(len(placed), 1)

    def test_missing_dimensions_are_reported_instead_of_silently_estimated(self):
        result = self.engine.generate_planogram(
            [{"sku": "UNKNOWN", "product_name": "Beypazarı Sade Soda"}],
            self.engine.generate_default_layout(),
            allow_ai_dimensions=False,
        )
        self.assertEqual(result["summary"]["placed_products"], 0)
        self.assertEqual(result["unplaced"][0]["reason"], "dimension_missing")


if __name__ == "__main__":
    unittest.main()
