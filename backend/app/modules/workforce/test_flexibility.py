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
            "skill_keys": [],
            "certification_keys": [],
            "equipment_keys": [],
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
            "role": "Worker",
            "activity_keys": [],
            "activities": [],
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

    def test_activity_requirements_fail_closed_when_employee_capability_is_missing(self):
        offer = {
            **self.offer(),
            "activity_keys": ["food_grill_cook", "warmer_sanitation"],
            "activities": [
                {
                    "activity_key": "food_grill_cook",
                    "required_skill_keys": ["grill_station"],
                    "required_certification_keys": ["food_safety"],
                    "required_equipment_keys": [],
                },
                {
                    "activity_key": "warmer_sanitation",
                    "required_skill_keys": [],
                    "required_certification_keys": ["food_safety"],
                    "required_equipment_keys": [],
                },
            ],
        }
        with (
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "person_has_workforce_access", return_value=True),
            patch.object(flexibility.service, "_day_context", return_value={"on_approved_leave": False}),
            patch.object(flexibility.service, "list_shifts", return_value=[]),
        ):
            result = flexibility.evaluate_open_shift(offer, "EMP-100", [])
        self.assertFalse(result["eligible"])
        self.assertIn("SKILL_REQUIREMENT", result["reasons"])
        self.assertIn("CERTIFICATION_REQUIREMENT", result["reasons"])
        self.assertEqual(result["missing_skill_keys"], ["grill_station"])
        self.assertEqual(result["missing_certification_keys"], ["food_safety"])

    def test_same_activity_engine_accepts_qsr_factory_or_retail_capabilities(self):
        person = {
            **self.person(),
            "skill_keys": ["machine_operation", "checkout", "grill_station"],
            "certification_keys": ["machine_authorization", "food_safety"],
            "equipment_keys": ["material_handling_equipment"],
        }
        offers = [
            {
                **self.offer(),
                "activity_keys": ["food_grill_cook"],
                "activities": [{
                    "activity_key": "food_grill_cook",
                    "required_skill_keys": ["grill_station"],
                    "required_certification_keys": ["food_safety"],
                    "required_equipment_keys": [],
                }],
            },
            {
                **self.offer(),
                "id": "OPEN-FACTORY",
                "activity_keys": ["machine_operation"],
                "activities": [{
                    "activity_key": "machine_operation",
                    "required_skill_keys": ["machine_operation"],
                    "required_certification_keys": ["machine_authorization"],
                    "required_equipment_keys": [],
                }],
            },
            {
                **self.offer(),
                "id": "OPEN-RETAIL",
                "activity_keys": ["checkout_service"],
                "activities": [{
                    "activity_key": "checkout_service",
                    "required_skill_keys": ["checkout"],
                    "required_certification_keys": [],
                    "required_equipment_keys": [],
                }],
            },
        ]
        with (
            patch.object(flexibility.service, "resolve_person_identity", return_value=person),
            patch.object(flexibility.service, "person_has_workforce_access", return_value=True),
            patch.object(flexibility.service, "_day_context", return_value={"on_approved_leave": False}),
            patch.object(flexibility.service, "list_shifts", return_value=[]),
        ):
            results = [flexibility.evaluate_open_shift(offer, "EMP-100", []) for offer in offers]
        self.assertTrue(all(result["eligible"] for result in results))
        self.assertTrue(all(result["activity_match"] for result in results))

    def test_create_open_shift_snapshots_approved_activity_authority(self):
        approved = [{
            "id": "ACT-food_grill_cook-V3",
            "activity_key": "food_grill_cook",
            "version": 3,
            "display_name": "Grill cooking",
            "category": "food_production",
            "unit_key": "items",
            "demand_mode": "VOLUME",
            "required_skill_keys": ["grill_station"],
            "required_certification_keys": ["food_safety"],
            "required_equipment_keys": [],
            "safety_tags": ["hot_surface"],
            "location_types": ["restaurant"],
            "source_ref": "ops-standard:grill:v3",
        }]
        captured = {}
        with (
            patch.object(flexibility, "_warehouse_record", return_value={"id": "WH-FULYA", "name": "Fulya", "location_type": "restaurant"}),
            patch.object(flexibility, "resolve_activity_bundle", return_value=approved),
            patch.object(flexibility, "_load_open_shifts", return_value=[]),
            patch.object(flexibility, "_persist_collection", side_effect=lambda kind, rows, event, actor, **details: captured.update(rows=rows, event=event, details=details)),
            patch.object(flexibility.service, "_minimum_break_minutes", return_value=60),
            patch.object(flexibility.service, "_gross_shift_minutes", return_value=540),
            patch.object(flexibility.service, "_rule_value", return_value=660),
        ):
            result = flexibility.create_open_shift(
                {
                    "warehouse_id": "WH-FULYA",
                    "date": "2099-08-21",
                    "start": "09:00",
                    "end": "18:00",
                    "break_minutes": 60,
                    "role": "Crew",
                    "activity_keys": ["food_grill_cook"],
                    "capacity": 2,
                    "note": "",
                },
                "manager@example.test",
            )
        self.assertEqual(result["activity_keys"], ["food_grill_cook"])
        self.assertEqual(result["activities"][0]["activity_version"], 3)
        self.assertEqual(result["activities"][0]["authority_ref"], "ACT-food_grill_cook-V3")
        self.assertEqual(captured["event"], "WORKFORCE_OPEN_SHIFT_CREATED")
        self.assertEqual(captured["details"]["activity_authority_refs"], ["ACT-food_grill_cook-V3"])

    def test_claim_commits_marketplace_and_canonical_shift_in_one_snapshot(self):
        open_rows = [self.offer()]
        persisted = {}
        before = {"shifts": [], "notifications": []}
        after = {
            "shifts": [{"id": "SHIFT-1", "person_id": "EMP-100"}],
            "notifications": [{"id": "NTF-1", "shift_id": "SHIFT-1"}],
        }

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
            patch.object(flexibility.service, "_snapshot_collections", side_effect=[before, after]),
            patch.object(flexibility.service, "create_shift", return_value={"id": "SHIFT-1", "person_id": "EMP-100"}) as create_shift,
            patch.object(flexibility.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            result = flexibility.claim_open_shift("OPEN-1", "EMP-100", "employee@example.test")

        create_shift.assert_called_once()
        self.assertFalse(create_shift.call_args.kwargs["persist"])
        self.assertEqual(create_shift.call_args.args[0]["activity_keys"], [])
        self.assertEqual(persisted["event"], "WORKFORCE_OPEN_SHIFT_CLAIMED")
        self.assertEqual(persisted["collections"]["shifts"][0]["id"], "SHIFT-1")
        self.assertEqual(persisted["collections"]["notifications"][0]["shift_id"], "SHIFT-1")
        claimed = persisted["collections"]["workforce_open_shifts"][0]
        self.assertEqual(claimed["status"], "FILLED")
        self.assertEqual(claimed["claimed_count"], 1)
        self.assertEqual(result["shift"]["id"], "SHIFT-1")

    def test_claim_restores_workforce_state_on_cas_conflict(self):
        open_rows = [self.offer()]
        before = {"shifts": [], "notifications": []}
        after = {"shifts": [{"id": "SHIFT-1"}], "notifications": [{"id": "NTF-1"}]}
        with (
            patch.object(flexibility.persistence, "ENABLED", False),
            patch.object(flexibility, "_load_open_shifts", return_value=open_rows),
            patch.object(flexibility, "_load_availability", return_value=[]),
            patch.object(flexibility, "evaluate_open_shift", return_value={"eligible": True, "score": 80, "preference_match": None}),
            patch.object(flexibility.service, "resolve_person_identity", return_value=self.person()),
            patch.object(flexibility.service, "_snapshot_collections", side_effect=[before, after]),
            patch.object(flexibility.service, "create_shift", return_value={"id": "SHIFT-1", "person_id": "EMP-100"}),
            patch.object(flexibility.service, "_hydrate_snapshot") as hydrate,
            patch.object(
                flexibility.persistence,
                "persist_snapshot_with_audit",
                side_effect=flexibility.persistence.ConcurrentWriteError("stale"),
            ),
        ):
            with self.assertRaises(flexibility.service.WorkforceRuleError):
                flexibility.claim_open_shift("OPEN-1", "EMP-100", "employee@example.test")
        hydrate.assert_called_once_with(before)


if __name__ == "__main__":
    unittest.main()
