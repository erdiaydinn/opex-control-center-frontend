from copy import deepcopy
from hashlib import sha256
import os
import unittest
from unittest.mock import patch

from app.modules.workforce import pii, service
from app.modules.workforce.schemas import LeaveImportRow


PII_KEY = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="
LOOKUP_KEY = "QkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkJCQkI="


class WorkforceIdentityLeaveHardeningTests(unittest.TestCase):
    def setUp(self):
        self.people = deepcopy(service._PEOPLE)
        self.leaves = deepcopy(service._LEAVES)
        self.shifts = deepcopy(service._SHIFTS)
        self.attendance = deepcopy(service._ATTENDANCE)
        self.environment = patch.dict(os.environ, {
            "DOCKOS_ENV": "test",
            "OPEX_PII_KEY": PII_KEY,
            "OPEX_PII_LOOKUP_KEY": LOOKUP_KEY,
        }, clear=False)
        self.environment.start()

    def tearDown(self):
        service._PEOPLE[:] = self.people
        service._LEAVES[:] = self.leaves
        service._SHIFTS[:] = self.shifts
        service._ATTENDANCE[:] = self.attendance
        self.environment.stop()

    def test_employee_master_stores_keyed_lookup_digest_not_plain_sha256(self):
        tckn = "31987654310"
        service.upsert_people([{
            "employee_id": "EMP-HMAC-1",
            "roster_ids": ["RST-HMAC-1"],
            "full_name": "HMAC Test Person",
            "tckn": tckn,
            "position": "Picker",
            "warehouse_id": "fulya",
            "active": True,
        }], "test", persist=False)
        person = next(row for row in service._PEOPLE if row["employee_id"] == "EMP-HMAC-1")
        self.assertTrue(person["tckn_lookup_digest"].startswith("v1:"))
        self.assertNotEqual(person["tckn_lookup_digest"], sha256(tckn.encode()).hexdigest())
        self.assertNotIn("tckn_hash", person)
        self.assertEqual(service.resolve_person_identity(tckn, "TC")["employee_id"], "EMP-HMAC-1")
        public = next(row for row in service.list_people(False) if row["employee_id"] == "EMP-HMAC-1")
        self.assertNotIn("tckn_lookup_digest", public)
        self.assertNotIn("tckn_ciphertext", public)

    def test_production_requires_separate_lookup_key(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "OPEX_PII_KEY": PII_KEY}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "OPEX_PII_LOOKUP_KEY"):
                pii.ensure_lookup_key_ready()

    def test_legacy_sha256_identity_is_migrated_from_encrypted_source(self):
        tckn = "31987654311"
        service._PEOPLE[:] = [{
            "id": "EMP-LEGACY-1",
            "employee_id": "EMP-LEGACY-1",
            "full_name": "Legacy Identity",
            "tckn_hash": sha256(tckn.encode()).hexdigest(),
            "tckn_ciphertext": pii.encrypt(tckn, "EMP-LEGACY-1"),
            "active": True,
        }]
        migrated = service._migrate_identity_lookup_digests()
        self.assertEqual(migrated, 1)
        person = service._PEOPLE[0]
        self.assertNotIn("tckn_hash", person)
        self.assertEqual(person["tckn_lookup_digest"], pii.lookup_digest(tckn))
        self.assertEqual(service.resolve_person_identity(tckn, "TC")["employee_id"], "EMP-LEGACY-1")

    def test_leave_schema_defaults_to_zero_not_synthetic_workday(self):
        row = LeaveImportRow(
            person_id="EMP-HMAC-1",
            type_id="annual",
            category="Yıllık İzin",
            date="2026-09-03",
        )
        self.assertEqual(row.minutes, 0)

    def test_zero_minute_leave_uses_authoritative_planned_shift(self):
        service._PEOPLE[:] = [{
            "id": "EMP-LEAVE-1", "employee_id": "EMP-LEAVE-1", "full_name": "Planlı İzin",
            "warehouse_id": "fulya", "active": True,
        }]
        service._LEAVES[:] = []
        service._SHIFTS.append({
            "id": "SHIFT-LEAVE-PLAN", "person_id": "EMP-LEAVE-1", "person_name": "Planlı İzin",
            "warehouse_id": "fulya", "warehouse": "Fulya (İstanbul)", "date": "2026-09-03",
            "start": "08:00", "end": "17:00", "break_minutes": 60,
            "expected_minutes": 480, "role": "Picker", "status": "Atandı",
        })
        with patch.object(service, "_append_audit", return_value={}):
            result = service.import_leaves([{
                "person_id": "EMP-LEAVE-1", "source_person_id": "EMP-LEAVE-1",
                "identity_method": "EMPLOYEE_ID", "person_name": "Planlı İzin",
                "type_id": "annual", "category": "Yıllık İzin", "date": "2026-09-03",
                "minutes": 0, "approval": "Onaylandı", "source": "DM Time Off",
            }], "test", "leave.xlsx")
        self.assertEqual(result["inserted"], 1)
        self.assertEqual(result["duration_derived"], 1)
        self.assertEqual(result["duration_unresolved"], 0)
        leave = next(row for row in service._LEAVES if row["person_id"] == "EMP-LEAVE-1")
        self.assertEqual(leave["minutes"], 480)
        self.assertEqual(leave["duration_source"], "PLANNED_SHIFT")
        self.assertFalse(leave["requires_duration_review"])

    def test_leave_without_plan_stays_zero_and_requires_review(self):
        service._PEOPLE[:] = [{
            "id": "EMP-LEAVE-2", "employee_id": "EMP-LEAVE-2", "full_name": "Plansız İzin",
            "warehouse_id": "fulya", "active": True,
        }]
        service._LEAVES[:] = []
        service._SHIFTS[:] = [row for row in service._SHIFTS if row.get("person_id") != "EMP-LEAVE-2"]
        service._ATTENDANCE[:] = [row for row in service._ATTENDANCE if row.get("person_id") != "EMP-LEAVE-2"]
        with patch.object(service, "_append_audit", return_value={}):
            result = service.import_leaves([{
                "person_id": "EMP-LEAVE-2", "source_person_id": "EMP-LEAVE-2",
                "identity_method": "EMPLOYEE_ID", "person_name": "Plansız İzin",
                "type_id": "annual", "category": "Yıllık İzin", "date": "2026-09-04",
                "minutes": 0, "approval": "Onaylandı", "source": "DM Time Off",
            }], "test", "leave.xlsx")
        self.assertEqual(result["duration_unresolved"], 1)
        leave = service._LEAVES[0]
        self.assertEqual(leave["minutes"], 0)
        self.assertEqual(leave["duration_source"], "UNRESOLVED")
        self.assertTrue(leave["requires_duration_review"])
        status = next(row for row in service.list_daily_status() if row["person_id"] == "EMP-LEAVE-2")
        self.assertTrue(status["leave_duration_unresolved"])
        self.assertTrue(status["requires_review"])


if __name__ == "__main__":
    unittest.main()
