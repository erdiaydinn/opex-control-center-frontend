from pathlib import Path
import unittest

from . import persistence


class WorkforcePostgresBootstrapContractTests(unittest.TestCase):
    def test_ci_production_bootstrap_covers_every_required_migration(self) -> None:
        script = (
            Path(__file__).resolve().parents[3]
            / "scripts"
            / "setup_workforce_postgres_ci.py"
        ).read_text(encoding="utf-8")
        for migration_path in persistence._MIGRATION_PATHS:
            self.assertIn(
                migration_path.name,
                script,
                f"production-shaped CI bootstrap omits {migration_path.name}",
            )

    def test_required_schema_version_matches_latest_migration(self) -> None:
        self.assertEqual(persistence.SCHEMA_VERSION, 39)
        self.assertEqual(persistence._MIGRATION_PATHS[-1].name,
                         "023_recruitment_candidate_upload_authority.sql")


if __name__ == "__main__":
    unittest.main()
