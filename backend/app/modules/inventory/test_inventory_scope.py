import os
import tempfile
import unittest
from pathlib import Path

from .test_inventory_device_recovery import InventoryDeviceRecoveryPostgresTests
from .test_inventory_explanation_attempt_truth import InventoryExplanationAttemptTruthTests
from .test_inventory_recovery import InventoryRecoveryPostgresTests


class InventoryWarehouseScopeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        os.environ["INVENTORY_DB"] = str(Path(cls.temp.name) / "inventory.db")
        from app.modules.inventory import service
        service.DB_PATH = Path(os.environ["INVENTORY_DB"])
        service.initialize()
        cls.service = service

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_document_creation_rejects_other_warehouse(self):
        payload = {
            "warehouse_id": "WH-002",
            "name": "Scope test",
            "locations": ["A01"],
            "products": [{"sku": "SKU-1", "barcode": "8690000000001", "expected": 1, "cost": 10}],
            "thresholds": {"quantity": 5, "value_try": 1000},
        }
        with self.assertRaises(PermissionError):
            self.service.create_document(payload, "user-wh-1", {"WH-001"})

    def test_document_read_rejects_other_warehouse(self):
        payload = {
            "warehouse_id": "WH-001",
            "name": "Scope read",
            "locations": ["A01"],
            "products": [{"sku": "SKU-2", "barcode": "8690000000002", "expected": 1, "cost": 10}],
            "thresholds": {"quantity": 5, "value_try": 1000},
        }
        document = self.service.create_document(payload, "control", {"WH-001"})
        with self.assertRaises(PermissionError):
            self.service.get_document(document["id"], {"WH-002"})

    def test_terminal_tasks_do_not_expose_blind_count_stock(self):
        payload = {
            "warehouse_id": "WH-001",
            "name": "Blind terminal task",
            "locations": ["A02"],
            "products": [{"sku": "SECRET-SKU", "barcode": "8690000000099", "expected": 47, "cost": 999}],
            "thresholds": {"quantity": 5, "value_try": 1000},
        }
        document = self.service.create_document(payload, "control", {"WH-001"})
        tasks = self.service.list_terminal_tasks({"WH-001"})
        task = next(row for row in tasks if row["id"] == document["id"])
        serialized = str(task)
        self.assertNotIn("payload", task)
        self.assertNotIn("SECRET-SKU", serialized)
        self.assertNotIn("expected", serialized)
        self.assertEqual(task["location_count"], 1)


def load_tests(loader, tests, pattern):
    tests.addTests(loader.loadTestsFromTestCase(InventoryExplanationAttemptTruthTests))
    tests.addTests(loader.loadTestsFromTestCase(InventoryDeviceRecoveryPostgresTests))
    tests.addTests(loader.loadTestsFromTestCase(InventoryRecoveryPostgresTests))
    return tests


if __name__ == "__main__":
    unittest.main()
