from __future__ import annotations

from pathlib import Path
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.modules.recruitment import production_authority_preflight as preflight
from app.modules.recruitment.candidate_evidence_storage import EvidenceStorageError
from app.modules.recruitment.production_authority_preflight import ProductionAuthorityPreflightError


class ProductionAuthorityPreflightTests(unittest.TestCase):
    def infrastructure(self):
        storage = Mock()
        storage.preflight.return_value = {"kms_key_state": "Enabled", "kms_key_usage": "ENCRYPT_DECRYPT", "s3_versioning": "Enabled", "s3_object_lock": "Enabled"}
        scanner = Mock()
        scanner.preflight.return_value = {"active_kid": "2026-08", "verification_kids": ("2026-07", "2026-08"), "verified_key_count": 2}
        return storage, scanner

    def blank_m2m_env(self):
        return {name: "" for name in preflight._M2M_ENV}

    def test_repo_controlled_authorities_are_ready_while_e_devlet_agreement_is_pending(self):
        storage, scanner = self.infrastructure()
        with patch.dict(os.environ, self.blank_m2m_env(), clear=False), patch.object(preflight.persistence, "ENABLED", True), patch.object(preflight.persistence, "schema_version", return_value=47), patch.object(preflight.S3KmsEnvelopeEvidenceStore, "from_environment", return_value=storage), patch.object(preflight.AwsKmsHmacKeyAuthority, "from_environment", return_value=scanner), patch.object(preflight, "scanner_db_preflight", return_value={"session_user": "eay_candidate_scanner_runtime"}), patch.object(preflight.AuthorizedOfficialM2MAdapter, "from_environment") as official:
            result = preflight.run_live_preflight()
        self.assertTrue(result["ready"])
        self.assertEqual(result["checks"][0]["key"], "postgres_v47")
        self.assertEqual(result["external_pending"], ["official_m2m_transport"])
        transport = next(check for check in result["checks"] if check["key"] == "official_m2m_transport")
        self.assertFalse(transport["required"])
        self.assertIsNone(transport["ok"])
        self.assertFalse(transport["detail"]["blocking"])
        self.assertFalse(transport["detail"]["document_submitted"])
        official.assert_not_called()

    def test_fully_configured_m2m_proves_transport_without_submitting_document(self):
        storage, scanner = self.infrastructure()
        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "client.crt"
            key = Path(directory) / "client.key"
            cert.write_text("test-cert", encoding="utf-8")
            key.write_text("test-key", encoding="utf-8")
            configured = {name: "configured" for name in preflight._M2M_ENV}
            configured["RECRUITMENT_OFFICIAL_M2M_MTLS_CERT"] = str(cert)
            configured["RECRUITMENT_OFFICIAL_M2M_MTLS_KEY"] = str(key)
            adapter = Mock()
            adapter.config.mtls_cert = str(cert)
            adapter.config.mtls_key = str(key)
            adapter.config.contract_id = "official-contract-v1"
            adapter._access_token.return_value = "opaque-oauth-token"
            with patch.dict(os.environ, configured, clear=False), patch.object(preflight.persistence, "ENABLED", True), patch.object(preflight.persistence, "schema_version", return_value=47), patch.object(preflight.S3KmsEnvelopeEvidenceStore, "from_environment", return_value=storage), patch.object(preflight.AwsKmsHmacKeyAuthority, "from_environment", return_value=scanner), patch.object(preflight, "scanner_db_preflight", return_value={"session_user": "eay_candidate_scanner_runtime"}), patch.object(preflight.AuthorizedOfficialM2MAdapter, "from_environment", return_value=adapter), patch.object(preflight, "canonical_response_mapper", return_value={}):
                result = preflight.run_live_preflight()
        self.assertTrue(result["ready"])
        self.assertEqual(result["external_pending"], [])
        transport = next(check for check in result["checks"] if check["key"] == "official_m2m_transport")
        self.assertTrue(transport["ok"])
        self.assertFalse(transport["detail"]["document_submitted"])
        self.assertNotIn("opaque-oauth-token", repr(result))

    def test_partial_m2m_configuration_fails_closed(self):
        storage, scanner = self.infrastructure()
        partial = self.blank_m2m_env()
        partial["RECRUITMENT_OFFICIAL_M2M_ENDPOINT"] = "https://institution.example/verify"
        with patch.dict(os.environ, partial, clear=False), patch.object(preflight.persistence, "ENABLED", True), patch.object(preflight.persistence, "schema_version", return_value=47), patch.object(preflight.S3KmsEnvelopeEvidenceStore, "from_environment", return_value=storage), patch.object(preflight.AwsKmsHmacKeyAuthority, "from_environment", return_value=scanner), patch.object(preflight, "scanner_db_preflight", return_value={"session_user": "eay_candidate_scanner_runtime"}):
            with self.assertRaisesRegex(ProductionAuthorityPreflightError, "kısmi yapılandırması"):
                preflight.run_live_preflight()

    def test_v46_fails_before_external_authorities_are_touched(self):
        with patch.object(preflight.persistence, "ENABLED", True), patch.object(preflight.persistence, "schema_version", return_value=46), patch.object(preflight.S3KmsEnvelopeEvidenceStore, "from_environment") as storage, patch.object(preflight.AwsKmsHmacKeyAuthority, "from_environment") as scanner, patch.object(preflight, "scanner_db_preflight") as scanner_db:
            with self.assertRaisesRegex(ProductionAuthorityPreflightError, "PostgreSQL V47"):
                preflight.run_live_preflight()
        storage.assert_not_called()
        scanner.assert_not_called()
        scanner_db.assert_not_called()

    def test_aws_storage_failure_is_fail_closed_before_scanner_authorities(self):
        with patch.object(preflight.persistence, "ENABLED", True), patch.object(preflight.persistence, "schema_version", return_value=47), patch.object(preflight.S3KmsEnvelopeEvidenceStore, "from_environment", side_effect=EvidenceStorageError("Object Lock disabled")), patch.object(preflight.AwsKmsHmacKeyAuthority, "from_environment") as scanner, patch.object(preflight, "scanner_db_preflight") as scanner_db:
            with self.assertRaisesRegex(ProductionAuthorityPreflightError, "Object Lock disabled"):
                preflight.run_live_preflight()
        scanner.assert_not_called()
        scanner_db.assert_not_called()


if __name__ == "__main__":
    unittest.main()
