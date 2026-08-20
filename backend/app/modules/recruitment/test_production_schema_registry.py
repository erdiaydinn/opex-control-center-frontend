from __future__ import annotations

from pathlib import Path
import unittest

from app.modules.recruitment import production_startup_guard
from app.modules.workforce import persistence


class ProductionSchemaRegistryTests(unittest.TestCase):
    def test_workforce_base_registry_remains_v42(self):
        self.assertEqual(persistence.SCHEMA_VERSION, 42)

    def test_v42_base_authority_migrations_are_canonical(self):
        names = [path.name for path in persistence._MIGRATION_PATHS]
        expected = [
            "023_recruitment_candidate_upload_authority.sql",
            "024_recruitment_production_authority.sql",
            "025_recruitment_request_evidence_scan_authority.sql",
            "026_recruitment_evidence_release_authority.sql",
        ]
        for name in expected:
            self.assertIn(name, names)
        for left, right in zip(expected, expected[1:]):
            self.assertLess(names.index(left), names.index(right))

    def test_hiring_production_requires_v44_with_v43_isolation_and_v44_orchestration(self):
        self.assertEqual(production_startup_guard.REQUIRED_RECRUITMENT_SCHEMA_VERSION, 44)
        migration_dir = Path(__file__).resolve().parents[3] / "migrations"
        v43 = migration_dir / "027_recruitment_scanner_role_isolation.sql"
        v44 = migration_dir / "028_recruitment_orchestration.sql"
        self.assertTrue(v43.is_file())
        self.assertTrue(v44.is_file())
        v43_source = v43.read_text(encoding="utf-8")
        v44_source = v44.read_text(encoding="utf-8")
        self.assertIn("VALUES (43, 'dedicated recruitment scanner database role')", v43_source)
        self.assertIn("REVOKE EXECUTE", v43_source)
        self.assertIn("eay_candidate_scanner_runtime", v43_source)
        self.assertIn("VALUES (44, 'governed recruitment orchestration')", v44_source)
        self.assertIn("pipeline_templates", v44_source)
        self.assertIn("interview_scorecards", v44_source)
        self.assertIn("offer_decision_capabilities", v44_source)
        self.assertIn("onboarding_tasks", v44_source)

    def test_main_invokes_hiring_guard_and_priority_orchestration(self):
        main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        workforce_at = main_source.index("initialize_workforce()")
        guard_at = main_source.index("assert_recruitment_production_ready()")
        recruitment_at = main_source.index("initialize_recruitment()")
        orchestration_at = main_source.index('app.include_router(recruitment_orchestration_router, prefix="/api")')
        legacy_at = main_source.index('app.include_router(recruitment_router, prefix="/api")')
        self.assertLess(workforce_at, guard_at)
        self.assertLess(guard_at, recruitment_at)
        self.assertLess(orchestration_at, legacy_at)


if __name__ == "__main__":
    unittest.main()
