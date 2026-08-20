from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import os
import unittest
from unittest.mock import Mock, patch

from app.modules.recruitment import candidate_evidence_runtime as runtime
from app.modules.recruitment.candidate_evidence_runtime import CandidateEvidenceRuntimeError


class CandidateEvidenceRuntimeTests(unittest.TestCase):
    def evidence(self, *, backend="S3_KMS_ENVELOPE", state="MALWARE_CLEARED", retention=None):
        content = b"%PDF-1.7\nencrypted-runtime"
        digest = sha256(content).hexdigest()
        evidence = {
            "id": "evidence-id",
            "sha256": digest,
            "stored_name": "quarantine/eay-ci/11111111-1111-1111-1111-111111111111",
            "content_type": "application/pdf",
            "original_name": "residence.pdf",
            "document_type": "RESIDENCE",
            "content_safety_state": state,
            "storage_backend": backend,
            "storage_bucket": "evidence-bucket" if backend == "S3_KMS_ENVELOPE" else None,
            "kms_key_id": "arn:kms:evidence" if backend == "S3_KMS_ENVELOPE" else None,
            "encryption_scheme": "AES-256-GCM+AWS-KMS-DATA-KEY" if backend == "S3_KMS_ENVELOPE" else None,
            "envelope_version": 1 if backend == "S3_KMS_ENVELOPE" else None,
            "retention_until": (retention or datetime.now(UTC) + timedelta(days=1)).isoformat(),
        }
        record = {
            "id": "REQ-1",
            "candidates": [{"id": "CAND-1", "evidence": [evidence]}],
        }
        return content, digest, evidence, record

    def test_encrypted_read_requires_malware_clearance(self):
        _, digest, _, record = self.evidence(state="STATIC_FORMAT_ACCEPTED_AV_PENDING")
        with patch.object(runtime, "_records", return_value=[record]):
            with self.assertRaises(CandidateEvidenceRuntimeError):
                runtime.read_candidate_evidence("REQ-1", "CAND-1", digest)

    def test_production_rejects_legacy_plaintext_read(self):
        _, digest, _, record = self.evidence(backend="LEGACY_LOCAL")
        with patch.object(runtime, "_records", return_value=[record]), patch.dict(
            os.environ, {"DOCKOS_ENV": "production"}, clear=False
        ):
            with self.assertRaises(CandidateEvidenceRuntimeError):
                runtime.read_candidate_evidence("REQ-1", "CAND-1", digest)

    def test_encrypted_read_rechecks_authority_metadata_and_exact_bytes(self):
        content, digest, _, record = self.evidence()
        store = Mock()
        store.bucket = "evidence-bucket"
        store.kms_key_id = "arn:kms:evidence"
        store.get.return_value = content
        with patch.object(runtime, "_records", return_value=[record]), patch.object(
            runtime.persistence, "ENABLED", True
        ), patch.object(runtime.persistence, "schema_version", return_value=40), patch.object(
            runtime.persistence, "tenant_id", return_value="eay-ci"
        ), patch.object(
            runtime.S3KmsEnvelopeEvidenceStore, "from_environment", return_value=store
        ):
            resolved, metadata = runtime.read_candidate_evidence("REQ-1", "CAND-1", digest)
        self.assertEqual(resolved, content)
        self.assertEqual(metadata["sha256"], digest)
        store.get.assert_called_once()

    def test_secure_hr_upload_reuses_one_time_authority(self):
        content, _, evidence, record = self.evidence()
        candidate = record["candidates"][0]
        with patch.object(runtime.persistence, "ENABLED", True), patch.object(
            runtime.persistence, "schema_version", return_value=40
        ), patch.object(
            runtime.candidate_upload_authority,
            "issue",
            return_value={"capability": "opaque-capability"},
        ) as issue, patch.object(
            runtime.candidate_upload_authority,
            "finalize",
            return_value=evidence,
        ) as finalize, patch.object(runtime, "_records", return_value=[record]):
            result = runtime.secure_hr_candidate_upload(
                "REQ-1",
                "CAND-1",
                filename="residence.pdf",
                content_type="application/pdf",
                content=content,
                document_type="RESIDENCE",
                actor="hr-user",
            )
        self.assertIs(result, candidate)
        issue.assert_called_once()
        finalize.assert_called_once()

    def test_expired_encrypted_purge_deletes_object_before_metadata_phase(self):
        expired = datetime.now(UTC) - timedelta(seconds=1)
        _, _, _, record = self.evidence(retention=expired)
        store = Mock()
        store.bucket = "evidence-bucket"
        store.kms_key_id = "arn:kms:evidence"
        with patch.object(runtime, "_records", return_value=[record]), patch.object(
            runtime.persistence, "ENABLED", True
        ), patch.object(runtime.persistence, "schema_version", return_value=40), patch.object(
            runtime.persistence, "tenant_id", return_value="eay-ci"
        ), patch.object(
            runtime.S3KmsEnvelopeEvidenceStore, "from_environment", return_value=store
        ):
            result = runtime.purge_expired_encrypted_candidate_evidence(
                now=datetime.now(UTC)
            )
        self.assertEqual(result["encrypted_objects_deleted"], 1)
        store.delete_after_retention.assert_called_once()


if __name__ == "__main__":
    unittest.main()
