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

    def test_hiring_production_requires_v47_extension_chain(self):
        self.assertEqual(production_startup_guard.REQUIRED_RECRUITMENT_SCHEMA_VERSION, 47)
        migration_dir = Path(__file__).resolve().parents[3] / "migrations"
        expected = {
            43: ("027_recruitment_scanner_role_isolation.sql", "dedicated recruitment scanner database role"),
            44: ("028_recruitment_orchestration.sql", "governed recruitment orchestration"),
            45: ("029_workforce_audit_chain_fencing.sql", "database audit hash chain fencing"),
            46: ("030_recruitment_interview_scheduling.sql", "shared candidate self-service interview scheduling authority"),
            47: ("031_recruitment_lifecycle_authority.sql", "governed hiring lifecycle authority"),
        }
        for version, (filename, label) in expected.items():
            path = migration_dir / filename
            self.assertTrue(path.is_file())
            source = path.read_text(encoding="utf-8")
            self.assertIn(f"VALUES ({version}, '{label}')", source)
        self.assertIn("REVOKE EXECUTE", (migration_dir / expected[43][0]).read_text(encoding="utf-8"))
        orchestration = (migration_dir / expected[44][0]).read_text(encoding="utf-8")
        for table in ("pipeline_templates", "interview_scorecards", "offer_decision_capabilities", "onboarding_tasks"):
            self.assertIn(table, orchestration)
        fencing = (migration_dir / expected[45][0]).read_text(encoding="utf-8")
        self.assertIn("pg_advisory_xact_lock", fencing)
        self.assertIn("audit hash chain stale", fencing)
        scheduling = (migration_dir / expected[46][0]).read_text(encoding="utf-8")
        for table in ("interview_schedules", "interview_slots", "interview_bookings", "interview_booking_capabilities", "interview_booking_events"):
            self.assertIn(table, scheduling)
        self.assertIn("FORCE ROW LEVEL SECURITY", scheduling)
        self.assertIn("interview booking event is append-only", scheduling)
        lifecycle = (migration_dir / expected[47][0]).read_text(encoding="utf-8")
        for table in (
            "offer_approval_workflows", "offer_approval_events", "candidate_communication_outbox",
            "talent_pool_memberships", "offboarding_cases", "offboarding_tasks", "offboarding_events",
        ):
            self.assertIn(table, lifecycle)
        self.assertIn("required_approvals", lifecycle)
        self.assertIn("FORCE ROW LEVEL SECURITY", lifecycle)
        self.assertIn("recruitment lifecycle event is append-only", lifecycle)

    def test_main_invokes_hiring_guard_and_priority_orchestration(self):
        main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        self.assertLess(main_source.index("initialize_workforce()"), main_source.index("assert_recruitment_production_ready()"))
        self.assertLess(main_source.index("assert_recruitment_production_ready()"), main_source.index("initialize_recruitment()"))
        lifecycle_mount = 'app.include_router(recruitment_lifecycle_router, prefix="/api")'
        orchestration_mount = 'app.include_router(recruitment_orchestration_router, prefix="/api")'
        legacy_mount = 'app.include_router(recruitment_router, prefix="/api")'
        self.assertLess(main_source.index(lifecycle_mount), main_source.index(orchestration_mount))
        self.assertLess(main_source.index(orchestration_mount), main_source.index(legacy_mount))
        self.assertIn('app.include_router(recruitment_public_orchestration_router, prefix="/api")', main_source)
        self.assertIn('app.include_router(recruitment_public_interview_router, prefix="/api")', main_source)
        self.assertIn('app.include_router(recruitment_interview_router, prefix="/api")', main_source)


if __name__ == "__main__":
    unittest.main()
