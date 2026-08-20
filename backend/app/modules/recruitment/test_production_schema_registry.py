from __future__ import annotations

import unittest

from app.modules.workforce import persistence


class ProductionSchemaRegistryTests(unittest.TestCase):
    def test_workforce_startup_requires_v40(self):
        self.assertEqual(persistence.SCHEMA_VERSION, 40)

    def test_v40_authority_migration_is_canonical(self):
        names = [path.name for path in persistence._MIGRATION_PATHS]
        self.assertIn("023_recruitment_candidate_upload_authority.sql", names)
        self.assertIn("024_recruitment_production_authority.sql", names)
        self.assertLess(
            names.index("023_recruitment_candidate_upload_authority.sql"),
            names.index("024_recruitment_production_authority.sql"),
        )


if __name__ == "__main__":
    unittest.main()
