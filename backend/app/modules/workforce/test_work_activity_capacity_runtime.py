import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import work_activity_capacity_runtime as runtime
from .work_activity_authority import (
    ActivityLaborStandardVersion,
    WorkActivityDemandRequest,
    WorkActivityVersion,
    WorkloadSignal,
    build_work_activity_demand_snapshot,
)


AT = datetime(2026, 8, 20, 15, 0, tzinfo=ZoneInfo("Europe/Istanbul"))


def demand_snapshot():
    activity = WorkActivityVersion(
        tenant_id="tenant-a",
        activity_key="food_grill_cook",
        version=1,
        display_name="Grill",
        category="food_production",
        unit_key="items",
        demand_mode="VOLUME",
        effective_from=datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Istanbul")),
        source_ref="activity:v1",
        approved_by="ops",
        required_skill_keys=("grill_station",),
        required_certification_keys=("food_safety",),
    )
    labor = ActivityLaborStandardVersion(
        tenant_id="tenant-a",
        activity_key="food_grill_cook",
        version=1,
        seconds_per_unit=Decimal("1800"),
        people=Decimal("1"),
        effective_from=datetime(2026, 1, 1, tzinfo=ZoneInfo("Europe/Istanbul")),
        source_ref="time-study:v1",
        approved_by="ie",
    )
    request = WorkActivityDemandRequest(
        tenant_id="tenant-a",
        location_id="WH-1",
        interval_start=AT,
        interval_minutes=60,
        model_version="generic-v1",
        signals=(
            WorkloadSignal(
                driver_key="pos:grill",
                activity_key="food_grill_cook",
                demand_mode="VOLUME",
                quantity=Decimal("4"),
                source_ref="forecast:v1",
            ),
        ),
    )
    return build_work_activity_demand_snapshot(request, (activity,), (labor,))


class ScheduledCapabilityRuntimeTests(unittest.TestCase):
    def test_skill_mix_gap_uses_canonical_employee_capabilities(self):
        people = {
            "EMP-1": {
                "employee_id": "EMP-1",
                "skill_keys": ["grill_station"],
                "certification_keys": ["food_safety"],
                "equipment_keys": [],
                "active": True,
            },
            "EMP-2": {
                "employee_id": "EMP-2",
                "skill_keys": ["checkout"],
                "certification_keys": ["food_safety"],
                "equipment_keys": [],
                "active": True,
            },
        }
        shifts = [
            {"id": "SHIFT-1", "person_id": "EMP-1", "warehouse_id": "WH-1", "date": "2026-08-20", "start": "15:00", "end": "16:00", "status": "Atandı"},
            {"id": "SHIFT-2", "person_id": "EMP-2", "warehouse_id": "WH-1", "date": "2026-08-20", "start": "15:00", "end": "16:00", "status": "Atandı"},
        ]
        with (
            patch.object(runtime, "build_catalog_demand_snapshot", return_value=demand_snapshot()),
            patch.object(runtime.service, "list_warehouses", return_value=[{"id": "WH-1", "name": "Site 1"}]),
            patch.object(runtime.service, "list_shifts", return_value=shifts),
            patch.object(runtime.service, "resolve_person_identity", side_effect=lambda employee_id, _method: people.get(employee_id)),
            patch.object(runtime.service, "person_has_workforce_access", return_value=True),
            patch.object(runtime.service, "_day_context", return_value={"on_approved_leave": False}),
        ):
            plan = runtime.build_scheduled_capacity_plan(
                worksite_id="WH-1",
                interval_start=AT,
                interval_minutes=60,
                model_version="generic-v1",
                signals=[{"driver_key": "pos:grill"}],
            )
        self.assertEqual(plan.required_man_hours, Decimal("2"))
        self.assertEqual(plan.available_man_hours, Decimal("2"))
        self.assertEqual(plan.allocated_man_hours, Decimal("1"))
        self.assertEqual(plan.deficit_man_hours, Decimal("1"))
        self.assertEqual(plan.root_cause, "skill_mix_constraint")
        self.assertEqual(plan.primary_capability_target, "activity:food_grill_cook")

    def test_approved_leave_is_not_counted_as_scheduled_capacity(self):
        person = {
            "employee_id": "EMP-1",
            "skill_keys": ["grill_station"],
            "certification_keys": ["food_safety"],
            "equipment_keys": [],
            "active": True,
        }
        with (
            patch.object(runtime, "build_catalog_demand_snapshot", return_value=demand_snapshot()),
            patch.object(runtime.service, "list_warehouses", return_value=[{"id": "WH-1", "name": "Site 1"}]),
            patch.object(runtime.service, "list_shifts", return_value=[{"id": "SHIFT-1", "person_id": "EMP-1", "warehouse_id": "WH-1", "date": "2026-08-20", "start": "15:00", "end": "16:00", "status": "Atandı"}]),
            patch.object(runtime.service, "resolve_person_identity", return_value=person),
            patch.object(runtime.service, "person_has_workforce_access", return_value=True),
            patch.object(runtime.service, "_day_context", return_value={"on_approved_leave": True}),
        ):
            plan = runtime.build_scheduled_capacity_plan(
                worksite_id="WH-1",
                interval_start=AT,
                interval_minutes=60,
                model_version="generic-v1",
                signals=[{"driver_key": "pos:grill"}],
            )
        self.assertEqual(plan.available_man_hours, Decimal("0"))
        self.assertEqual(plan.deficit_man_hours, Decimal("2"))
        self.assertEqual(plan.root_cause, "manpower_capacity_shortage")
        self.assertEqual(plan.recommended_people, 2)


if __name__ == "__main__":
    unittest.main()
