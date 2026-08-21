import unittest
from unittest.mock import patch

from . import service, shift_trade_views, shift_trading


class WorkforceShiftTradeViewTests(unittest.TestCase):
    def shift(self, shift_id, person_id, warehouse_id="W1"):
        return {
            "id": shift_id,
            "person_id": person_id,
            "person_name": person_id,
            "status": "Atandı",
            "warehouse_id": warehouse_id,
            "warehouse": f"Warehouse {warehouse_id}",
            "date": "2099-01-10",
            "start": "09:00",
            "end": "17:00",
            "role": "Worker",
        }

    def evaluate(self, shift, person_id, ignored_shift_ids=None):
        return {
            "eligible": True,
            "reasons": [],
            "preference_match": person_id == "P1",
        }

    def identity(self, person_id, identity_type):
        names = {"P1": "Requester", "P2": "Coworker"}
        return {
            "employee_id": person_id,
            "full_name": names.get(person_id, person_id),
        }

    def test_candidate_is_two_way_eligible_and_hides_employee_ids(self):
        shifts = [self.shift("S1", "P1"), self.shift("S2", "P2")]
        with (
            patch.object(service, "_SHIFTS", shifts),
            patch.object(shift_trading, "_hydrate_schedule"),
            patch.object(shift_trading, "_load_trades", return_value=[]),
            patch.object(shift_trading, "_assert_shift_tradeable"),
            patch.object(shift_trading, "_evaluate_assignment", side_effect=self.evaluate),
            patch.object(service, "resolve_person_identity", side_effect=self.identity),
        ):
            rows = shift_trade_views.list_swap_candidates("P1", "S1")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["shift_id"], "S2")
        self.assertEqual(rows[0]["counterpart_display_name"], "Coworker")
        self.assertNotIn("person_id", rows[0])
        self.assertNotIn("target_person_id", rows[0])
        self.assertNotIn("employee_id", rows[0])

    def test_candidate_is_excluded_when_requester_cannot_take_counter_shift(self):
        shifts = [self.shift("S1", "P1"), self.shift("S2", "P2")]

        def evaluate(shift, person_id, ignored_shift_ids=None):
            blocked = str(shift["id"]) == "S2" and person_id == "P1"
            return {
                "eligible": not blocked,
                "reasons": ["REST_RULE"] if blocked else [],
                "preference_match": False,
            }

        with (
            patch.object(service, "_SHIFTS", shifts),
            patch.object(shift_trading, "_hydrate_schedule"),
            patch.object(shift_trading, "_load_trades", return_value=[]),
            patch.object(shift_trading, "_assert_shift_tradeable"),
            patch.object(shift_trading, "_evaluate_assignment", side_effect=evaluate),
            patch.object(service, "resolve_person_identity", side_effect=self.identity),
        ):
            rows = shift_trade_views.list_swap_candidates("P1", "S1")

        self.assertEqual(rows, [])

    def test_candidate_is_locked_when_target_is_already_in_active_trade(self):
        shifts = [self.shift("S1", "P1"), self.shift("S2", "P2")]
        trades = [{
            "id": "TRADE-OTHER",
            "status": "PENDING_EMPLOYEE_ACCEPTANCE",
            "shift_id": "S9",
            "target_shift_id": "S2",
        }]
        with (
            patch.object(service, "_SHIFTS", shifts),
            patch.object(shift_trading, "_hydrate_schedule"),
            patch.object(shift_trading, "_load_trades", return_value=trades),
            patch.object(shift_trading, "_assert_shift_tradeable"),
            patch.object(shift_trading, "_evaluate_assignment", side_effect=self.evaluate),
            patch.object(service, "resolve_person_identity", side_effect=self.identity),
        ):
            rows = shift_trade_views.list_swap_candidates("P1", "S1")

        self.assertEqual(rows, [])

    def test_manager_view_is_worksite_scoped_and_active_only(self):
        shifts = [
            self.shift("S1", "P1", "W1"),
            self.shift("S2", "P2", "W1"),
            self.shift("S3", "P3", "W2"),
        ]
        trades = [
            {
                "id": "TRADE-ACTIVE",
                "status": "PENDING_MANAGER_APPROVAL",
                "mode": "SWAP",
                "warehouse_id": "W1",
                "date": "2099-01-10",
                "created_at": "2099-01-01T10:00:00Z",
                "shift_id": "S1",
                "target_shift_id": "S2",
                "requester_person_id": "P1",
                "target_person_id": "P2",
            },
            {
                "id": "TRADE-FINAL",
                "status": "APPROVED",
                "mode": "TRANSFER",
                "warehouse_id": "W1",
                "date": "2099-01-10",
                "created_at": "2099-01-01T09:00:00Z",
                "shift_id": "S1",
                "requester_person_id": "P1",
                "target_person_id": "P2",
            },
            {
                "id": "TRADE-OTHER-WORKSITE",
                "status": "PENDING_MANAGER_APPROVAL",
                "mode": "TRANSFER",
                "warehouse_id": "W2",
                "date": "2099-01-10",
                "created_at": "2099-01-01T08:00:00Z",
                "shift_id": "S3",
                "requester_person_id": "P3",
                "target_person_id": "P2",
            },
        ]

        with (
            patch.object(service, "_SHIFTS", shifts),
            patch.object(shift_trading, "_hydrate_schedule"),
            patch.object(shift_trading, "_load_trades", return_value=trades),
            patch.object(service, "resolve_person_identity", side_effect=self.identity),
        ):
            active = shift_trade_views.list_manager_shift_trades("W1", active_only=True)
            history = shift_trade_views.list_manager_shift_trades("W1", active_only=False)

        self.assertEqual([row["id"] for row in active], ["TRADE-ACTIVE"])
        self.assertEqual(active[0]["requester_display_name"], "Requester")
        self.assertEqual(active[0]["target_display_name"], "Coworker")
        self.assertEqual(active[0]["source_shift"]["shift_id"], "S1")
        self.assertEqual(active[0]["target_shift"]["shift_id"], "S2")
        self.assertEqual(
            {row["id"] for row in history},
            {"TRADE-ACTIVE", "TRADE-FINAL"},
        )


if __name__ == "__main__":
    unittest.main()
