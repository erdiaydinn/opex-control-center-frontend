from __future__ import annotations

import base64
from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime
from hashlib import sha256
from uuid import uuid4
import unittest
from unittest.mock import patch

from app.modules.recruitment import request_evidence_scan_authority as authority
from app.modules.recruitment.request_evidence_scan_authority import RequestEvidenceScanAuthorityError


class FakeCursor:
    def __init__(self, record: dict, *, receipt_claim_ok: bool = True):
        self.record = deepcopy(record)
        self.receipt_claim_ok = receipt_claim_ok
        self.executed: list[str] = []
        self.rowcount = 0
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.executed.append(normalized)
        if normalized.startswith("SELECT payload,revision FROM recruitment_requests"):
            self._row = (deepcopy(self.record), int(self.record.get("revision", 1)))
            return
        if "record_request_evidence_scan_receipt" in normalized:
            if not self.receipt_claim_ok:
                raise RuntimeError("duplicate receipt")
            self._row = (uuid4(),)
            return
        if normalized.startswith("UPDATE recruitment_requests"):
            self.rowcount = 1
            self._row = None
            return
        self._row = None

    def fetchone(self):
        value = self._row
        self._row = None
        return value


class FakeDatabase:
    def __init__(self, record: dict, *, receipt_claim_ok: bool = True):
        self.cursor_instance = FakeCursor(record, receipt_claim_ok=receipt_claim_ok)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class RequestEvidenceScanAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.evidence_id = str(uuid4())
        self.digest = sha256(b"evidence").hexdigest()
        self.record = {
            "id": "REQ-1",
            "revision": 9,
            "evidence": {
                "id": self.evidence_id,
                "sha256": self.digest,
                "storage_backend": "S3_KMS_ENVELOPE",
                "content_safety_state": "STATIC_FORMAT_ACCEPTED_AV_PENDING",
            },
            "history": [],
        }
        self.now = datetime.now(UTC)
        self.payload = {
            "tenant_id": "eay-ci",
            "candidate_id": "REQ-1",
            "evidence_id": self.evidence_id,
            "evidence_sha256": self.digest,
            "provider": "ci-scanner",
            "engine": "clamav-1",
            "key_id": "2026-08",
            "receipt_id": "receipt-1",
            "nonce": "nonce-1",
            "result": "CLEAN",
            "issued_at": self.now.isoformat(),
        }
        self.signature_bytes = b"s" * 32
        self.signature = base64.urlsafe_b64encode(self.signature_bytes).decode().rstrip("=")

    def patches(self, database: FakeDatabase):
        @contextmanager
        def connection():
            yield database

        return (
            patch.object(authority.persistence, "ENABLED", True),
            patch.object(authority.persistence, "schema_version", return_value=42),
            patch.object(authority.persistence, "tenant_id", return_value="eay-ci"),
            patch.object(authority.persistence, "_set_tenant"),
            patch.object(authority.persistence, "_build_audit_record"),
            patch.object(authority.persistence, "connection", connection),
            patch.object(authority, "_verifier", return_value=lambda _kid, _message, sig: sig == self.signature_bytes),
        )

    def test_clean_receipt_is_claimed_before_aggregate_release_and_committed(self):
        database = FakeDatabase(self.record)
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            evidence = authority.record_verified_request_scan(
                "REQ-1", self.payload, self.signature, now=self.now
            )
        self.assertTrue(database.committed)
        self.assertEqual(evidence["content_safety_state"], "MALWARE_CLEARED")
        self.assertEqual(evidence["content_safety_truth_boundary"], "CRYPTOGRAPHIC_SCANNER_RECEIPT")
        receipt_at = next(i for i, sql in enumerate(database.cursor_instance.executed) if "record_request_evidence_scan_receipt" in sql)
        update_at = next(i for i, sql in enumerate(database.cursor_instance.executed) if sql.startswith("UPDATE recruitment_requests"))
        self.assertLess(receipt_at, update_at)

    def test_wrong_sha_fails_before_receipt_claim(self):
        database = FakeDatabase(self.record)
        payload = {**self.payload, "evidence_sha256": "0" * 64}
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(RequestEvidenceScanAuthorityError, "Scanner receipt reddedildi"):
                authority.record_verified_request_scan("REQ-1", payload, self.signature, now=self.now)
        self.assertTrue(database.rolled_back)
        self.assertFalse(any("record_request_evidence_scan_receipt" in sql for sql in database.cursor_instance.executed))

    def test_replayed_receipt_cannot_release_aggregate(self):
        database = FakeDatabase(self.record, receipt_claim_ok=False)
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(RequestEvidenceScanAuthorityError, "Scanner receipt reddedildi"):
                authority.record_verified_request_scan("REQ-1", self.payload, self.signature, now=self.now)
        self.assertTrue(database.rolled_back)
        self.assertFalse(any(sql.startswith("UPDATE recruitment_requests") for sql in database.cursor_instance.executed))

    def test_malware_detected_is_terminal_for_future_receipts(self):
        record = deepcopy(self.record)
        record["evidence"]["content_safety_state"] = "MALWARE_DETECTED"
        database = FakeDatabase(record)
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6]:
            with self.assertRaisesRegex(RequestEvidenceScanAuthorityError, "Scanner receipt reddedildi"):
                authority.record_verified_request_scan("REQ-1", self.payload, self.signature, now=self.now)
        self.assertFalse(any("record_request_evidence_scan_receipt" in sql for sql in database.cursor_instance.executed))


if __name__ == "__main__":
    unittest.main()
