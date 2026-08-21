from copy import deepcopy
import unittest
from unittest.mock import patch

from . import shift_trading


class WorkforceShiftTradingTests(unittest.TestCase):
    def source_shift(self):
        return {
            "id": "SHIFT-A",
            "person_id": "EMP-A",
            "person_name": "Employee A",
            "warehouse_id": "WH-FULYA",
            "warehouse": "Fulya",
            "date": "2099-08-21",
            "start": "09:00",
            "end": "18:00",
            "break_minutes": 60,
            "expected_minutes": 480,
            "status": "Atandı",
            "activity_bundle": [],
        }

    def target_shift(self):
        return {
            "id": "SHIFT-B",
            "person_id": "EMP-B",
            "person_name": "Employee B",
            "warehouse_id": "WH-FULYA",
            "warehouse": "Fulya",
            "date": "2099-08-22",
            "start": "12:00",
            "end": "20:00",
            "break_minutes": 60,
            "expected_minutes": 420,
            "status": "Atandı",
            "activity_bundle": [],
        }

    def person(self, person_id):
        return {
            "employee_id": person_id,
            "full_name": f"Name {person_id}",
            "warehouse_id": "WH-FULYA",
            "active": True,
            "skill_keys": [],
            "certification_keys": [],
            "equipment_keys": [],
        }

    def test_employee_cannot_create_trade_for_another_workers_shift(self):
        source = {**self.source_shift(), "person_id": "EMP-OTHER"}
        with (
            patch.object(shift_trading.persistence, "ENABLED", False),
            patch.object(shift_trading, "_load_trades", return_value=[]),
            patch.object(shift_trading, "_shift", return_value=source),
        ):
            with self.assertRaises(shift_trading.service.WorkforceRuleError):
                shift_trading.create_shift_trade(
                    {
                        "person_id": "EMP-A",
                        "shift_id": "SHIFT-A",
                        "mode": "TRANSFER",
                        "target_person_id": None,
                        "target_shift_id": None,
                        "note": "",
                    },
                    "employee-a@example.test",
                )

    def test_open_transfer_acceptance_binds_employee_but_does_not_mutate_shift(self):
        trade = {
            "id": "TRADE-1",
            "mode": "TRANSFER",
            "shift_id": "SHIFT-A",
            "requester_person_id": "EMP-A",
            "target_person_id": None,
            "target_shift_id": None,
            "warehouse_id": "WH-FULYA",
            "date": "2099-08-21",
            "status": "OPEN_FOR_ACCEPTANCE",
        }
        persisted = {}

        def persist(collections, event, actor, **details):
            persisted.update(collections=deepcopy(collections), event=event, details=details)

        with (
            patch.object(shift_trading.persistence, "ENABLED", False),
            patch.object(shift_trading, "_load_trades", return_value=[trade]),
            patch.object(shift_trading, "_revalidate_trade", return_value={"source": self.source_shift()}),
            patch.object(shift_trading.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            result = shift_trading.accept_shift_trade("TRADE-1", "EMP-B", "employee-b@example.test")

        self.assertEqual(result["target_person_id"], "EMP-B")
        self.assertEqual(result["status"], "PENDING_MANAGER_APPROVAL")
        self.assertEqual(persisted["event"], "WORKFORCE_SHIFT_TRADE_ACCEPTED")
        self.assertNotIn("shifts", persisted["collections"])

    def test_manager_approval_revalidates_and_reassigns_canonical_transfer_atomically(self):
        source = self.source_shift()
        trade = {
            "id": "TRADE-1",
            "mode": "TRANSFER",
            "shift_id": "SHIFT-A",
            "requester_person_id": "EMP-A",
            "target_person_id": "EMP-B",
            "target_shift_id": None,
            "warehouse_id": "WH-FULYA",
            "date": "2099-08-21",
            "status": "PENDING_MANAGER_APPROVAL",
        }
        before = {"shifts": [deepcopy(source)], "notifications": [{"id": "OLD"}]}
        persisted = {}
        snapshots = 0

        def snapshot():
            nonlocal snapshots
            snapshots += 1
            if snapshots == 1:
                return deepcopy(before)
            return {"shifts": [deepcopy(source)], "notifications": []}

        def persist(collections, event, actor, **details):
            persisted.update(collections=deepcopy(collections), event=event, details=details)

        with (
            patch.object(shift_trading.persistence, "ENABLED", False),
            patch.object(shift_trading, "_load_trades", return_value=[trade]),
            patch.object(
                shift_trading,
                "_revalidate_trade",
                return_value={"source": source, "target": None, "target_evaluation": {"eligible": True}},
            ) as revalidate,
            patch.object(shift_trading.service, "_snapshot_collections", side_effect=snapshot),
            patch.object(shift_trading, "_person_name", return_value="Employee B"),
            patch.object(shift_trading, "_reschedule_shift_notifications", return_value=["OLD"]),
            patch.object(shift_trading.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            result = shift_trading.approve_shift_trade("TRADE-1", "manager@example.test", "approved")

        revalidate.assert_called_once()
        self.assertEqual(source["person_id"], "EMP-B")
        self.assertEqual(source["assignment_history"][0]["from_person_id"], "EMP-A")
        self.assertEqual(source["assignment_history"][0]["to_person_id"], "EMP-B")
        self.assertEqual(result["trade"]["status"], "APPROVED")
        self.assertEqual(persisted["event"], "WORKFORCE_SHIFT_TRADE_APPROVED")
        self.assertEqual(persisted["details"]["cancel_notification_ids"], ["OLD"])
        self.assertEqual(persisted["collections"]["shifts"][0]["person_id"], "EMP-B")

    def test_swap_requires_both_assignments_to_remain_eligible(self):
        source = self.source_shift()
        target = self.target_shift()
        trade = {
            "id": "TRADE-2",
            "mode": "SWAP",
            "shift_id": "SHIFT-A",
            "requester_person_id": "EMP-A",
            "target_person_id": "EMP-B",
            "target_shift_id": "SHIFT-B",
            "warehouse_id": "WH-FULYA",
            "status": "PENDING_MANAGER_APPROVAL",
        }
        with (
            patch.object(shift_trading, "_shift", side_effect=lambda shift_id: source if shift_id == "SHIFT-A" else target),
            patch.object(shift_trading, "_assert_shift_tradeable"),
            patch.object(
                shift_trading,
                "_evaluate_assignment",
                side_effect=[
                    {"eligible": True, "reasons": []},
                    {"eligible": False, "reasons": ["REST_RULE"]},
                ],
            ),
        ):
            with self.assertRaises(shift_trading.service.WorkforceRuleError):
                shift_trading._revalidate_trade(trade)

    def test_cas_conflict_restores_canonical_shift_state(self):
        source = self.source_shift()
        trade = {
            "id": "TRADE-1",
            "mode": "TRANSFER",
            "shift_id": "SHIFT-A",
            "requester_person_id": "EMP-A",
            "target_person_id": "EMP-B",
            "target_shift_id": None,
            "warehouse_id": "WH-FULYA",
            "status": "PENDING_MANAGER_APPROVAL",
        }
        before = {"shifts": [deepcopy(source)], "notifications": []}
        after = {"shifts": [deepcopy(source)], "notifications": []}
        with (
            patch.object(shift_trading.persistence, "ENABLED", False),
            patch.object(shift_trading, "_load_trades", return_value=[trade]),
            patch.object(
                shift_trading,
                "_revalidate_trade",
                return_value={"source": source, "target": None, "target_evaluation": {"eligible": True}},
            ),
            patch.object(shift_trading.service, "_snapshot_collections", side_effect=[before, after]),
            patch.object(shift_trading, "_person_name", return_value="Employee B"),
            patch.object(shift_trading, "_reschedule_shift_notifications", return_value=[]),
            patch.object(shift_trading.service, "_hydrate_snapshot") as hydrate,
            patch.object(
                shift_trading.persistence,
                "persist_snapshot_with_audit",
                side_effect=shift_trading.persistence.ConcurrentWriteError("stale"),
            ),
        ):
            with self.assertRaises(shift_trading.service.WorkforceRuleError):
                shift_trading.approve_shift_trade("TRADE-1", "manager@example.test")
        hydrate.assert_called_once_with(before)


if __name__ == "__main__":
    unittest.main()
