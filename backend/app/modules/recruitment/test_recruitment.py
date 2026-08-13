import unittest
import os
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import UTC, datetime
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.main import app
from . import router as recruitment_router

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
            "history": [], "candidates": [{"id": "CAND-HIRED", "status": "APPROVED"}],
            "created_at": "2026-08-01T00:00:00+00:00",
        }
        payload = {"candidate_id": "CAND-HIRED", "employee_id": "EMP-HIRED", "roster_ids": ["RST-HIRED"], "full_name": "Yeni Çalışan", "tckn": "12345098765", "email": None, "phone": None, "employment_start": "2026-08-20", "first_shift": {"date": "2026-08-20", "start": "09:00", "end": "18:00", "break_minutes": 60}}
        with (
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "upsert_people", return_value={"created": 1, "updated": 0, "total": 1, "roster_conflicts": []}) as upsert,
            patch.object(service, "_save_request") as save,
            patch.object(service.persistence, "append_audit"),
            patch("app.modules.workforce.service.create_shift", return_value={"id": "SHIFT-FIRST", "person_id": "EMP-HIRED"}) as create_shift,
        ):
            result = service.activate_hire(request["id"], payload, "hr@opex.local")
        self.assertEqual(result["status"], "FILLED")
        self.assertEqual(result["activation"]["workforce"], "ACTIVE")
        self.assertEqual(result["activation"]["first_shift_id"], "SHIFT-FIRST")
        self.assertEqual(upsert.call_args.args[0][0]["warehouse_id"], FULYA["id"])
        self.assertEqual(upsert.call_args.args[0][0]["position"], "Mağaza Görevlisi")
        save.assert_called_once()
        create_shift.assert_called_once()

    def test_temporary_plus_one_norm_reverts_after_september_with_review_flag(self):
        norm = {
            "norm": 12, "base_norm": 11, "temporary_adjustment": 1,
            "temporary_effective_from": "2026-07-01", "temporary_effective_until": "2026-09-30",
            "reversion_mode": "AUTOMATIC_REVIEW",
        }
        self.assertEqual(service._effective_norm(norm, "2026-09-30"), (12, "TEMPORARY_ACTIVE"))
        self.assertEqual(service._effective_norm(norm, "2026-10-01"), (11, "REVERTED_REVIEW_REQUIRED"))

    def test_open_position_count_decreases_after_partial_hire(self):
        requests = [{"id": "REC-PARTIAL", "warehouse_name": FULYA["name"], "position_code": "STORE_STAFF", "quantity": 3, "hires": [{"employee_id": "1"}], "status": "PARTIALLY_FILLED"}]
        with patch.object(service, "list_requests", return_value=requests):
            self.assertEqual(service._open_positions(FULYA["name"], "STORE_STAFF"), 2)

    def test_candidate_evidence_approval_chain_is_required_before_hire(self):
        request = {
            "id": "REC-CANDIDATE-1", "status": "APPROVED", "quantity": 1,
            "hires": [], "candidates": [], "revision": 1,
            "warehouse_id": FULYA["id"], "warehouse_name": FULYA["name"],
            "position_code": "STORE_STAFF", "position_label": "Mağaza Görevlisi",
            "history": [], "created_at": "2026-08-01T00:00:00+00:00",
        }
        with (
            TemporaryDirectory() as directory,
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "_save_request"),
            patch.object(service, "_EVIDENCE_DIR", Path(directory)),
        ):
            candidate = service.register_candidate(
                request["id"], {"full_name": "Aday Kişi", "source_ref": "ATS-42", "note": None}, "hr"
            )
            self.assertEqual(candidate["status"], "EVIDENCE_PENDING")
            with self.assertRaisesRegex(service.RecruitmentRuleError, "kanıt incelemesi"):
                service.decide_candidate(request["id"], candidate["id"], "APPROVED", "uygun", "hr")
            service.add_candidate_evidence(
                request["id"], candidate["id"], "cv.pdf", "application/pdf", b"%PDF-candidate", "hr"
            )
            approved = service.decide_candidate(request["id"], candidate["id"], "APPROVED", "uygun", "hr")
            self.assertEqual(approved["status"], "APPROVED")
            self.assertIn("retention_until", approved["evidence"][0])

    def test_retention_purge_redacts_candidate_pii_and_deletes_expired_evidence(self):
        with TemporaryDirectory() as directory:
            evidence_path = Path(directory) / "expired.pdf"
            evidence_path.write_bytes(b"expired")
            request = {
                "id": "REC-RETENTION", "status": "REJECTED", "warehouse_id": FULYA["id"],
                "revision": 1, "history": [], "evidence": None,
                "candidates": [{
                    "id": "C-OLD", "full_name": "Private Person", "source_ref": "ATS-PRIVATE",
                    "note": "private", "pii_retention_until": "2025-01-01T00:00:00+00:00",
                    "evidence": [{
                        "stored_name": evidence_path.name, "retention_until": "2025-01-01T00:00:00+00:00",
                    }],
                }],
            }
            with (
                patch.object(service, "list_requests", return_value=[request]),
                patch.object(service, "_save_request") as save,
                patch.object(service, "_EVIDENCE_DIR", Path(directory)),
            ):
                result = service.purge_expired_recruitment_data("dpo", datetime(2026, 1, 1, tzinfo=UTC))
        self.assertEqual(result["redacted_candidates"], 1)
        self.assertEqual(result["deleted_evidence"], 1)
        self.assertEqual(request["candidates"][0]["full_name"], "[REDACTED]")
        self.assertFalse(evidence_path.exists())
        save.assert_called_once()


class RecruitmentScopeApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.environment = {
            "DOCKOS_ENV": "production", "OPEX_ALLOW_LEGACY_HEADERS": "false",
            "OPEX_OIDC_ISSUER": "https://idp.example.test", "OPEX_OIDC_AUDIENCE": "opex",
        }
        self.claims = {
            "sub": "manager-1", "name": "Fulya Manager", "roles": ["warehouse_manager"],
            "permissions": [], "warehouse_scope": ["fulya"],
        }

    def test_manager_bootstrap_is_store_scoped_and_hides_admin_configuration(self):
        rows = [
            {
                "id": "REC-F", "warehouse_id": "fulya", "status": "PENDING_APPROVAL",
                "evidence": {"stored_name": "private.pdf", "sha256": "secret"},
                "candidates": [{"id": "C-1", "evidence": [{"stored_name": "cv.pdf", "sha256": "secret"}]}],
            },
            {"id": "REC-U", "warehouse_id": "uskudar", "status": "PENDING_APPROVAL"},
        ]
        with (
            patch.dict(os.environ, self.environment, clear=False),
            patch("app.security._decode_bearer", return_value=self.claims),
            patch.object(recruitment_router, "list_requests", return_value=rows),
            patch.object(recruitment_router, "list_norms", return_value=[]),
        ):
            response = self.client.get("/api/recruitment/bootstrap", headers={"Authorization": "Bearer signed"})
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([row["id"] for row in body["requests"]], ["REC-F"])
        self.assertNotIn("evidence", body["requests"][0])
        self.assertEqual(body["requests"][0]["candidates"][0]["evidence"], [])
        self.assertIsNone(body["settings"])
        self.assertEqual(body["email_outbox"], [])

    def test_manager_cannot_create_cross_store_vacancy_or_read_evidence(self):
        payload = {
            "warehouse_id": "uskudar", "position_code": "STORE_STAFF", "quantity": 1,
            "employment_type": "FULL_TIME", "reason_code": "NORM_GAP",
            "needed_by": "2027-01-01", "justification": "Cross-scope attempt",
        }
        with patch.dict(os.environ, self.environment, clear=False), patch("app.security._decode_bearer", return_value=self.claims):
            create_response = self.client.post(
                "/api/recruitment/requests", json=payload, headers={"Authorization": "Bearer signed"}
            )
            evidence_response = self.client.get(
                "/api/recruitment/requests/REC-F/evidence", headers={"Authorization": "Bearer signed"}
            )
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(evidence_response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
