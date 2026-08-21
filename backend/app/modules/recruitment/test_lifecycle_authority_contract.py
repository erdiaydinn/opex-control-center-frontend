from __future__ import annotations

from pathlib import Path
import unittest

from app.modules.recruitment import lifecycle_authority
from app.modules.recruitment.lifecycle_authority import RecruitmentLifecycleError


class RecruitmentLifecycleContractTests(unittest.TestCase):
    def test_offer_requires_two_independent_approvals(self):
        self.assertEqual(lifecycle_authority.REQUIRED_SCHEMA_VERSION, 47)
        self.assertEqual(lifecycle_authority._OFFER_APPROVAL_QUORUM, 2)
        source = Path(lifecycle_authority.__file__).read_text(encoding="utf-8")
        self.assertIn("Offer hazırlayan kişi kendi teklifini onaylayamaz", source)
        self.assertIn("UNIQUE", (Path(__file__).resolve().parents[3] / "migrations" / "031_recruitment_lifecycle_authority.sql").read_text(encoding="utf-8"))
        self.assertIn("approved_count >= int(required)", source)

    def test_candidate_communication_outbox_rejects_raw_pii(self):
        for payload in (
            {"email": "candidate@example.com"},
            {"meta": {"phone": "+905551234567"}},
            {"items": [{"tckn": "12345678901"}]},
            {"full-name": "Candidate Person"},
        ):
            with self.assertRaises(RecruitmentLifecycleError):
                lifecycle_authority._assert_pii_minimized(payload)
        lifecycle_authority._assert_pii_minimized({"offer_id": "opaque", "stage": "OFFER", "warehouse_code": "CI"})

    def test_offboarding_covers_cross_functional_owners(self):
        owners = {task[2] for task in lifecycle_authority._OFFBOARDING_TASKS}
        self.assertEqual(owners, {"HR", "IT", "ADMIN", "PAYROLL", "ACADEMY", "OPERATIONS"})
        source = Path(lifecycle_authority.__file__).read_text(encoding="utf-8")
        self.assertIn("Tüm required offboarding task tamamlanmadan case kapatılamaz", source)
        self.assertIn("Offboarding waiver gerekçesi zorunludur", source)

    def test_priority_router_shadows_legacy_offer_issue_paths(self):
        main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        lifecycle = 'app.include_router(recruitment_lifecycle_router, prefix="/api")'
        orchestration = 'app.include_router(recruitment_orchestration_router, prefix="/api")'
        self.assertLess(main_source.index(lifecycle), main_source.index(orchestration))
        router_source = (Path(__file__).resolve().parent / "lifecycle_router.py").read_text(encoding="utf-8")
        self.assertIn('@router.post("/requests/{request_id}/candidates/{candidate_id}/offers"', router_source)
        self.assertIn('@router.post("/offers/{offer_id}/decision-capabilities"', router_source)
        self.assertIn('"approveRecruitmentOffer"', router_source)
        self.assertIn('"deliverRecruitmentCommunication"', router_source)

    def test_v47_migration_is_rls_forced_and_events_append_only(self):
        migration = (Path(__file__).resolve().parents[3] / "migrations" / "031_recruitment_lifecycle_authority.sql").read_text(encoding="utf-8")
        for table in (
            "offer_approval_workflows", "offer_approval_events", "candidate_communication_outbox",
            "talent_pool_memberships", "offboarding_cases", "offboarding_tasks", "offboarding_events",
        ):
            self.assertIn(table, migration)
        self.assertIn("FORCE ROW LEVEL SECURITY", migration)
        self.assertIn("recruitment lifecycle event is append-only", migration)
        self.assertIn("VALUES (47, 'governed hiring lifecycle authority')", migration)


if __name__ == "__main__":
    unittest.main()
