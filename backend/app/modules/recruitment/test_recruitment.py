import unittest
from unittest.mock import patch

from .schemas import RecruitmentDecision, RecruitmentRequestCreate
from . import service


FULYA = {"id": "WH-287-FULYA", "name": "Fulya (İstanbul)"}


class RecruitmentRuleTests(unittest.TestCase):
    def base_settings(self):
        return {
            "hr_recipients": [],
            "partner_recipients": [],
            "default_manager_capacity": 1,
            "warehouse_manager_capacity": {"Fulya (İstanbul)": 2},
            "counted_position_codes": ["STORE_STAFF", "ASSISTANT_MANAGER", "STORE_SUPPORT"],
        }

    def evaluate(self, position="STORE_STAFF", quantity=1, headcount=None, departure=None):
        current = headcount or {
            "active_staff": 15,
            "active_managers": 2,
            "by_position": {
                "STORE_STAFF": 14,
                "ASSISTANT_MANAGER": 1,
                "STORE_SUPPORT": 0,
                "STORE_MANAGER": 2,
            },
        }
        with (
            patch.object(service, "_find_warehouse", return_value=FULYA),
            patch.object(service, "list_norms", return_value=[{
                "id": "NORM-FULYA", "warehouse": "Fulya (İstanbul)", "norm": 34,
                "active": True, "regional_manager": "Ali Sancaktar",
                "regional_executive": "Özhan Alpay",
            }]),
            patch.object(service, "_headcount", return_value=current),
            patch.object(service, "_open_positions", return_value=0),
            patch.object(service, "get_settings", return_value=self.base_settings()),
            patch.object(service, "list_people", return_value=[]),
        ):
            return service.evaluate(FULYA["id"], position, quantity, departure)

    def test_managers_are_excluded_from_staffing_norm(self):
        result = self.evaluate()
        self.assertEqual(result["capacity"], 34)
        self.assertEqual(result["active"], 15)
        self.assertEqual(result["available"], 19)

    def test_fulya_has_two_manager_capacity(self):
        result = self.evaluate(position="STORE_MANAGER")
        self.assertEqual(result["capacity"], 2)
        self.assertEqual(result["active"], 2)
        self.assertEqual(result["recommendation"], "REJECT")

    def test_planned_departure_requires_employee_details(self):
        with self.assertRaisesRegex(ValueError, "ayrılacak personel"):
            RecruitmentRequestCreate(
                warehouse_id="Fulya (İstanbul)", position_code="STORE_STAFF",
                quantity=1, employment_type="FULL_TIME", reason_code="PLANNED_DEPARTURE",
                needed_by="2026-08-01", justification="Planlı ayrılış nedeniyle önden talep açılır.",
            )

    def test_default_norm_source_contains_fulya(self):
        fulya = next(row for row in service._default_norms() if row["warehouse"] == "Fulya (İstanbul)")
        self.assertEqual(fulya["norm"], 34)
        self.assertEqual(fulya["regional_executive"], "Özhan Alpay")

    def test_human_decision_has_no_arbitrary_minimum_length(self):
        decision = RecruitmentDecision(decision="APPROVED", note="uygun")
        self.assertEqual(decision.note, "uygun")

    def test_approved_vacancy_hire_activates_employee_master_and_workforce(self):
        request = {
            "id": "REC-HIRE-1", "status": "APPROVED", "quantity": 1, "hires": [],
            "warehouse_id": FULYA["id"], "warehouse_name": FULYA["name"],
            "position_code": "STORE_STAFF", "position_label": "Mağaza Görevlisi",
            "history": [], "created_at": "2026-08-01T00:00:00+00:00",
        }
        payload = {"employee_id": "EMP-HIRED", "roster_ids": ["RST-HIRED"], "full_name": "Yeni Çalışan", "tckn": "12345098765", "email": None, "phone": None, "employment_start": "2026-08-20"}
        with (
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "upsert_people", return_value={"created": 1, "updated": 0, "total": 1, "roster_conflicts": []}) as upsert,
            patch.object(service, "_save_request") as save,
            patch.object(service.persistence, "append_audit"),
        ):
            result = service.activate_hire(request["id"], payload, "hr@opex.local")
        self.assertEqual(result["status"], "FILLED")
        self.assertEqual(result["activation"]["workforce"], "ACTIVE")
        self.assertEqual(upsert.call_args.args[0][0]["warehouse_id"], FULYA["id"])
        self.assertEqual(upsert.call_args.args[0][0]["position"], "Mağaza Görevlisi")
        save.assert_called_once()

    def test_open_position_count_decreases_after_partial_hire(self):
        requests = [{"id": "REC-PARTIAL", "warehouse_name": FULYA["name"], "position_code": "STORE_STAFF", "quantity": 3, "hires": [{"employee_id": "1"}], "status": "PARTIALLY_FILLED"}]
        with patch.object(service, "list_requests", return_value=requests):
            self.assertEqual(service._open_positions(FULYA["name"], "STORE_STAFF"), 2)


if __name__ == "__main__":
    unittest.main()
