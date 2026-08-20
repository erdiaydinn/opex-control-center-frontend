from __future__ import annotations

import unittest

from app.modules.workforce import persistence


class ProductionSchemaRegistryTests(unittest.TestCase):
    def test_workforce_startup_requires_v42(self):
        self.assertEqual(persistence.SCHEMA_VERSION, 42)

    def test_v42_authority_migrations_are_canonical(self):
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


if __name__ == "__main__":
    unittest.main()
