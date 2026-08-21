from __future__ import annotations

from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.modules.recruitment import lifecycle_governance_router as router
from app.modules.recruitment.lifecycle_router import OffboardingTaskInput


class LifecycleGovernanceContractTests(unittest.TestCase):
    def test_governance_router_precedes_generic_lifecycle_router(self):
        main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        governance = 'app.include_router(recruitment_lifecycle_governance_router, prefix="/api")'
        lifecycle = 'app.include_router(recruitment_lifecycle_router, prefix="/api")'
        orchestration = 'app.include_router(recruitment_orchestration_router, prefix="/api")'
        self.assertLess(main_source.index(governance), main_source.index(lifecycle))
        self.assertLess(main_source.index(lifecycle), main_source.index(orchestration))

    def test_general_manager_cannot_waive_required_task(self):
        with patch.object(router, "offboarding_task_authority", return_value={"owner_role": "IT"}), patch.object(router, "update_offboarding_task") as update:
            with self.assertRaises(HTTPException) as raised:
                router.governed_offboarding_task_update(
                    "11111111-1111-1111-1111-111111111111",
                    OffboardingTaskInput(status="WAIVED", note="waiver"),
                    Mock(),
                    x_opex_role="viewer",
                    x_opex_permissions="manageRecruitmentOffboarding",
                )
        self.assertEqual(raised.exception.status_code, 403)
        update.assert_not_called()

    def test_owner_specific_completion_permission_reaches_authority(self):
        request = Mock()
        with patch.object(router, "offboarding_task_authority", return_value={"owner_role": "IT"}), patch.object(router, "_actor", return_value="it@example.test"), patch.object(router, "update_offboarding_task", return_value={"status": "COMPLETED"}) as update:
            result = router.governed_offboarding_task_update(
                "11111111-1111-1111-1111-111111111111",
                OffboardingTaskInput(status="COMPLETED", note="access revoked"),
                request,
                x_opex_role="viewer",
                x_opex_permissions="completeRecruitmentOffboarding:IT",
            )
        self.assertEqual(result["status"], "COMPLETED")
        update.assert_called_once()

    def test_case_close_requires_distinct_permission(self):
        request = Mock()
        with patch.object(router, "close_offboarding_case") as close:
            with self.assertRaises(HTTPException) as raised:
                router.governed_offboarding_close(
                    "11111111-1111-1111-1111-111111111111",
                    request,
                    x_opex_role="viewer",
                    x_opex_permissions="manageRecruitmentOffboarding",
                )
        self.assertEqual(raised.exception.status_code, 403)
        close.assert_not_called()

    def test_global_communication_projection_exposes_no_payload_or_recipient(self):
        projection = (Path(__file__).resolve().parent / "lifecycle_projection.py").read_text(encoding="utf-8")
        function = projection[projection.index("def list_communication_outbox"):projection.index("def offboarding_task_authority")]
        self.assertNotIn('"payload":', function)
        self.assertNotIn('"email":', function)
        self.assertNotIn('"phone":', function)
        self.assertIn('"payload_exposed": False', function)
        self.assertIn('"recipient_exposed": False', function)


if __name__ == "__main__":
    unittest.main()
