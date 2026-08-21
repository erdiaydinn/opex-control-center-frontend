import unittest
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import patch

from . import service
from . import work_activity_labor_catalog as labor
from . import work_activity_runtime as runtime
from .work_activity_authority import (
    ActivityLaborStandardVersion,
    WorkActivityDemandRequest,
    WorkActivityVersion,
    WorkloadSignal,
    build_work_activity_demand_snapshot,
)
from .work_activity_planning import CapabilityWorker, build_work_activity_capacity_plan
from .workforce_capability_authority import update_employee_capabilities, update_worksite_type


AT = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


def demand(activity_key, *, skills=(), certifications=(), equipment=(), quantity="4", seconds="900"):
    activity = WorkActivityVersion(
        tenant_id="tenant-a", activity_key=activity_key, version=1,
        display_name=activity_key, category="operations", unit_key="items", demand_mode="VOLUME",
        effective_from=datetime(2026, 1, 1, tzinfo=UTC), source_ref="activity:v1", approved_by="ops",
        required_skill_keys=skills, required_certification_keys=certifications,
        required_equipment_keys=equipment,
    )
    standard = ActivityLaborStandardVersion(
        tenant_id="tenant-a", activity_key=activity_key, version=1,
        seconds_per_unit=Decimal(seconds), people=Decimal("1"),
        effective_from=datetime(2026, 1, 1, tzinfo=UTC), source_ref="time-study:v1", approved_by="ie",
    )
    request = WorkActivityDemandRequest(
        tenant_id="tenant-a", location_id="SITE-1", interval_start=AT,
        interval_minutes=60, model_version="generic-v1",
        signals=(WorkloadSignal(driver_key=f"driver:{activity_key}", activity_key=activity_key, demand_mode="VOLUME", quantity=Decimal(quantity), source_ref="forecast:v1"),),
    )
    return build_work_activity_demand_snapshot(request, [activity], [standard])


