import unittest
from uuid import UUID

from .sku_identity import frozen_sku_identity


DOCUMENT_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")


class InventorySkuIdentityTests(unittest.TestCase):
 def test_known_identity_is_deterministic_and_contains_no_stock_truth(self) -> None:
    first = frozen_sku_identity(
        DOCUMENT_ID,
        " 8690000000001 ",
        {"sku": "SKU-REAL-1", "expected_quantity": 47, "unit_cost": 999},
    )
    second = frozen_sku_identity(
        DOCUMENT_ID,
        "8690000000001",
        {"sku": "SKU-REAL-1", "expected_quantity": 1, "unit_cost": 0},
    )

    self.assertEqual(first, second)
    self.assertEqual(first["sku"], "SKU-REAL-1")
    self.assertEqual(first["status"], "KNOWN")
    self.assertEqual(first["barcode"], "8690000000001")
    self.assertEqual(len(first["snapshot_hash"]), 64)
    rendered = repr(first).lower()
    for forbidden in ("expected", "quantity", "cost", "variance", "stock"):
        self.assertNotIn(forbidden, rendered)


 def test_unexpected_barcode_never_receives_invented_sku(self) -> None:
    identity = frozen_sku_identity(DOCUMENT_ID, "9999999999999", None)

    self.assertEqual(identity["status"], "UNEXPECTED")
    self.assertIsNone(identity["sku"])
    self.assertEqual(identity["barcode"], "9999999999999")


 def test_identity_proof_is_bound_to_document_barcode_and_sku(self) -> None:
    baseline = frozen_sku_identity(DOCUMENT_ID, "8691", {"sku": "SKU-1"})

    self.assertNotEqual(baseline["snapshot_hash"], frozen_sku_identity(
        UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"), "8691", {"sku": "SKU-1"}
    )["snapshot_hash"])
    self.assertNotEqual(baseline["snapshot_hash"], frozen_sku_identity(
        DOCUMENT_ID, "8692", {"sku": "SKU-1"}
    )["snapshot_hash"])
    self.assertNotEqual(baseline["snapshot_hash"], frozen_sku_identity(
        DOCUMENT_ID, "8691", {"sku": "SKU-2"}
    )["snapshot_hash"])


if __name__ == "__main__":
    unittest.main()
