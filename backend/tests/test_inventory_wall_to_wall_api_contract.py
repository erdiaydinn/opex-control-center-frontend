from decimal import Decimal
from unittest import TestCase
from unittest.mock import patch
from uuid import UUID

from backend.app.modules.inventory.production import (
    InventoryPrincipal,
    create_document,
    list_terminal_tasks,
)
from backend.app.modules.inventory.schemas import DocumentCreate, TerminalEventCreate


class _Result:
    def __init__(self, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _Db:
    def __init__(self, task_rows=None):
        self.calls = []
        self.task_rows = task_rows or []
        self.committed = False
        self.rolled_back = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        self.calls.append((compact, params))
        if "SELECT inventory_current_tenant() AS tenant_id" in compact:
            return _Result({"tenant_id": "tenant-a"})
        if "FROM inventory_devices" in compact and "status='ACTIVE'" in compact:
            return _Result({"ok": 1})
        if "SELECT id FROM inventory_documents" in compact and "count_mode='WALL_TO_WALL'" in compact:
            return _Result(None)
        if "FROM inventory_documents d JOIN inventory_document_locations" in compact:
            return _Result(rows=self.task_rows)
        if "SELECT hash FROM inventory_audit" in compact:
            return _Result(None)
        return _Result(None)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class InventoryWallToWallApiContractTest(TestCase):
    def setUp(self):
        self.principal = InventoryPrincipal(
            tenant_id="tenant-a",
            subject="subject-a",
            employee_id="EMP-1",
            warehouse_scope=frozenset({"WH-1"}),
            device_id=UUID("11111111-1111-1111-1111-111111111111"),
        )

    def test_document_schema_defaults_to_golden_and_accepts_wall_to_wall(self):
        golden = DocumentCreate(
            warehouse_id="WH-1",
            name="Golden count",
            locations=["A01"],
            products=[{"sku": "SKU-1", "barcode": "8690000000001"}],
        )
        wall = DocumentCreate(
            warehouse_id="WH-1",
            name="Full count",
            count_mode="WALL_TO_WALL",
            locations=["A01"],
            products=[{"sku": "SKU-1", "barcode": "8690000000001"}],
        )
        self.assertEqual(golden.count_mode, "GOLDEN_COUNT")
        self.assertEqual(wall.count_mode, "WALL_TO_WALL")

    def test_terminal_quantity_keeps_decimal_precision(self):
        event = TerminalEventCreate(
            event_id="11111111-1111-1111-1111-111111111112",
            document_id="11111111-1111-1111-1111-111111111113",
            active_shift_id="SHIFT-1",
            attempt_id="11111111-1111-1111-1111-111111111114",
            lease_id="11111111-1111-1111-1111-111111111115",
            device_sequence=1,
            location_id="A01",
            barcode="8690000000001",
            quantity="3.250",
            symbology="EAN13",
            occurred_at="2026-08-23T01:00:00+03:00",
            payload_hash="a" * 64,
        )
        self.assertIsInstance(event.quantity, Decimal)
        self.assertEqual(event.quantity, Decimal("3.250"))

    def test_w2w_create_auto_adds_lost_found_and_binds_count_mode(self):
        db = _Db()
        payload = {
            "warehouse_id": "WH-1",
            "name": "Full count",
            "count_mode": "WALL_TO_WALL",
            "locations": ["A01", "A02"],
            "products": [{"sku": "SKU-1", "barcode": "8690000000001", "expected": "3.250", "cost": "10.00"}],
        }
        with patch("backend.app.modules.inventory.production.connect", return_value=db):
            result = create_document(self.principal, payload)

        inserts = [call for call in db.calls if call[0].startswith("INSERT INTO inventory_document_locations")]
        inserted_locations = [call[1][2] for call in inserts]
        self.assertEqual(inserted_locations, ["A01", "A02", "LOST_FOUND"])
        document_insert = next(call for call in db.calls if call[0].startswith("INSERT INTO inventory_documents"))
        self.assertEqual(document_insert[1][-1], "WALL_TO_WALL")
        self.assertEqual(result["count_mode"], "WALL_TO_WALL")
        self.assertTrue(db.committed)

    def test_terminal_tasks_fail_closed_for_non_ready_w2w_and_keep_blind_boundary(self):
        ready_id = UUID("22222222-2222-2222-2222-222222222221")
        blocked_id = UUID("22222222-2222-2222-2222-222222222222")
        golden_id = UUID("22222222-2222-2222-2222-222222222223")
        rows = [
            {
                "id": blocked_id,
                "warehouse_id": "WH-1",
                "name": "Blocked W2W",
                "state": "COUNTING",
                "revision": 1,
                "updated_at": None,
                "count_mode": "WALL_TO_WALL",
                "location_id": "A01",
                "location_kind": "STANDARD",
                "remaining_standard_count": 1,
                "location_count": 2,
                "w2w_readiness": {"status": "BLOCKED", "blockers": ["OPERATIONAL_MISSIONS_ACTIVE"]},
            },
            {
                "id": ready_id,
                "warehouse_id": "WH-1",
                "name": "Ready W2W",
                "state": "COUNTING",
                "revision": 1,
                "updated_at": None,
                "count_mode": "WALL_TO_WALL",
                "location_id": "A01",
                "location_kind": "STANDARD",
                "remaining_standard_count": 1,
                "location_count": 2,
                "w2w_readiness": {"status": "READY", "blockers": []},
            },
            {
                "id": ready_id,
                "warehouse_id": "WH-1",
                "name": "Ready W2W",
                "state": "COUNTING",
                "revision": 1,
                "updated_at": None,
                "count_mode": "WALL_TO_WALL",
                "location_id": "LOST_FOUND",
                "location_kind": "LOST_FOUND",
                "remaining_standard_count": 1,
                "location_count": 2,
                "w2w_readiness": {"status": "READY", "blockers": []},
            },
            {
                "id": golden_id,
                "warehouse_id": "WH-1",
                "name": "Golden",
                "state": "COUNTING",
                "revision": 1,
                "updated_at": None,
                "count_mode": "GOLDEN_COUNT",
                "location_id": "G01",
                "location_kind": "STANDARD",
                "remaining_standard_count": 1,
                "location_count": 1,
                "w2w_readiness": {"status": "READY", "applicable": False, "blockers": []},
            },
        ]
        db = _Db(task_rows=rows)
        with patch("backend.app.modules.inventory.production.connect", return_value=db):
            tasks = list_terminal_tasks(self.principal)

        self.assertEqual([(row["count_mode"], row["location_id"]) for row in tasks], [
            ("WALL_TO_WALL", "A01"),
            ("GOLDEN_COUNT", "G01"),
        ])
        for row in tasks:
            self.assertNotIn("expected_quantity", row)
            self.assertNotIn("unit_cost", row)
            self.assertNotIn("variance", row)
            self.assertNotIn("w2w_readiness", row)
