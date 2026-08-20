from __future__ import annotations

import unittest

from app.modules.workforce import persistence


class ProductionSchemaRegistryTests(unittest.TestCase):
    def test_workforce_startup_requires_v41(self):
        self.assertEqual(persistence.SCHEMA_VERSION, 41)

    def test_v41_authority_migrations_are_canonical(self):
        names = [path.name for path in persistence._MIGRATION_PATHS]
        expected = [
            "023_recruitment_candidate_upload_authority.sql",
            "024_recruitment_production_authority.sql",
            "025_recruitment_request_evidence_scan_authority.sql",
        ]
        for name in expected:
            self.assertIn(name, names)
        self.assertLess(names.index(expected[0]), names.index(expected[1]))
        self.assertLess(names.index(expected[1]), names.index(expected[2]))


if __name__ == "__main__":
    unittest.main()
