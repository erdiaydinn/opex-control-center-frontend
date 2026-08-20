from decimal import Decimal
import unittest
from uuid import uuid4

from .operational_mobile import _project_operational_mobile_row
from .production import InventoryPrincipal


class OperationalMobileProjectionContractTests(unittest.TestCase):
    def setUp(self):
        self.principal = InventoryPrincipal(
            "tenant-a",
            "sub-a",
            "EMP-A",
            frozenset({"WH-1"}),
            uuid4(),
        )

    def test_non_receiving_projection_strips_legacy_condition_defaults(self):
        row = self._row(
            mission_type="PICKING",
            operation="inventory.pick.capture",
            steps=["SOURCE_LOCATION", "ITEM", "QUANTITY", "CONTAINER", "COMPLETE"],
            source_location_id="A01",
            container_id="TOTE-1",
            allowed_conditions=["GOOD"],
        )
        projected = _project_operational_mobile_row(row, self.principal, "SHIFT-A")
        self.assertIsNotNone(projected)
        self.assertEqual(projected["allowed_conditions"], [])

    def test_receiving_projection_keeps_only_server_frozen_conditions(self):
        row = self._row(
            mission_type="RECEIVING",
            operation="inventory.receiving.capture",
            steps=["CONTAINER", "ITEM", "QUANTITY", "CONDITION", "COMPLETE"],
            container_id="PALLET-1",
            allowed_conditions=["good", " damaged "],
        )
        projected = _project_operational_mobile_row(row, self.principal, "SHIFT-A")
        self.assertIsNotNone(projected)
        self.assertEqual(projected["allowed_conditions"], ["GOOD", "DAMAGED"])

    def test_receiving_without_condition_authority_fails_closed(self):
        row = self._row(
            mission_type="RECEIVING",
            operation="inventory.receiving.capture",
            steps=["CONTAINER", "ITEM", "QUANTITY", "CONDITION", "COMPLETE"],
            container_id="PALLET-1",
            allowed_conditions=[],
        )
        self.assertIsNone(_project_operational_mobile_row(row, self.principal, "SHIFT-A"))

    def test_foreign_claim_never_projects(self):
        row = self._row(
            mission_type="PUTAWAY",
            operation="inventory.putaway.capture",
            steps=["ITEM", "QUANTITY", "DESTINATION_LOCATION", "COMPLETE"],
            destination_location_id="B02",
            state="CLAIMED",
            claim_employee_id="EMP-B",
            claim_device_id=self.principal.device_id,
            claim_shift_id="SHIFT-A",
        )
        self.assertIsNone(_project_operational_mobile_row(row, self.principal, "SHIFT-A"))

    def _row(self, **overrides):
        row = {
            "mission_id": uuid4(),
            "warehouse_id": "WH-1",
            "mission_type": "PICKING",
            "operation": "inventory.pick.capture",
            "external_reference": "REF-1",
            "steps": ["SOURCE_LOCATION", "ITEM", "QUANTITY", "CONTAINER", "COMPLETE"],
            "state": "OPEN",
            "sku_id": "SKU-1",
            "planned_quantity": Decimal("4"),
            "source_location_id": "A01",
            "destination_location_id": None,
            "container_id": "TOTE-1",
            "allowed_conditions": ["GOOD"],
            "claim_employee_id": None,
            "claim_device_id": None,
            "claim_shift_id": None,
            "completed_steps": 0,
        }
        row.update(overrides)
        return row


if __name__ == "__main__":
    unittest.main()
