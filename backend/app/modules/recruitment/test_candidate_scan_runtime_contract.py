from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
import inspect
from uuid import uuid4
import unittest
from unittest.mock import patch

from app.modules.recruitment import candidate_scan_authority, service
from app.modules.recruitment.candidate_scan_authority import CandidateScanAuthorityError


class FakeCursor:
    def __init__(self, *, candidate_id: str, evidence_id: str, digest: bytes):
        self.candidate_id = candidate_id
        self.evidence_id = evidence_id
        self.digest = digest
        self.executed: list[str] = []
        self._row = None
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        self.executed.append(normalized)
        if "get_candidate_evidence_scan_binding" in normalized:
            self._row = ("REQ-DB", self.candidate_id, self.digest)
        elif "record_candidate_evidence_scan_receipt" in normalized:
            self._row = (uuid4(),)
        else:
            self._row = None

    def fetchone(self):
        value = self._row
        self._row = None
        return value


class FakeDatabase:
    def __init__(self, cursor: FakeCursor):
        self.cursor_instance = cursor
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        pass


class CandidateScanRuntimeContractTests(unittest.TestCase):
    def test_receipt_claim_aggregate_and_audit_share_one_transaction(self) -> None:
        source = inspect.getsource(candidate_scan_authority.record_verified_scan)
        claim_at = source.index("record_candidate_evidence_scan_receipt")
        aggregate_at = source.index("SELECT payload,revision")
        audit_at = source.index("_build_audit_record")
        commit_at = source.index("database.commit()")
        self.assertLess(claim_at, aggregate_at)
        self.assertLess(aggregate_at, audit_at)
        self.assertLess(audit_at, commit_at)

    def test_exact_evidence_binding_is_database_derived(self) -> None:
        evidence_id = str(uuid4())
        digest = sha256(b"exact-db-evidence").digest()
        cursor = FakeCursor(candidate_id="CAND-DB", evidence_id=evidence_id, digest=digest)
        database = FakeDatabase(cursor)

        @contextmanager
        def connection():
            yield database

        now = datetime.now(UTC)
        payload = {
            "tenant_id": "eay-ci",
            "candidate_id": "CAND-ATTACKER-CONTROLLED",
            "evidence_id": evidence_id,
            "evidence_sha256": digest.hex(),
            "provider": "ci-scanner",
            "engine": "engine-1",
            "key_id": "2026-08",
            "receipt_id": "receipt-1",
            "nonce": "nonce-1",
            "result": "CLEAN",
            "issued_at": now.isoformat(),
        }
        signature_bytes = b"s" * 32
        signature = base64.urlsafe_b64encode(signature_bytes).decode().rstrip("=")

        with patch.object(candidate_scan_authority.persistence, "ENABLED", True), patch.object(
            candidate_scan_authority.persistence, "schema_version", return_value=42
        ), patch.object(
            candidate_scan_authority.persistence, "tenant_id", return_value="eay-ci"
        ), patch.object(
            candidate_scan_authority.persistence, "_set_tenant"
        ), patch.object(
            candidate_scan_authority.persistence, "connection", connection
        ), patch.object(
            candidate_scan_authority,
            "_select_verifier",
            return_value=lambda _kid, _message, sig: sig == signature_bytes,
        ):
            with self.assertRaisesRegex(CandidateScanAuthorityError, "Scanner receipt reddedildi"):
                candidate_scan_authority.record_verified_scan(
                    payload,
                    signature,
                    verifier=lambda *_args: True,
                    actor="scanner",
                    now=now,
                )

        self.assertTrue(database.rolled_back)
        self.assertTrue(any("get_candidate_evidence_scan_binding" in sql for sql in cursor.executed))
        self.assertFalse(any("record_candidate_evidence_scan_receipt" in sql for sql in cursor.executed))

    def test_production_scanner_requires_current_security_schema(self) -> None:
        with patch.dict("os.environ", {"DOCKOS_ENV": "production"}, clear=False), patch.object(
            candidate_scan_authority.persistence, "ENABLED", True
        ), patch.object(
            candidate_scan_authority.persistence, "schema_version", return_value=41
        ):
            with self.assertRaisesRegex(CandidateScanAuthorityError, "PostgreSQL scanner receipt"):
                candidate_scan_authority.record_verified_scan(
                    {}, "signature", verifier=lambda *_args: True, actor="scanner"
                )

    def test_production_rejects_legacy_boolean_scanner_authority(self) -> None:
        source = inspect.getsource(service.record_candidate_content_safety_scan)
        self.assertIn('os.getenv("DOCKOS_ENV", "development")', source)
        self.assertIn("kriptografik receipt otoritesi", source)


if __name__ == "__main__":
    unittest.main()
