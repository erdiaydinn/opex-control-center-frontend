import unittest
from unittest.mock import patch

from . import flexibility


class WorkforceFlexibilityTests(unittest.TestCase):
    def person(self):
        return {
            "employee_id": "EMP-100",
            "full_name": "Test Employee",
            "warehouse_id": "WH-FULYA",
            "active": True,
        }

    def offer(self):
        return {
            "id": "OPEN-1",
            "warehouse_id": "WH-FULYA",
            "warehouse": "Fulya",
            "date": "2099-08-21",
            "start": "09:00",
            "end": "18:00",
            "break_minutes": 60,
            "role": "Picker",
            "capacity": 1,
            "claimed_count": 0,
            "claims": [],
            "status": "OPEN",
        }

    def test_unavailable_day_fails_closed(self):
        availability = [{
            "id": "AVA-1", "person_id": "EMP-100", "date": "2099-08-21", "available": False,
        }]
        with (
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "person_has_workforce_access", return_value=True),
            patch.object(flexibility.service, "_day_context", return_value={"on_approved_leave": False}),
            patch.object(flexibility.service, "list_shifts", return_value=[]),
        ):
            result = flexibility.evaluate_open_shift(self.offer(), "EMP-100", availability)
        self.assertFalse(result["eligible"])
        self.assertIn("UNAVAILABLE", result["reasons"])
        self.assertEqual(result["score"], 0)

    def test_preferred_window_is_soft_ranking_not_authority(self):
        availability = [{
            "id": "AVA-1",
            "person_id": "EMP-100",
            "date": "2099-08-21",
            "available": True,
            "earliest_start": "08:00",
            "latest_end": "20:00",
            "preferred_start": "08:30",
            "preferred_end": "18:30",
        }]
        with (
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "person_has_workforce_access", return_value=True),
            patch.object(flexibility.service, "_day_context", return_value={"on_approved_leave": False}),
            patch.object(flexibility.service, "list_shifts", return_value=[]),
        ):
            result = flexibility.evaluate_open_shift(self.offer(), "EMP-100", availability)
        self.assertTrue(result["eligible"])
        self.assertTrue(result["preference_match"])
        self.assertEqual(result["score"], 100)

    def test_hard_availability_window_blocks_outside_offer(self):
        offer = {**self.offer(), "start": "07:00", "end": "16:00"}
        availability = [{
            "id": "AVA-1",
            "person_id": "EMP-100",
            "date": "2099-08-21",
            "available": True,
            "earliest_start": "08:00",
            "latest_end": "20:00",
        }]
        with (
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "person_has_workforce_access", return_value=True),
            patch.object(flexibility.service, "_day_context", return_value={"on_approved_leave": False}),
            patch.object(flexibility.service, "list_shifts", return_value=[]),
        ):
            result = flexibility.evaluate_open_shift(offer, "EMP-100", availability)
        self.assertFalse(result["eligible"])
        self.assertIn("OUTSIDE_AVAILABILITY_WINDOW", result["reasons"])

    def test_claim_commits_marketplace_and_canonical_shift_in_one_snapshot(self):
        open_rows = [self.offer()]
        persisted = {}

        def persist(collections, event, actor, **details):
            persisted["collections"] = collections
            persisted["event"] = event
            persisted["actor"] = actor
            persisted["details"] = details

        with (
            patch.object(flexibility.persistence, "ENABLED", False),
            patch.object(flexibility, "_load_open_shifts", return_value=open_rows),
            patch.object(flexibility, "_load_availability", return_value=[]),
            patch.object(flexibility, "evaluate_open_shift", return_value={"eligible": True, "score": 80, "preference_match": None}),
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "_snapshot_collections", return_value={"shifts": [], "notifications": []}),
            patch.object(flexibility.service, "create_shift", return_value={"id": "SHIFT-1", "person_id": "EMP-100"}) as create_shift,
            patch.object(flexibility.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            result = flexibility.claim_open_shift("OPEN-1", "EMP-100", "employee@example.test")

        create_shift.assert_called_once()
        self.assertFalse(create_shift.call_args.kwargs["persist"])
        self.assertEqual(persisted["event"], "WORKFORCE_OPEN_SHIFT_CLAIMED")
        self.assertIn("workforce_open_shifts", persisted["collections"])
        self.assertIn("shifts", persisted["collections"])
        claimed = persisted["collections"]["workforce_open_shifts"][0]
        self.assertEqual(claimed["status"], "FILLED")
        self.assertEqual(claimed["claimed_count"], 1)
        self.assertEqual(result["shift"]["id"], "SHIFT-1")


if __name__ == "__main__":
    unittest.main()
