from __future__ import annotations

from contextlib import contextmanager
import os
import unittest
from unittest.mock import patch

from app.modules.recruitment import scanner_database_authority as authority
from app.modules.recruitment.scanner_database_authority import ScannerDatabaseAuthorityError


class FakeCursor:
    def __init__(self, identity=("eay_candidate_scanner_runtime", "eay_candidate_scanner_runtime", "eay-ci"), privileges=None):
        self.identity = identity
        self.privileges = privileges or (True, True, True, True, True, False, False)
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, _params=None):
        normalized = " ".join(sql.split())
        if normalized.startswith("SELECT session_user"):
            self._row = self.identity
        elif "has_function_privilege" in normalized:
            self._row = self.privileges
        else:
            self._row = None

    def fetchone(self):
        return self._row


class FakeDatabase:
    def __init__(self, cursor):
        self._cursor = cursor
        self.rolled_back = False

    def cursor(self):
        return self._cursor

    def rollback(self):
        self.rolled_back = True


class ScannerDatabaseAuthorityTests(unittest.TestCase):
    def context(self, cursor):
        database = FakeDatabase(cursor)

        @contextmanager
        def connection(_url=None):
            yield database

        return database, connection

    def test_production_requires_dedicated_dsn_before_connect(self):
        with patch.dict(os.environ, {"DOCKOS_ENV": "production", "RECRUITMENT_SCANNER_DATABASE_URL": ""}, clear=False), patch.object(
            authority.persistence, "ENABLED", True
        ), patch.object(authority.persistence, "schema_version", return_value=43):
            with self.assertRaisesRegex(ScannerDatabaseAuthorityError, "dedicated PostgreSQL DSN"):
                with authority.transaction():
                    pass

    def test_wrong_database_role_is_rejected(self):
        cursor = FakeCursor(identity=("workforce_runtime", "workforce_runtime", "eay-ci"))
        _, connection = self.context(cursor)
        with patch.dict(
            os.environ,
            {"DOCKOS_ENV": "production", "RECRUITMENT_SCANNER_DATABASE_URL": "postgresql://scanner"},
            clear=False,
        ), patch.object(authority.persistence, "ENABLED", True), patch.object(
            authority.persistence, "schema_version", return_value=43
        ), patch.object(authority.persistence, "tenant_id", return_value="eay-ci"), patch.object(
            authority.persistence, "connection", connection
        ), patch.object(authority.persistence, "_set_tenant"):
            with self.assertRaisesRegex(ScannerDatabaseAuthorityError, "dedicated scanner rolü"):
                with authority.transaction():
                    pass

    def test_live_preflight_proves_least_privilege_shape(self):
        cursor = FakeCursor()
        database, connection = self.context(cursor)
        with patch.dict(
            os.environ,
            {"DOCKOS_ENV": "production", "RECRUITMENT_SCANNER_DATABASE_URL": "postgresql://scanner"},
            clear=False,
        ), patch.object(authority.persistence, "ENABLED", True), patch.object(
            authority.persistence, "schema_version", return_value=43
        ), patch.object(authority.persistence, "tenant_id", return_value="eay-ci"), patch.object(
            authority.persistence, "connection", connection
        ), patch.object(authority.persistence, "_set_tenant"):
            result = authority.live_preflight()
        self.assertEqual(result["session_user"], "eay_candidate_scanner_runtime")
        self.assertEqual(result["tenant_id"], "eay-ci")
        self.assertTrue(result["dedicated_dsn"])
        self.assertFalse(result["hr_settings_write"])
        self.assertFalse(result["hr_norms_write"])
        self.assertTrue(database.rolled_back)

    def test_overprivileged_scanner_role_fails_closed(self):
        cursor = FakeCursor(privileges=(True, True, True, True, True, True, False))
        _, connection = self.context(cursor)
        with patch.dict(
            os.environ,
            {"DOCKOS_ENV": "production", "RECRUITMENT_SCANNER_DATABASE_URL": "postgresql://scanner"},
            clear=False,
        ), patch.object(authority.persistence, "ENABLED", True), patch.object(
            authority.persistence, "schema_version", return_value=43
        ), patch.object(authority.persistence, "tenant_id", return_value="eay-ci"), patch.object(
            authority.persistence, "connection", connection
        ), patch.object(authority.persistence, "_set_tenant"):
            with self.assertRaisesRegex(ScannerDatabaseAuthorityError, "least-privilege"):
                authority.live_preflight()


if __name__ == "__main__":
    unittest.main()
