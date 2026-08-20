from __future__ import annotations

from contextlib import contextmanager
from uuid import uuid4
import unittest
from unittest.mock import patch

from app.modules.recruitment import evidence_release_authority as authority
from app.modules.recruitment.evidence_release_authority import EvidenceReleaseAuthorityError


class FakeCursor:
    def __init__(self, released: bool):
        self.released = released
        self.executed = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql, params=None):
        self.executed.append((" ".join(sql.split()), params))
        self._row = (self.released,)

    def fetchone(self):
        return self._row


class FakeDatabase:
    def __init__(self, released: bool):
        self.cursor_instance = FakeCursor(released)
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def rollback(self):
        self.rolled_back = True


class EvidenceReleaseAuthorityTests(unittest.TestCase):
    def evidence(self):
        digest = "a" * 64
        return {
            "id": str(uuid4()),
            "sha256": digest,
            "storage_backend": "S3_KMS_ENVELOPE",
            "content_safety_state": "MALWARE_CLEARED",
            "content_safety_truth_boundary": "CRYPTOGRAPHIC_SCANNER_RECEIPT",
            "content_safety_receipt": {
                "signature_verified": True,
                "result": "CLEAN",
                "evidence_sha256": digest,
            },
        }

    def patches(self, database):
        @contextmanager
        def connection():
            yield database

        return (
            patch.object(authority.persistence, "ENABLED", True),
            patch.object(authority.persistence, "schema_version", return_value=42),
            patch.object(authority.persistence, "tenant_id", return_value="eay-ci"),
            patch.object(authority.persistence, "_set_tenant"),
            patch.object(authority.persistence, "connection", connection),
        )

    def test_candidate_release_requires_database_authority_not_aggregate_alone(self):
        database = FakeDatabase(False)
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with self.assertRaisesRegex(EvidenceReleaseAuthorityError, "append-only scanner authority"):
                authority.require_candidate_evidence_released("REQ-1", "CAND-1", self.evidence())
        sql, params = database.cursor_instance.executed[0]
        self.assertIn("candidate_evidence_release_authorized", sql)
        self.assertEqual(params[0:3], ("eay-ci", "REQ-1", "CAND-1"))

    def test_request_release_accepts_only_database_confirmed_clean_binding(self):
        database = FakeDatabase(True)
        evidence = self.evidence()
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            authority.require_request_evidence_released("REQ-1", evidence)
        self.assertTrue(database.rolled_back)
        sql, params = database.cursor_instance.executed[0]
        self.assertIn("request_evidence_release_authorized", sql)
        self.assertEqual(params[0:2], ("eay-ci", "REQ-1"))

    def test_forged_clean_aggregate_without_crypto_truth_boundary_fails_before_database(self):
        database = FakeDatabase(True)
        evidence = self.evidence()
        evidence["content_safety_truth_boundary"] = "STATIC_FORMAT_GATE_ONLY"
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with self.assertRaisesRegex(EvidenceReleaseAuthorityError, "truth boundary"):
                authority.require_request_evidence_released("REQ-1", evidence)
        self.assertEqual(database.cursor_instance.executed, [])

    def test_receipt_sha_mismatch_fails_before_database(self):
        database = FakeDatabase(True)
        evidence = self.evidence()
        evidence["content_safety_receipt"]["evidence_sha256"] = "b" * 64
        patches = self.patches(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4]:
            with self.assertRaisesRegex(EvidenceReleaseAuthorityError, "receipt aggregate binding"):
                authority.require_candidate_evidence_released("REQ-1", "CAND-1", evidence)
        self.assertEqual(database.cursor_instance.executed, [])

    def test_v41_is_not_enough_for_release(self):
        with patch.object(authority.persistence, "ENABLED", True), patch.object(
            authority.persistence, "schema_version", return_value=41
        ):
            with self.assertRaisesRegex(EvidenceReleaseAuthorityError, "V42"):
                authority.require_request_evidence_released("REQ-1", self.evidence())


if __name__ == "__main__":
    unittest.main()
