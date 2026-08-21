import os
import tempfile
import unittest

os.environ["INVENTORY_DB"] = tempfile.mktemp(suffix=".db")

from .service import complete, create_document, initialize, lock_location, record_scan


class InventoryV20Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        initialize()

    def test_idempotent_scan_and_threshold_recount(self):
        document = create_document({
            "warehouse_id": "WH1", "name": "Test", "locations": ["A01"],
            "products": [{"sku": "1", "barcode": "8690000000001", "expected": 10, "cost": 100}],
            "thresholds": {"quantity": 2, "value_try": 100},
        }, "admin")
        lock_location(document["id"], "A01", "ZEBRA-01", "counter", 900)
        payload = {"client_event_id": "EVENT-00000001", "device_id": "ZEBRA-01", "location": "A01", "barcode": "8690000000001", "quantity": 5, "source": "TERMINAL"}
        first = record_scan(document["id"], payload, "counter")
        second = record_scan(document["id"], payload, "counter")
        self.assertEqual(first["id"], second["id"])
        self.assertTrue(second["idempotent_replay"])
        self.assertEqual(complete(document["id"], "manager")["status"], "RECOUNT_REQUIRED")


if __name__ == "__main__":
    unittest.main()
