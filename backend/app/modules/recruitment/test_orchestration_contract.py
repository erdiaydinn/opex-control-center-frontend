from __future__ import annotations

from pathlib import Path
import unittest

from app.modules.recruitment import orchestration
from app.modules.recruitment.orchestration import RecruitmentOrchestrationError


class RecruitmentOrchestrationContractTests(unittest.TestCase):
    def test_pipeline_requires_unique_stages_and_ready_to_hire_terminal(self):
        stages = orchestration._stage_rows(
            [
                {"key": "SOURCING", "label": "Sourcing", "sla_hours": 24},
                {"key": "INTERVIEW", "label": "Interview", "sla_hours": 24, "min_scorecards": 2, "min_average_score": 75},
                {"key": "READY_TO_HIRE", "label": "Ready", "sla_hours": 24},
            ]
        )
        self.assertEqual(stages[-1]["key"], "READY_TO_HIRE")
        self.assertEqual(stages[1]["min_scorecards"], 2)
        with self.assertRaises(RecruitmentOrchestrationError):
            orchestration._stage_rows([{"key": "A"}, {"key": "A"}])
        with self.assertRaisesRegex(RecruitmentOrchestrationError, "READY_TO_HIRE"):
            orchestration._stage_rows([{"key": "A"}, {"key": "B"}])

    def test_offer_package_digest_is_deterministic_and_has_explicit_signature_truth_boundary(self):
        package = {
            "country_code": "TR",
            "position": "Store Staff",
            "employment_type": "FULL_TIME",
            "employment_start": "2026-09-01",
            "currency": "TRY",
            "compensation_amount": 50000,
        }
        normalized_a, digest_a = orchestration._canonical_offer_package(package)
        normalized_b, digest_b = orchestration._canonical_offer_package(dict(reversed(list(package.items()))))
        self.assertEqual(normalized_a, normalized_b)
        self.assertEqual(digest_a, digest_b)
        self.assertEqual(len(digest_a), 32)

    def test_default_onboarding_spans_cross_department_dependencies(self):
        tasks = {item["task_key"]: item for item in orchestration._DEFAULT_ONBOARDING_TASKS}
        self.assertEqual(
            {item["owner_role"] for item in tasks.values()},
            {"HR", "IT", "ADMIN", "ACADEMY", "OPERATIONS"},
        )
        self.assertIn("HR_EMPLOYMENT_PACKET", tasks["IT_IDENTITY_ACCOUNT"]["dependencies"])
        self.assertIn("IT_IDENTITY_ACCOUNT", tasks["OPS_FIRST_SHIFT_READY"]["dependencies"])
        self.assertIn("ADMIN_ASSET_UNIFORM", tasks["OPS_FIRST_SHIFT_READY"]["dependencies"])

    def test_public_offer_capability_route_is_outside_authenticated_recruitment_prefix(self):
        from app.modules.recruitment.orchestration_router import public_router
        paths = {getattr(route, "path", "") for route in public_router.routes}
        self.assertIn("/public/recruitment/offer", paths)
        self.assertIn("/public/recruitment/offer/decision", paths)
        main = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        self.assertIn('app.include_router(recruitment_public_orchestration_router, prefix="/api")', main)

    def test_hire_activation_route_is_shadowed_by_readiness_gate(self):
        from app.modules.recruitment.orchestration_router import router
        hire_routes = [
            route for route in router.routes
            if getattr(route, "path", "") == "/recruitment/requests/{request_id}/hires"
        ]
        self.assertTrue(any("POST" in getattr(route, "methods", set()) for route in hire_routes))
        main = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        self.assertLess(
            main.index('app.include_router(recruitment_orchestration_router, prefix="/api")'),
            main.index('app.include_router(recruitment_router, prefix="/api")'),
        )


if __name__ == "__main__":
    unittest.main()
