import json
import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import command_center


ISTANBUL = ZoneInfo("Europe/Istanbul")


class WorkforceCommandCenterTests(unittest.TestCase):
    def authority(self, start=None):
        start = start or datetime(2026, 8, 21, 8, 0, tzinfo=ISTANBUL)
        return {
            "tenant_id": "tenant-a",
            "location_id": "WH-1",
            "interval_start": start,
            "interval_minutes": 60,
            "dpi": {
                "id": "DPI-1",
                "model_version": "dpi-v1",
                "snapshot_fingerprint": "d" * 64,
                "demand_snapshot_fingerprint": "a" * 64,
                "capacity_snapshot_fingerprint": "b" * 64,
                "required_man_hours": Decimal("3"),
                "effective_man_hours": Decimal("2"),
                "skill_deficit_man_hours": Decimal("1"),
                "demand_pressure_index": Decimal("1.5"),
                "capacity_gap_man_hours": Decimal("1"),
                "capacity_sufficient": False,
                "kpi_bad": True,
                "bad_kpi_keys": ["picking_seconds_per_order"],
                "manpower_shortage": True,
                "root_cause": "capacity_deficit",
                "automatic_extra_people_permitted": False,
                "staffing_review_required": True,
                "kpi_observations": [{"key": "picking_seconds_per_order", "actual": "180"}],
                "explanation": ["capacity_gap_positive"],
                "created_at": start,
            },
            "demand": {
                "id": "DEM-1",
                "model_version": "demand-v1",
                "required_people": Decimal("3"),
                "labor_standard_refs": ["picking:v1"],
                "contributors": [{"driver_key": "orders", "man_hours": "3"}],
                "created_at": start,
            },
            "capacity": {
                "id": "CAP-1",
                "model_version": "capacity-v1",
                "scheduled_man_hours": Decimal("2"),
                "absence_man_hours": Decimal("0"),
                "break_man_hours": Decimal("0"),
                "unavailable_man_hours": Decimal("0"),
                "net_available_man_hours": Decimal("2"),
                "skill_feasible_man_hours": Decimal("2"),
                "skill_deficit_man_hours": Decimal("1"),
                "productivity_factor": Decimal("1"),
                "effective_man_hours": Decimal("2"),
                "scheduled_fte": Decimal("2"),
                "effective_capacity": Decimal("2"),
                "skill_deficits": {"picking": "1"},
                "unused_worker_hours": {},
                "source_refs": ["schedule://WH-1"],
                "contributors": [],
                "created_at": start,
            },
            "replan": {
                "id": "SCN-1",
                "scenario_fingerprint": "c" * 64,
                "scenario_gap_man_hours": Decimal("1.5"),
                "scenario_dpi": Decimal("1.7"),
                "dpi_delta": Decimal("0.2"),
                "predicted_kpi_deltas": {"picking": "5"},
                "estimated_scenario_cost_minor_units": 1000,
                "cost_delta_minor_units": 200,
                "shocks": [{"shock_type": "absence"}],
                "recommendation": "rerun_constraint_optimizer_for_capacity_loss",
                "replan_required": True,
                "automatic_apply_permitted": False,
                "human_approval_required": True,
                "proposal_fingerprint": "e" * 64,
                "created_at": start,
            },
        }

    def shifts(self):
        return [
            {"id": "S1", "person_id": "P1", "warehouse_id": "WH-1", "date": "2026-08-21", "start": "08:00", "end": "09:00", "break_minutes": 0, "expected_minutes": 60, "status": "Atandı"},
            {"id": "S2", "person_id": "P2", "warehouse_id": "WH-1", "date": "2026-08-21", "start": "08:00", "end": "09:00", "break_minutes": 0, "expected_minutes": 60, "status": "Atandı"},
        ]

    def build(self, *, authority=None, shifts=None, now=None, trades=None):
        authority = authority or self.authority()
        shifts = shifts or self.shifts()
        now = now or datetime(2026, 8, 21, 8, 45, tzinfo=ISTANBUL)
        trades = trades if trades is not None else [{"id": "T1", "status": "PENDING_MANAGER_APPROVAL"}]
        attendance = [{"id": "A1", "shift_id": "S1", "person_id": "P1", "warehouse": "WH-1", "date": "21.08.2026", "check_in": "08:05", "check_out": None, "status": "Vardiyada"}]
        breaks = [{"id": "B1", "shift_id": "S1", "person_id": "P1", "started_at": "2026-08-21T08:30:00+03:00"}]
        with (
            patch.object(command_center, "get_command_center_authority", return_value=authority),
            patch.object(command_center.persistence, "ENABLED", False),
            patch.object(command_center.service, "list_shifts", return_value=shifts),
            patch.object(command_center.service, "list_attendance", return_value=attendance),
            patch.object(command_center.service, "list_breaks", return_value=breaks),
            patch.object(command_center.service, "_rule_value", side_effect=lambda key, *_: 660),
            patch.object(command_center, "_location_matches", return_value=True),
            patch.object(command_center, "_attendance_location", return_value="WH-1"),
            patch.object(command_center.shift_trade_views, "list_manager_shift_trades", return_value=trades),
        ):
            return command_center.build_command_center("WH-1", now=now)

    def test_current_interval_composes_live_operations_and_governed_actions(self):
        result = self.build()
        self.assertEqual(result["interval"]["relation"], "CURRENT")
        self.assertEqual(result["operations"]["scheduled_people"], 2)
        self.assertEqual(result["operations"]["attendance_started_people"], 1)
        self.assertEqual(result["operations"]["actual_present_people"], 1)
        self.assertEqual(result["operations"]["no_show_count"], 1)
        self.assertEqual(result["operations"]["active_break_count"], 1)
        self.assertFalse(result["automatic_schedule_apply_permitted"])
        self.assertTrue(result["human_in_loop"])
        codes = [row["code"] for row in result["action_queue"]]
        self.assertEqual(
            codes,
            ["CAPACITY_SHORTAGE", "SKILL_DEFICIT", "NO_SHOW", "KPI_PRESSURE", "PENDING_REPLAN", "PENDING_SHIFT_TRADE"],
        )
        self.assertTrue(all(row["requires_human_approval"] for row in result["action_queue"]))

    def test_past_authority_never_receives_live_label(self):
        result = self.build(now=datetime(2026, 8, 21, 10, 0, tzinfo=ISTANBUL))
        self.assertEqual(result["interval"]["relation"], "PAST")
        self.assertIsNone(result["operations"]["actual_present_people"])
        self.assertFalse(result["truth_boundary"]["live_label_permitted"])
        self.assertEqual(result["action_queue"][0]["code"], "AUTHORITY_INTERVAL_NOT_CURRENT")
        self.assertFalse(result["action_queue"][0]["requires_human_approval"])

    def test_daily_limit_uses_canonical_rule_and_adds_no_early_warning_threshold(self):
        shifts = [
            {"id": "S1", "person_id": "P1", "warehouse_id": "WH-1", "date": "2026-08-21", "start": "06:00", "end": "12:00", "expected_minutes": 360, "status": "Atandı"},
            {"id": "S2", "person_id": "P1", "warehouse_id": "WH-1", "date": "2026-08-21", "start": "13:00", "end": "19:00", "expected_minutes": 360, "status": "Atandı"},
        ]
        result = self.build(shifts=shifts, trades=[])
        self.assertEqual(result["operations"]["daily_limit_breach_count"], 1)
        codes = [row["code"] for row in result["action_queue"]]
        self.assertIn("DAILY_LIMIT_BREACH", codes)
        self.assertNotIn("DAILY_LIMIT_WARNING", codes)

    def test_manager_read_model_contains_no_sensitive_identity_material(self):
        result = self.build()
        serialized = json.dumps(result, default=str).casefold()
        for forbidden in ("tckn", "national_id", "ciphertext", "lookup_digest"):
            self.assertNotIn(forbidden, serialized)
        self.assertFalse(result["truth_boundary"]["schedule_mutation_performed"])
        self.assertFalse(result["truth_boundary"]["repository_or_synthetic_evidence_is_field_proof"])


if __name__ == "__main__":
    unittest.main()
