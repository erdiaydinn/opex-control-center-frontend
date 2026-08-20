import unittest
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

from . import hr_actual
from .schemas import RecruitmentHrActualImport


class RecruitmentHrActualTests(unittest.TestCase):
    def payload(self):
        return {
            "source_name": "hr-actual.xlsx",
            "as_of": "2026-08-20",
            "rows": [
                {"employee_id": "HR-100", "tckn": "12345678901", "warehouse": "Fulya", "position": "Mağaza Görevlisi", "fte": 1, "active": True},
                {"employee_id": "HR-200", "warehouse": "Fulya", "position": "Mağaza Müdür Yardımcısı", "fte": 0.5, "active": True},
            ],
        }

    def test_schema_requires_employee_id_or_tckn(self):
        with self.assertRaisesRegex(ValueError, "employee_id veya TCKN"):
            RecruitmentHrActualImport.model_validate({"source_name": "actual.xlsx", "as_of": "2026-08-20", "rows": [{"warehouse": "Fulya", "position": "Picker"}]})

    def test_import_resolves_identity_but_never_persists_tckn(self):
        captured = {}
        def persist(collections, event, actor, **details):
            captured.update(collections=collections, event=event, actor=actor, details=details)
        with (
            patch.object(hr_actual, "list_warehouses", return_value=[{"id": "WH-287-FULYA", "name": "Fulya (İstanbul)", "code": "FULYA"}]),
            patch.object(hr_actual, "resolve_person_identity", side_effect=lambda value, method: {"employee_id": "EMP-CANON", "warehouse_id": "WH-287-FULYA"} if value in {"12345678901", "HR-200"} else None),
            patch.object(hr_actual.persistence, "load_collection", return_value=[]) as load_collection,
            patch.object(hr_actual.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            summary = hr_actual.import_snapshot(self.payload(), "hr@example.test")
        snapshot = captured["collections"]["recruitment_hr_actual"][0]
        load_collection.assert_called_once_with("recruitment_hr_actual")
        self.assertEqual(captured["event"], "RECRUITMENT_HR_ACTUAL_IMPORTED")
        self.assertEqual(summary["active_fte"], 1.5)
        self.assertEqual(summary["matched_rows"], 2)
        self.assertTrue(all("tckn" not in row and "full_name" not in row for row in snapshot["rows"]))

    def test_import_primes_persisted_revision_before_cas_write(self):
        calls = []
        with (
            patch.object(hr_actual, "list_warehouses", return_value=[{"id": "WH-287-FULYA", "name": "Fulya (İstanbul)", "code": "FULYA"}]),
            patch.object(hr_actual, "resolve_person_identity", return_value={"employee_id": "EMP-CANON", "warehouse_id": "WH-287-FULYA"}),
            patch.object(hr_actual.persistence, "load_collection", side_effect=lambda kind: calls.append(("load", kind)) or []),
            patch.object(hr_actual.persistence, "persist_snapshot_with_audit", side_effect=lambda collections, *args, **kwargs: calls.append(("persist", next(iter(collections))))),
        ):
            hr_actual.import_snapshot(self.payload(), "hr@example.test")
        self.assertEqual(calls[0], ("load", "recruitment_hr_actual"))
        self.assertEqual(calls[-1], ("persist", "recruitment_hr_actual"))

    def test_committed_projection_counts_future_starts_and_confirmed_exits(self):
        today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
        evaluation = {
            "warehouse_id": "WH-287-FULYA", "warehouse_name": "Fulya (İstanbul)",
            "position_code": "STORE_STAFF", "active": 10, "capacity": 15, "open_positions": 1,
        }
        people = [
            {"employee_id": "START-1", "active": True, "warehouse_id": "WH-287-FULYA", "position": "Mağaza Görevlisi", "employment_start": (today + timedelta(days=10)).isoformat(), "fte": 1},
            {"employee_id": "EXIT-1", "active": True, "warehouse_id": "WH-287-FULYA", "position": "Mağaza Görevlisi", "employment_end": (today + timedelta(days=20)).isoformat(), "fte": 1},
            {"employee_id": "LATE-START", "active": True, "warehouse_id": "WH-287-FULYA", "position": "Mağaza Görevlisi", "employment_start": (today + timedelta(days=50)).isoformat(), "fte": 0.5},
        ]
        result_30 = hr_actual._projection_for_days(evaluation, people, 30)
        result_60 = hr_actual._projection_for_days(evaluation, people, 60)
        self.assertEqual(result_30["incoming"], 1)
        self.assertEqual(result_30["confirmed_exits"], 1)
        self.assertEqual(result_30["committed_headcount"], 10)
        self.assertEqual(result_30["uncovered_gap"], 4)
        self.assertEqual(result_60["incoming"], 2)
        self.assertEqual(result_60["committed_headcount"], 11)
        self.assertEqual(result_60["uncovered_gap"], 3)

    def test_hr_actual_enriches_staffing_without_replacing_decision_authority(self):
        snapshot = {
            "source_name": "hr-actual.xlsx", "as_of": "2026-08-20",
            "rows": [
                {"warehouse": "Fulya (İstanbul)", "position_code": "STORE_STAFF", "fte": 1, "active": True, "matched": True},
                {"warehouse": "Fulya (İstanbul)", "position_code": "ASSISTANT_MANAGER", "fte": 0.5, "active": True, "matched": False},
                {"warehouse": "Fulya (İstanbul)", "position_code": "STORE_MANAGER", "fte": 1, "active": True, "matched": True},
            ],
        }
        evaluation = {"warehouse_id": "WH-287-FULYA", "warehouse_name": "Fulya (İstanbul)", "position_code": "STORE_STAFF", "active": 3, "capacity": 5, "available": 2, "open_positions": 0}
        with patch.object(hr_actual, "latest_snapshot", return_value=snapshot), patch.object(hr_actual, "list_people", return_value=[]):
            result = hr_actual.enrich_evaluation(evaluation)
        self.assertEqual(result["hr_actual"], 2)
        self.assertEqual(result["hr_actual_fte"], 1.5)
        self.assertEqual(result["hr_actual_unmatched"], 1)
        self.assertEqual(result["hr_actual_delta"], 1)
        self.assertEqual(result["committed_headcount"], 3)
        self.assertEqual(result["actual_authority"], "HR_SNAPSHOT")
        self.assertEqual(result["decision_actual_source"], "EMPLOYEE_MASTER")

    def test_dashboard_returns_scope_safe_staffing_rows(self):
        evaluation = {"warehouse_id": "WH-287-FULYA", "warehouse_name": "Fulya (İstanbul)", "position_code": "STORE_STAFF", "active": 10, "capacity": 12, "available": 2, "open_positions": 0}
        with (
            patch.object(hr_actual, "evaluate", return_value=evaluation),
            patch.object(hr_actual, "enrich_evaluation", side_effect=lambda value: {**value, "hr_actual": 9, "hr_actual_unmatched": 0, "uncovered_gap": 2}),
        ):
            result = hr_actual.build_dashboard([{"warehouse": "Fulya (İstanbul)"}], [{"status": "PENDING_APPROVAL"}])
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["norm_gap_warehouses"], 1)
        self.assertEqual(result["uncovered_gap_warehouses"], 1)
        self.assertEqual(result["warehouse_rows"][0]["hr_actual"], 9)


if __name__ == "__main__":
    unittest.main()