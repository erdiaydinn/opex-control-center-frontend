from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from app.modules.recruitment import production_startup_guard as guard
from app.modules.recruitment.production_startup_guard import RecruitmentProductionStartupError


class ProductionStartupGuardTests(unittest.TestCase):
    def env(self):
        return {"DOCKOS_ENV": "production", "RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE": "postgres", "RECRUITMENT_EVIDENCE_STORAGE_MODE": "s3-kms-envelope"}

    def test_v44_is_rejected_even_when_other_config_is_present(self):
        with patch.dict(os.environ, self.env(), clear=False), patch.object(guard.persistence, "ENABLED", True), patch.object(guard.persistence, "schema_version", return_value=44):
            with self.assertRaisesRegex(RecruitmentProductionStartupError, "V45"):
                guard.assert_recruitment_production_ready()

    def test_repository_controlled_authorities_can_start_without_e_devlet_contract(self):
        with patch.dict(os.environ, self.env(), clear=False), patch.object(guard.persistence, "ENABLED", True), patch.object(guard.persistence, "schema_version", return_value=45), patch.object(guard.S3KmsEnvelopeEvidenceStore, "from_environment") as storage, patch.object(guard.AwsKmsHmacKeyAuthority, "from_environment") as scanner_kms, patch.object(guard, "scanner_db_preflight", return_value={"session_user": "eay_candidate_scanner_runtime"}) as scanner_db:
            guard.assert_recruitment_production_ready()
        storage.assert_called_once_with()
        scanner_kms.assert_called_once_with()
        scanner_db.assert_called_once_with()

    def test_plaintext_storage_or_non_postgres_upload_authority_is_rejected(self):
        bad_storage = {**self.env(), "RECRUITMENT_EVIDENCE_STORAGE_MODE": "legacy-local"}
        with patch.dict(os.environ, bad_storage, clear=False), patch.object(guard.persistence, "ENABLED", True), patch.object(guard.persistence, "schema_version", return_value=45):
            with self.assertRaisesRegex(RecruitmentProductionStartupError, "S3/KMS"):
                guard.assert_recruitment_production_ready()
        bad_upload = {**self.env(), "RECRUITMENT_CANDIDATE_UPLOAD_AUTHORITY_MODE": "legacy-development"}
        with patch.dict(os.environ, bad_upload, clear=False), patch.object(guard.persistence, "ENABLED", True), patch.object(guard.persistence, "schema_version", return_value=45):
            with self.assertRaisesRegex(RecruitmentProductionStartupError, "PostgreSQL modunda"):
                guard.assert_recruitment_production_ready()


if __name__ == "__main__":
    unittest.main()
