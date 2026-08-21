from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from app.modules.recruitment import recruitment_evidence_runtime as runtime
from app.modules.recruitment.recruitment_evidence_runtime import RecruitmentEvidenceRuntimeError


class FakeCursor:
    def __init__(self, record: dict):
        self.record = deepcopy(record)
        self.rowcount = 0
        self._row = None
        self.executed: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params=None):
        normalized = " ".join(sql.split())
        self.executed.append(normalized)
        if normalized.startswith("SELECT payload,revision FROM recruitment_requests"):
            self._row = (deepcopy(self.record), int(self.record.get("revision", 1)))
        elif normalized.startswith("UPDATE recruitment_requests"):
            self.rowcount = 1
            self._row = None
        else:
            self._row = None

    def fetchone(self):
        value = self._row
        self._row = None
        return value


class FakeDatabase:
    def __init__(self, record: dict):
        self.cursor_instance = FakeCursor(record)
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


class FakeStore:
    bucket = "eay-evidence"
    kms_key_id = "arn:kms:evidence"

    def __init__(self, content: bytes):
        self.content = content
        self.put_calls = []
        self.get_calls = []
        self.delete_calls = []

    def put(self, **kwargs):
        self.put_calls.append(kwargs)
        return {
            "storage_backend": "S3_KMS_ENVELOPE",
            "storage_bucket": self.bucket,
            "object_key": kwargs["object_key"],
            "encryption_scheme": "AES-256-GCM+AWS-KMS-DATA-KEY",
            "kms_key_id": self.kms_key_id,
            "envelope_version": 1,
        }

    def get(self, **kwargs):
        self.get_calls.append(kwargs)
        return self.content

    def delete_after_retention(self, **kwargs):
        self.delete_calls.append(kwargs)


class RecruitmentEvidenceRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.content = b"%PDF-1.7\nresignation-evidence"
        self.digest = sha256(self.content).hexdigest()
        self.record = {
            "id": "REQ-1",
            "status": "EVIDENCE_REQUIRED",
            "evidence_required": True,
            "evidence": None,
            "revision": 7,
            "history": [],
        }

    def production_persistence(self, database: FakeDatabase):
        @contextmanager
        def connection():
            yield database

        return (
            patch.object(runtime.persistence, "ENABLED", True),
            patch.object(runtime.persistence, "schema_version", return_value=40),
            patch.object(runtime.persistence, "tenant_id", return_value="eay-ci"),
            patch.object(runtime.persistence, "_set_tenant"),
            patch.object(runtime.persistence, "_build_audit_record"),
            patch.object(runtime.persistence, "connection", connection),
        )

    def test_secure_upload_locks_request_writes_encrypted_object_and_commits_metadata(self):
        database = FakeDatabase(self.record)
        store = FakeStore(self.content)
        patches = self.production_persistence(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
            runtime, "_store_for", return_value=store
        ):
            result = runtime.secure_request_evidence_upload(
                "REQ-1",
                filename="resignation.pdf",
                content_type="application/pdf",
                content=self.content,
                actor="manager-1",
            )
        self.assertTrue(database.committed)
        self.assertEqual(result["status"], "PENDING_APPROVAL")
        self.assertEqual(result["evidence"]["sha256"], self.digest)
        self.assertEqual(result["evidence"]["storage_backend"], "S3_KMS_ENVELOPE")
        self.assertEqual(
            result["evidence"]["content_safety_truth_boundary"],
            "STATIC_FORMAT_GATE_ONLY_NOT_MALWARE_CLEARED",
        )
        self.assertEqual(len(store.put_calls), 1)
        self.assertTrue(store.put_calls[0]["object_key"].startswith("quarantine/eay-ci/request-"))
        self.assertIn(
            "FOR UPDATE",
            next(sql for sql in database.cursor_instance.executed if sql.startswith("SELECT payload,revision")),
        )

    def test_production_replacement_is_immutable(self):
        record = {**self.record, "evidence": {"sha256": "a" * 64}}
        database = FakeDatabase(record)
        store = FakeStore(self.content)
        patches = self.production_persistence(database)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
            runtime, "_store_for", return_value=store
        ):
            with self.assertRaisesRegex(RecruitmentEvidenceRuntimeError, "değiştirilemez"):
                runtime.secure_request_evidence_upload(
                    "REQ-1",
                    filename="replacement.pdf",
                    content_type="application/pdf",
                    content=self.content,
                    actor="manager-1",
                )
        self.assertEqual(store.put_calls, [])
        self.assertFalse(database.committed)

    def test_encrypted_read_is_in_memory_and_exactly_bound(self):
        metadata = {
            "original_name": "resignation.pdf",
            "content_type": "application/pdf",
            "sha256": self.digest,
            "stored_name": "quarantine/eay-ci/request-abc",
            "storage_backend": "S3_KMS_ENVELOPE",
            "storage_bucket": "eay-evidence",
            "kms_key_id": "arn:kms:evidence",
            "encryption_scheme": "AES-256-GCM+AWS-KMS-DATA-KEY",
            "envelope_version": 1,
        }
        store = FakeStore(self.content)
        with patch(
            "app.modules.recruitment.service.list_requests",
            return_value=[{"id": "REQ-1", "evidence": metadata}],
        ), patch.object(runtime.persistence, "tenant_id", return_value="eay-ci"), patch.object(
            runtime, "_store_for", return_value=store
        ):
            content, returned = runtime.read_request_evidence("REQ-1")
        self.assertEqual(content, self.content)
        self.assertIs(returned, metadata)
        self.assertEqual(store.get_calls[0]["expected_sha256"], self.digest)

    def test_production_legacy_read_fails_closed(self):
        metadata = {
            "original_name": "legacy.pdf",
            "content_type": "application/pdf",
            "sha256": self.digest,
            "stored_name": "legacy.pdf",
            "storage_backend": "LEGACY_LOCAL",
        }
        with patch(
            "app.modules.recruitment.service.list_requests",
            return_value=[{"id": "REQ-1", "evidence": metadata}],
        ), patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False):
            with self.assertRaisesRegex(RecruitmentEvidenceRuntimeError, "plaintext yerel depodan"):
                runtime.read_request_evidence("REQ-1")

    def test_expired_encrypted_request_object_is_deleted_before_metadata_purge(self):
        expired = datetime.now(UTC) - timedelta(seconds=1)
        metadata = {
            "sha256": self.digest,
            "stored_name": "quarantine/eay-ci/request-abc",
            "storage_backend": "S3_KMS_ENVELOPE",
            "storage_bucket": "eay-evidence",
            "kms_key_id": "arn:kms:evidence",
            "encryption_scheme": "AES-256-GCM+AWS-KMS-DATA-KEY",
            "envelope_version": 1,
            "retention_until": expired.isoformat(),
        }
        store = FakeStore(self.content)
        with patch(
            "app.modules.recruitment.service.list_requests",
            return_value=[{"id": "REQ-1", "evidence": metadata}],
        ), patch.object(runtime.persistence, "tenant_id", return_value="eay-ci"), patch.object(
            runtime, "_store_for", return_value=store
        ):
            result = runtime.purge_expired_encrypted_request_evidence(now=datetime.now(UTC))
        self.assertEqual(result["encrypted_request_objects_deleted"], 1)
        self.assertEqual(len(store.delete_calls), 1)

    def test_priority_router_shadows_legacy_request_evidence_routes(self):
        from app.modules.recruitment.production_evidence_router import router as secure_router

        secure_routes = [
            route
            for route in secure_router.routes
            if getattr(route, "path", None) == "/recruitment/requests/{request_id}/evidence"
        ]
        self.assertTrue(any("POST" in getattr(route, "methods", set()) for route in secure_routes))
        self.assertTrue(any("GET" in getattr(route, "methods", set()) for route in secure_routes))

        main_source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        secure_include = main_source.index(
            'app.include_router(recruitment_production_evidence_router, prefix="/api")'
        )
        legacy_include = main_source.index(
            'app.include_router(recruitment_router, prefix="/api")'
        )
        self.assertLess(secure_include, legacy_include)


if __name__ == "__main__":
    unittest.main()
