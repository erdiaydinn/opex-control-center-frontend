import unittest
from datetime import UTC, datetime
from decimal import Decimal

from .demand_model import PickerDemandComponents
from .industry_activity_templates import (
    LEGACY_DARKSTORE_ACTIVITY_MAP,
    get_template,
    starter_candidates,
)
from .work_activity_authority import (
    ActivityLaborStandardVersion,
    WorkActivityAuthorityError,
    WorkActivityDemandRequest,
    WorkActivityVersion,
    WorkloadSignal,
    build_work_activity_demand_snapshot,
    resolve_activity,
)


AT = datetime(2026, 8, 20, 12, 0, tzinfo=UTC)


class WorkActivityAuthorityTests(unittest.TestCase):
    def activity(
        self,
        activity_key: str,
        *,
        tenant_id: str = "tenant-a",
        demand_mode: str = "VOLUME",
        display_name: str | None = None,
        status: str = "APPROVED",
        skills: tuple[str, ...] = (),
        certifications: tuple[str, ...] = (),
    ) -> WorkActivityVersion:
        return WorkActivityVersion(
            tenant_id=tenant_id,
            activity_key=activity_key,
            version=1,
            display_name=display_name or activity_key.replace("_", " ").title(),
            category="operations",
            unit_key="items" if demand_mode == "VOLUME" else "cycles",
            demand_mode=demand_mode,
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            source_ref="tenant-approved-activity-v1",
            approved_by="ops-admin@example.test",
            required_skill_keys=skills,
            required_certification_keys=certifications,
            status=status,
        )

    def standard(
        self,
        activity_key: str,
        *,
        tenant_id: str = "tenant-a",
        seconds: str = "60",
    ) -> ActivityLaborStandardVersion:
        return ActivityLaborStandardVersion(
            tenant_id=tenant_id,
            activity_key=activity_key,
            version=1,
            seconds_per_unit=Decimal(seconds),
            people=Decimal("1"),
            effective_from=datetime(2026, 1, 1, tzinfo=UTC),
            source_ref="time-study:approved:v1",
            approved_by="industrial-engineering@example.test",
        )

    def request(self, signal: WorkloadSignal) -> WorkActivityDemandRequest:
        return WorkActivityDemandRequest(
            tenant_id="tenant-a",
            location_id="LOC-001",
            interval_start=AT,
            interval_minutes=60,
            model_version="generic-work-activity-v1",
            signals=(signal,),
        )

    def test_qsr_fixed_sanitation_and_factory_machine_work_are_generic(self):
        qsr = get_template("qsr")
        factory = get_template("manufacturing")
        qsr_keys = {item.activity_key for item in qsr.activities}
        factory_keys = {item.activity_key for item in factory.activities}
        self.assertIn("warmer_sanitation", qsr_keys)
        self.assertIn("food_grill_cook", qsr_keys)
        self.assertIn("machine_operation", factory_keys)
        self.assertIn("line_changeover", factory_keys)

    def test_starter_templates_never_ship_guessed_labor_authority(self):
        for template_key in ("darkstore", "qsr", "supermarket", "manufacturing", "convenience_kiosk"):
            for row in starter_candidates(template_key):
                self.assertNotIn("seconds_per_unit", row)
                self.assertNotIn("people", row)
                self.assertNotIn("approved_by", row)
                self.assertNotIn("labor_standard", row)

    def test_non_zero_demand_without_approved_labor_standard_fails_closed(self):
        activity = self.activity("food_grill_cook", skills=("grill_station",), certifications=("food_safety",))
        signal = WorkloadSignal(
            driver_key="orders:12:00:grill",
            activity_key="food_grill_cook",
            demand_mode="VOLUME",
            quantity=Decimal("20"),
            source_ref="pos:forecast:12:00",
        )
        with self.assertRaisesRegex(WorkActivityAuthorityError, "no approved effective labor standard"):
            build_work_activity_demand_snapshot(self.request(signal), [activity], [])

    def test_activity_and_labor_authority_calculate_explainable_demand(self):
        activity = self.activity(
            "machine_operation",
            skills=("machine_operation",),
            certifications=("machine_authorization",),
        )
        standard = self.standard("machine_operation", seconds="90")
        signal = WorkloadSignal(
            driver_key="mes:line-7:planned-units",
            activity_key="machine_operation",
            demand_mode="VOLUME",
            quantity=Decimal("40"),
            source_ref="mes:line-7:2026-08-20T12",
        )
        snapshot = build_work_activity_demand_snapshot(self.request(signal), [activity], [standard])
        self.assertEqual(snapshot.required_man_hours, Decimal("1"))
        self.assertEqual(snapshot.required_people, Decimal("1"))
        contribution = snapshot.contributions[0]
        self.assertEqual(contribution.activity_key, "machine_operation")
        self.assertEqual(contribution.required_skill_keys, ("machine_operation",))
        self.assertEqual(contribution.required_certification_keys, ("machine_authorization",))
        self.assertEqual(len(snapshot.input_fingerprint), 64)
        self.assertEqual(len(snapshot.snapshot_fingerprint), 64)

    def test_fixed_work_uses_occurrence_count_without_special_case_hardcoding(self):
        activity = self.activity("warmer_sanitation", demand_mode="FIXED", certifications=("food_safety",))
        standard = self.standard("warmer_sanitation", seconds="900")
        signal = WorkloadSignal(
            driver_key="schedule:warmer-clean:close",
            activity_key="warmer_sanitation",
            demand_mode="FIXED",
            quantity=Decimal("2"),
            source_ref="site:sanitation-plan:v4",
        )
        snapshot = build_work_activity_demand_snapshot(self.request(signal), [activity], [standard])
        self.assertEqual(snapshot.required_man_hours, Decimal("0.5"))

    def test_cross_tenant_activity_or_standard_never_resolves(self):
        signal = WorkloadSignal(
            driver_key="retail:checkout",
            activity_key="checkout_service",
            demand_mode="VOLUME",
            quantity=Decimal("10"),
            source_ref="pos:forecast",
        )
        activity = self.activity("checkout_service", tenant_id="tenant-b")
        standard = self.standard("checkout_service", tenant_id="tenant-b")
        with self.assertRaisesRegex(WorkActivityAuthorityError, "no approved effective work activity"):
            build_work_activity_demand_snapshot(self.request(signal), [activity], [standard])

    def test_retired_activity_cannot_be_used_for_new_demand(self):
        retired = self.activity("food_grill_cook", status="RETIRED")
        with self.assertRaisesRegex(WorkActivityAuthorityError, "no approved effective work activity"):
            resolve_activity([retired], tenant_id="tenant-a", activity_key="food_grill_cook", at=AT)

    def test_darkstore_legacy_keys_have_explicit_generic_migration_targets(self):
        legacy_keys = set(PickerDemandComponents().as_mapping())
        self.assertEqual(legacy_keys, set(LEGACY_DARKSTORE_ACTIVITY_MAP))
        generic_keys = {item.activity_key for item in get_template("darkstore").activities}
        self.assertTrue(set(LEGACY_DARKSTORE_ACTIVITY_MAP.values()).issubset(generic_keys))


if __name__ == "__main__":
    unittest.main()
