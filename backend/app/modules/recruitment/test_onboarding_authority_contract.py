from __future__ import annotations

from pathlib import Path
import unittest

from pydantic import ValidationError

from app.modules.recruitment import onboarding_router


class OnboardingAuthorityContractTests(unittest.TestCase):
    def test_owner_roles_are_functionally_separated(self):
        self.assertEqual(onboarding_router._allowed_owner_roles("it_admin", ""), {"IT"})
        self.assertEqual(onboarding_router._allowed_owner_roles("trainer", ""), {"ACADEMY"})
        self.assertEqual(onboarding_router._allowed_owner_roles("warehouse_manager", ""), {"OPERATIONS"})
        self.assertEqual(onboarding_router._allowed_owner_roles("viewer", ""), set())

    def test_specific_permission_can_grant_one_owner_queue(self):
        allowed = onboarding_router._allowed_owner_roles("viewer", "completeRecruitmentOnboarding:ADMIN")
        self.assertEqual(allowed, {"ADMIN"})

    def test_owner_update_cannot_waive_required_task(self):
        with self.assertRaises(ValidationError):
            onboarding_router.OwnerTaskUpdate(status="WAIVED", note="self waive")
        valid = onboarding_router.OwnerTaskUpdate(status="BLOCKED", note="dependency missing")
        self.assertEqual(valid.status, "BLOCKED")

    def test_dedicated_waiver_route_requires_central_permission(self):
        source = Path(onboarding_router.__file__).read_text(encoding="utf-8")
        self.assertIn('"manageRecruitmentOnboarding"', source)
        self.assertIn('status="WAIVED"', source)
        self.assertIn("ordinary task owners cannot self-waive", source)

    def test_safe_onboarding_router_precedes_legacy_orchestration_route(self):
        main = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        safe = 'app.include_router(recruitment_onboarding_router, prefix="/api")'
        legacy = 'app.include_router(recruitment_orchestration_router, prefix="/api")'
        self.assertIn(safe, main)
        self.assertLess(main.index(safe), main.index(legacy))


if __name__ == "__main__":
    unittest.main()