class LaborCatalogTests(unittest.TestCase):
    def test_labor_standard_requires_approved_activity_and_audits_source(self):
        captured = {}
        activity = {"id": "ACT-grill-V2", "version": 2}
        with (
            patch.object(labor.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(labor, "resolve_catalog_activity", return_value=activity),
            patch.object(labor.persistence, "load_collection", return_value=[]),
            patch.object(labor.persistence, "persist_snapshot_with_audit", side_effect=lambda collections, event, actor, **details: captured.update(collections=collections, event=event, details=details)),
        ):
            row = labor.approve_labor_standard({
                "activity_key": "food_grill_cook", "seconds_per_unit": 72, "people": 1,
                "effective_from": "2026-08-20", "source_ref": "approved-time-study:qsr:v4",
            }, "industrial-engineering@example.test")
        self.assertEqual(row["activity_authority_ref"], "ACT-grill-V2")
        self.assertEqual(row["seconds_per_unit"], "72")
        self.assertEqual(captured["event"], "WORKFORCE_ACTIVITY_LABOR_STANDARD_APPROVED")
        self.assertEqual(captured["details"]["source_ref"], "approved-time-study:qsr:v4")

    def test_labor_standard_fails_closed_without_activity_authority(self):
        with (
            patch.object(labor.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(labor, "resolve_catalog_activity", side_effect=labor.WorkActivityCatalogError("missing")),
        ):
            with self.assertRaisesRegex(labor.ActivityLaborCatalogError, "requires approved"):
                labor.approve_labor_standard({
                    "activity_key": "machine_operation", "seconds_per_unit": 90, "people": 1,
                    "effective_from": "2026-08-20", "source_ref": "factory-study:v1",
                }, "ie")


class CatalogRuntimeTests(unittest.TestCase):
    def activity_row(self, key="food_grill_cook", location_types=()):
        return {
            "id": f"ACT-{key}-V1", "tenant_id": "tenant-a", "activity_key": key, "version": 1,
            "display_name": key, "category": "operations", "unit_key": "items", "demand_mode": "VOLUME",
            "effective_from": "2026-01-01T00:00:00+00:00", "effective_until": None,
            "source_ref": "activity:v1", "approved_by": "ops", "status": "APPROVED",
            "required_skill_keys": ["grill_station"] if key == "food_grill_cook" else [],
            "required_certification_keys": ["food_safety"] if key == "food_grill_cook" else [],
            "required_equipment_keys": [], "safety_tags": [], "location_types": list(location_types),
        }

    def labor_row(self, key="food_grill_cook"):
        return {
            "id": f"LAB-{key}-V1", "tenant_id": "tenant-a", "activity_key": key, "version": 1,
            "seconds_per_unit": "90", "people": "1", "effective_from": "2026-01-01T00:00:00+00:00",
            "effective_until": None, "source_ref": "time-study:v1", "approved_by": "ie", "status": "APPROVED",
        }

    def test_runtime_uses_tenant_catalog_not_starter_template_or_guessed_timing(self):
        with (
            patch.object(runtime.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(runtime, "resolve_catalog_activity", return_value=self.activity_row()),
            patch.object(runtime, "resolve_labor_standard", return_value=self.labor_row()),
        ):
            snapshot = runtime.build_catalog_demand_snapshot(
                worksite_id="SITE-QSR-1", interval_start=AT, interval_minutes=60,
                model_version="generic-v1",
                signals=[{"driver_key": "pos:grill", "activity_key": "food_grill_cook", "demand_mode": "VOLUME", "quantity": 40, "source_ref": "pos:forecast:v1"}],
            )
        self.assertEqual(snapshot.required_man_hours, Decimal("1"))
        self.assertEqual(snapshot.required_people, Decimal("1"))
        self.assertEqual(snapshot.contributions[0].required_certification_keys, ("food_safety",))
        self.assertEqual(snapshot.contributions[0].labor_standard_source_ref, "time-study:v1")

    def test_runtime_fails_closed_when_labor_authority_is_missing(self):
        with (
            patch.object(runtime.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(runtime, "resolve_catalog_activity", return_value=self.activity_row("machine_operation")),
            patch.object(runtime, "resolve_labor_standard", side_effect=runtime.ActivityLaborCatalogError("missing labor")),
        ):
            with self.assertRaisesRegex(runtime.WorkActivityRuntimeError, "missing labor"):
                runtime.build_catalog_demand_snapshot(
                    worksite_id="SITE-FACTORY-1", interval_start=AT, interval_minutes=60,
                    model_version="generic-v1",
                    signals=[{"driver_key": "mes:line1", "activity_key": "machine_operation", "demand_mode": "VOLUME", "quantity": 20, "source_ref": "mes:plan:v1"}],
                )

    def test_runtime_fails_closed_when_worksite_type_is_incompatible(self):
        activity = self.activity_row("machine_operation", ("factory",))
        with (
            patch.object(runtime.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(runtime, "resolve_catalog_activity", return_value=activity),
            patch.object(runtime, "resolve_labor_standard", return_value=self.labor_row("machine_operation")),
            patch.object(service, "list_warehouses", return_value=[{"id": "SITE-1", "location_type": "restaurant"}]),
        ):
            with self.assertRaisesRegex(runtime.WorkActivityRuntimeError, "not eligible"):
                runtime.build_catalog_demand_snapshot(
                    worksite_id="SITE-1", interval_start=AT, interval_minutes=60,
                    model_version="generic-v1",
                    signals=[{"driver_key": "mes:line1", "activity_key": "machine_operation", "demand_mode": "VOLUME", "quantity": 1, "source_ref": "mes:v1"}],
                )

    def test_runtime_requires_classification_for_constrained_activity(self):
        activity = self.activity_row("food_grill_cook", ("restaurant",))
        with (
            patch.object(runtime.persistence, "tenant_id", return_value="tenant-a"),
            patch.object(runtime, "resolve_catalog_activity", return_value=activity),
            patch.object(runtime, "resolve_labor_standard", return_value=self.labor_row()),
            patch.object(service, "list_warehouses", return_value=[{"id": "SITE-1"}]),
        ):
            with self.assertRaisesRegex(runtime.WorkActivityRuntimeError, "classification is required"):
                runtime.build_catalog_demand_snapshot(
                    worksite_id="SITE-1", interval_start=AT, interval_minutes=60,
                    model_version="generic-v1",
                    signals=[{"driver_key": "pos:grill", "activity_key": "food_grill_cook", "demand_mode": "VOLUME", "quantity": 1, "source_ref": "pos:v1"}],
                )


class GenericPlanningTests(unittest.TestCase):
    def test_qsr_capability_bundle_blocks_unqualified_headcount(self):
        snapshot = demand("food_grill_cook", skills=("grill_station",), certifications=("food_safety",))
        workers = (
            CapabilityWorker("EMP-1", Decimal("1"), frozenset({"checkout"}), frozenset({"food_safety"}), source_ref="roster:v1"),
            CapabilityWorker("EMP-2", Decimal("1"), frozenset({"grill_station"}), frozenset(), source_ref="roster:v1"),
        )
        plan = build_work_activity_capacity_plan(snapshot, workers)
        self.assertEqual(plan.available_man_hours, Decimal("2"))
        self.assertEqual(plan.deficit_man_hours, Decimal("1"))
        self.assertEqual(plan.root_cause, "skill_mix_constraint")
        self.assertEqual(plan.primary_capability_target, "activity:food_grill_cook")

    def test_factory_machine_authority_allocates_only_certified_operator(self):
        snapshot = demand("machine_operation", skills=("machine_operation",), certifications=("machine_authorization",), quantity="2", seconds="1800")
        workers = (
            CapabilityWorker("EMP-M1", Decimal("1"), frozenset({"machine_operation"}), frozenset({"machine_authorization"}), source_ref="roster:v1"),
            CapabilityWorker("EMP-M2", Decimal("1"), frozenset({"machine_operation"}), frozenset(), source_ref="roster:v1"),
        )
        plan = build_work_activity_capacity_plan(snapshot, workers)
        self.assertEqual(plan.deficit_man_hours, Decimal("0"))
        self.assertEqual(plan.rows[0].eligible_worker_ids, ("EMP-M1",))

    def test_market_checkout_shortage_becomes_people_recommendation(self):
        snapshot = demand("checkout_service", skills=("checkout",), quantity="8", seconds="900")
        workers = (CapabilityWorker("EMP-C1", Decimal("1"), frozenset({"checkout"}), source_ref="roster:v1"),)
        plan = build_work_activity_capacity_plan(snapshot, workers)
        self.assertEqual(plan.required_man_hours, Decimal("2"))
        self.assertEqual(plan.deficit_man_hours, Decimal("1"))
        self.assertEqual(plan.root_cause, "manpower_capacity_shortage")
        self.assertEqual(plan.recommended_people, 1)
        self.assertTrue(plan.human_approval_required)
        self.assertFalse(plan.automatic_execution_permitted)


class CapabilityAuthorityTests(unittest.TestCase):
    def test_employee_capabilities_extend_canonical_employee_master(self):
        person = {"employee_id": "EMP-1", "warehouse_id": "WH-1", "active": True}
        with (
            patch.object(service, "resolve_person_identity", return_value=person),
            patch.object(service, "_append_audit") as audit,
        ):
            result = update_employee_capabilities("EMP-1", {
                "skill_keys": ["grill_station"], "certification_keys": ["food_safety"], "equipment_keys": [],
            }, "hr-admin")
        self.assertEqual(person["skill_keys"], ["grill_station"])
        self.assertEqual(result["certification_keys"], ["food_safety"])
        audit.assert_called_once()
        self.assertEqual(audit.call_args.args[0], "EMPLOYEE_CAPABILITIES_UPDATED")

    def test_worksite_type_updates_existing_worksite_not_parallel_location_model(self):
        existing = {"id": "WH-1", "name": "Factory A", "latitude": 41.0, "longitude": 29.0, "radius": 120, "max_accuracy": 50, "active": True}
        with (
            patch.object(service, "list_warehouses", return_value=[existing]),
            patch.object(service, "upsert_warehouse", return_value={**existing, "location_type": "factory"}) as upsert,
        ):
            result = update_worksite_type("WH-1", "factory", "platform-admin")
        self.assertEqual(result["location_type"], "factory")
        self.assertEqual(upsert.call_args.args[0]["id"], "WH-1")


if __name__ == "__main__":
    unittest.main()
