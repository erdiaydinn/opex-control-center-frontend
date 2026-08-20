from __future__ import annotations

import inspect
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from app.modules.recruitment import candidate_upload_authority
from app.modules.recruitment import router as recruitment_router


ROUTER_SOURCE = Path(__file__).with_name("router.py").read_text(encoding="utf-8")


class CandidateUploadRuntimeAuthorityTests(unittest.TestCase):
    def test_malformed_token_fails_before_database_lookup(self) -> None:
        with self.assertRaises(candidate_upload_authority.CandidateUploadAuthorityError):
            candidate_upload_authority._token_digest("short")

    def test_encrypted_finalize_prepares_then_writes_then_consumes_then_commits(self) -> None:
        source = inspect.getsource(candidate_upload_authority._finalize_encrypted)
        prepare_at = source.index("prepare_candidate_evidence_upload")
        object_put_at = source.index("store.put")
        finalize_at = source.index("finalize_candidate_evidence_upload_v2")
        aggregate_at = source.index("_persist_aggregate")
        commit_at = source.index("database.commit()")
        self.assertLess(prepare_at, object_put_at)
        self.assertLess(object_put_at, finalize_at)
        self.assertLess(finalize_at, aggregate_at)
        self.assertLess(aggregate_at, commit_at)
        self.assertNotIn("UPDATE recruitment.candidate_upload_capabilities", source)

    def test_issue_uses_security_definer_boundary(self) -> None:
        source = inspect.getsource(candidate_upload_authority.issue)
        self.assertIn("issue_candidate_upload_capability", source)
        self.assertNotIn("INSERT INTO recruitment.candidate_upload_capabilities", source)

    def test_router_validates_bytes_before_postgres_finalize(self) -> None:
        source = ROUTER_SOURCE[
            ROUTER_SOURCE.index("async def upload_candidate_evidence_with_capability"): 
        ]
        validate_at = source.index("_validate_candidate_document_bytes")
        finalize_at = source.index("candidate_upload_authority.finalize")
        legacy_consume_at = source.index("consume_candidate_upload_capability")
        self.assertLess(validate_at, finalize_at)
        self.assertLess(finalize_at, legacy_consume_at)

    def test_production_runtime_requires_postgres_v40_and_encrypted_storage(self) -> None:
        production_env = {
            "DOCKOS_ENV": "production",
            "RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE": "postgres",
            "RECRUITMENT_EVIDENCE_STORAGE_MODE": "s3-kms-envelope",
            "RECRUITMENT_EVIDENCE_BUCKET": "eay-recruitment-evidence",
            "RECRUITMENT_EVIDENCE_KMS_KEY_ID": "arn:aws:kms:eu-central-1:1:key/test",
        }
        with patch.dict(os.environ, production_env, clear=False), patch.object(
            recruitment_router.persistence, "ENABLED", True
        ), patch.object(recruitment_router.persistence, "schema_version", return_value=40):
            readiness = recruitment_router._candidate_authority_readiness()
        self.assertTrue(readiness["postgres_authority_ready"])
        self.assertTrue(readiness["encrypted_storage_ready"])
        self.assertTrue(readiness["core_ready"])
        self.assertEqual(readiness["required_schema"], 40)

        with patch.dict(os.environ, production_env, clear=False), patch.object(
            recruitment_router.persistence, "ENABLED", True
        ), patch.object(recruitment_router.persistence, "schema_version", return_value=39):
            stale = recruitment_router._candidate_authority_readiness()
        self.assertFalse(stale["postgres_authority_ready"])
        self.assertFalse(stale["core_ready"])

    def test_direct_hr_upload_cannot_bypass_encrypted_authority_in_production(self) -> None:
        source = ROUTER_SOURCE[
            ROUTER_SOURCE.index("async def upload_candidate_evidence("): 
            ROUTER_SOURCE.index("def create_candidate_upload_capability(")
        ]
        secure_at = source.index("secure_hr_candidate_upload")
        legacy_at = source.index("add_candidate_evidence")
        self.assertLess(secure_at, legacy_at)
        self.assertIn('environment == "production" or storage_mode == "s3-kms-envelope"', source)

    def test_authority_uses_constant_public_error_for_secret_states(self) -> None:
        self.assertEqual(
            str(candidate_upload_authority._invalid()),
            "Aday yükleme yetkisi geçersiz veya süresi dolmuş.",
        )

    def test_plaintext_finalize_is_explicitly_nonproduction_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DOCKOS_ENV": "production"}, clear=False
        ):
            with self.assertRaisesRegex(
                candidate_upload_authority.CandidateUploadAuthorityError,
                "plaintext dosya sistemine yazılamaz",
            ):
                candidate_upload_authority._finalize_local_development(
                    "x" * 40,
                    "RESIDENCE",
                    "residence.pdf",
                    "application/pdf",
                    b"%PDF-1.7\nproduction",
                    Path(directory),
                    retention_days=365,
                )


if __name__ == "__main__":
    unittest.main()
