import unittest
from unittest.mock import patch

from . import hr_actual
from .schemas import RecruitmentHrActualImport


class RecruitmentHrActualTests(unittest.TestCase):
    def payload(self):
        return {
            "source_name": "hr-actual.xlsx",
            "as_of": "2026-08-20",
            "rows": [
                {
                    "employee_id": "HR-100",
                    "tckn": "12345678901",
                    "warehouse": "Fulya",
                    "position": "Mağaza Görevlisi",
                    "fte": 1,
                    "active": True,
                },
                {
                    "employee_id": "HR-200",
                    "warehouse": "Fulya",
                    "position": "Mağaza Müdür Yardımcısı",
                    "fte": 0.5,
                    "active": True,
                },
            ],
        }

    def test_schema_requires_employee_id_or_tckn(self):
        with self.assertRaisesRegex(ValueError, "employee_id veya TCKN"):
            RecruitmentHrActualImport.model_validate({
                "source_name": "actual.xlsx",
                "as_of": "2026-08-20",
                "rows": [{"warehouse": "Fulya", "position": "Picker"}],
            })

    def test_import_resolves_identity_but_never_persists_tckn(self):
        captured = {}

        def persist(collections, event, actor, **details):
            captured["collections"] = collections
            captured["event"] = event
            captured["actor"] = actor
            captured["details"] = details

        with (
            patch.object(hr_actual, "list_warehouses", return_value=[{
                "id": "WH-287-FULYA", "name": "Fulya (İstanbul)", "code": "FULYA",
            }]),
            patch.object(
                hr_actual,
                "resolve_person_identity",
                side_effect=lambda value, method: {
                    "employee_id": "EMP-CANON", "warehouse_id": "WH-287-FULYA"
                } if value in {"12345678901", "HR-200"} else None,
            ),
            patch.object(hr_actual.persistence, "load_collection", return_value=[]) as load_collection,
            patch.object(hr_actual.persistence, "persist_snapshot_with_audit", side_effect=persist) as persist_snapshot,
        ):
            summary = hr_actual.import_snapshot(self.payload(), "hr@example.test")

        snapshot = captured["collections"]["recruitment_hr_actual"][0]
        load_collection.assert_called_once_with("recruitment_hr_actual")
        self.assertLess(load_collection.call_count, persist_snapshot.call_count + 1)
        self.assertEqual(captured["event"], "RECRUITMENT_HR_ACTUAL_IMPORTED")
        self.assertEqual(summary["active_rows"], 2)
        self.assertEqual(summary["active_fte"], 1.5)
        self.assertEqual(summary["matched_rows"], 2)
        self.assertEqual(summary["unmatched_rows"], 0)
        self.assertEqual(snapshot["rows"][0]["employee_id"], "EMP-CANON")
        self.assertEqual(snapshot["rows"][0]["identity_method"], "TCKN")
        self.assertTrue(all("tckn" not in row for row in snapshot["rows"]))
        self.assertTrue(all("full_name" not in row for row in snapshot["rows"]))

    def test_import_primes_persisted_revision_before_cas_write(self):
        calls = []

        def load(kind):
            calls.append(("load", kind))
            return [{"id": kind, "source_sha256": "previous"}]

        def persist(collections, event, actor, **details):
            calls.append(("persist", next(iter(collections))))

        with (
            patch.object(hr_actual, "list_warehouses", return_value=[{
                "id": "WH-287-FULYA", "name": "Fulya (İstanbul)", "code": "FULYA",
            }]),
            patch.object(hr_actual, "resolve_person_identity", return_value={"employee_id": "EMP-CANON", "warehouse_id": "WH-287-FULYA"}),
            patch.object(hr_actual.persistence, "load_collection", side_effect=load),
            patch.object(hr_actual.persistence, "persist_snapshot_with_audit", side_effect=persist),
        ):
            hr_actual.import_snapshot(self.payload(), "hr@example.test")

        self.assertEqual(calls[0], ("load", "recruitment_hr_actual"))
        self.assertEqual(calls[-1], ("persist", "recruitment_hr_actual"))

    def test_hr_actual_enriches_staffing_without_replacing_decision_authority(self):
        snapshot = {
            "source_name": "hr-actual.xlsx",
            "as_of": "2026-08-20",
            "rows": [
                {"warehouse": "Fulya (İstanbul)", "position_code": "STORE_STAFF", "fte": 1, "active": True, "matched": True},
                {"warehouse": "Fulya (İstanbul)", "position_code": "ASSISTANT_MANAGER", "fte": 0.5, "active": True, "matched": False},
                {"warehouse": "Fulya (İstanbul)", "position_code": "STORE_MANAGER", "fte": 1, "active": True, "matched": True},
            ],
        }
        evaluation = {
            "warehouse_name": "Fulya (İstanbul)", "position_code": "STORE_STAFF",
            "active": 3, "capacity": 5, "available": 2,
        }
        with patch.object(hr_actual, "latest_snapshot", return_value=snapshot):
            result = hr_actual.enrich_evaluation(evaluation)
        self.assertEqual(result["hr_actual"], 2)
        self.assertEqual(result["hr_actual_fte"], 1.5)
        self.assertEqual(result["hr_actual_unmatched"], 1)
        self.assertEqual(result["hr_actual_delta"], 1)
        self.assertEqual(result["actual_authority"], "HR_SNAPSHOT")
        self.assertEqual(result["decision_actual_source"], "EMPLOYEE_MASTER")

    def test_dashboard_returns_scope_safe_staffing_rows(self):
        evaluation = {
            "warehouse_name": "Fulya (İstanbul)", "position_code": "STORE_STAFF",
            "active": 10, "capacity": 12, "available": 2,
        }
        with (
            patch.object(hr_actual, "evaluate", return_value=evaluation),
            patch.object(hr_actual, "enrich_evaluation", side_effect=lambda value: {**value, "hr_actual": 9, "hr_actual_unmatched": 0}),
        ):
            result = hr_actual.build_dashboard(
                [{"warehouse": "Fulya (İstanbul)"}],
                [{"status": "PENDING_APPROVAL"}],
            )
        self.assertEqual(result["pending"], 1)
        self.assertEqual(result["norm_gap_warehouses"], 1)
        self.assertEqual(result["warehouse_rows"][0]["hr_actual"], 9)


if __name__ == "__main__":
    unittest.main()