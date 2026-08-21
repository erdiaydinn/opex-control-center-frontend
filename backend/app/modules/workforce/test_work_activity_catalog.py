import unittest
from unittest.mock import patch

from . import work_activity_catalog as catalog


class WorkActivityCatalogTests(unittest.TestCase):
    def payload(self, activity_key="food_grill_cook"):
        return {
            "activity_key": activity_key,
            "display_name": "Grill cooking",
            "category": "food_production",
            "unit_key": "items",
            "demand_mode": "VOLUME",
            "effective_from": "2026-08-20",
            "source_ref": "ops-standard:qsr:v1",
            "required_skill_keys": ["grill_station"],
            "required_certification_keys": ["food_safety"],
            "required_equipment_keys": [],
            "safety_tags": ["hot_surface"],
            "location_types": ["restaurant"],
        }

    def test_approve_activity_versions_and_audits_tenant_authority(self):
        captured = {}
        def persist(collections, event, actor, **details):
            captured.update(collections=collections, event=event, actor=actor, details=details)
        with (
            patch.object(catalog.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(catalog.persistence, "load_collection", return_value=[]),
            patch.object(catalog.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            row = catalog.approve_activity(self.payload(), "ops-admin@example.test")
        self.assertEqual(row["tenant_id"], "tenant-a")
        self.assertEqual(row["version"], 1)
        self.assertEqual(row["required_skill_keys"], ["grill_station"])
        self.assertEqual(captured["event"], "WORKFORCE_ACTIVITY_APPROVED")
        self.assertEqual(captured["details"]["activity_key"], "food_grill_cook")

    def test_new_version_closes_previous_effective_authority(self):
        rows = [{
            "id": "ACT-food_grill_cook-V1", "tenant_id": "tenant-a", "activity_key": "food_grill_cook", "version": 1,
            "display_name": "Grill cooking", "category": "food_production", "unit_key": "items", "demand_mode": "VOLUME",
            "required_skill_keys": [], "required_certification_keys": [], "required_equipment_keys": [], "safety_tags": [],
            "location_types": ["restaurant"], "effective_from": "2026-01-01T00:00:00+03:00", "effective_until": None,
            "status": "APPROVED", "source_ref": "ops-standard:qsr:v0", "approved_by": "old-admin",
        }]
        captured = {}
        with (
            patch.object(catalog.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(catalog.persistence, "load_collection", return_value=rows),
            patch.object(catalog.persistence, "persist_snapshot_with_audit", side_effect=lambda collections, *args, **kwargs: captured.update(collections=collections)),
        ):
            row = catalog.approve_activity(self.payload(), "ops-admin@example.test")
        previous = captured["collections"]["workforce_activity_catalog"][0]
        self.assertEqual(row["version"], 2)
        self.assertEqual(previous["effective_until"], "2026-08-20T00:00:00+03:00")
        self.assertEqual(previous["superseded_by_version"], 2)

    def test_resolve_catalog_activity_fails_closed_when_missing_or_ambiguous(self):
        with (
            patch.object(catalog.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(catalog.persistence, "load_collection", return_value=[]),
        ):
            with self.assertRaisesRegex(catalog.WorkActivityCatalogError, "not found"):
                catalog.resolve_catalog_activity("machine_operation", "2026-08-20")
        row = {
            "id": "ACT-machine_operation-V1", "tenant_id": "tenant-a", "activity_key": "machine_operation", "version": 1,
            "display_name": "Machine operation", "category": "production", "unit_key": "units", "demand_mode": "VOLUME",
            "required_skill_keys": [], "required_certification_keys": [], "required_equipment_keys": [], "safety_tags": [],
            "location_types": ["factory"], "effective_from": "2026-01-01T00:00:00+03:00", "effective_until": None,
            "status": "APPROVED", "source_ref": "factory-standard:v1", "approved_by": "factory-admin",
        }
        with (
            patch.object(catalog.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(catalog.persistence, "load_collection", return_value=[row, {**row, "id": "ACT-machine_operation-V2", "version": 2}]),
        ):
            with self.assertRaisesRegex(catalog.WorkActivityCatalogError, "Ambiguous"):
                catalog.resolve_catalog_activity("machine_operation", "2026-08-20")

    def test_template_candidates_are_never_persisted_by_reading_template(self):
        with patch.object(catalog.persistence, "persist_snapshot_with_audit") as persist:
            rows = catalog.list_template_candidates("manufacturing")
        self.assertTrue(any(row["activity_key"] == "machine_operation" for row in rows))
        persist.assert_not_called()


if __name__ == "__main__":
    unittest.main()
