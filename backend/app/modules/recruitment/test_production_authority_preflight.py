from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.modules.recruitment import production_authority_preflight as preflight
from app.modules.recruitment.candidate_evidence_storage import EvidenceStorageError
from app.modules.recruitment.production_authority_preflight import ProductionAuthorityPreflightError


class ProductionAuthorityPreflightTests(unittest.TestCase):
    def test_live_preflight_proves_infrastructure_without_submitting_document(self):
        storage = Mock()
        storage.preflight.return_value = {
            "kms_key_state": "Enabled",
            "kms_key_usage": "ENCRYPT_DECRYPT",
            "s3_versioning": "Enabled",
            "s3_object_lock": "Enabled",
        }
        scanner = Mock()
        scanner.preflight.return_value = {
            "active_kid": "2026-08",
            "verification_kids": ("2026-07", "2026-08"),
            "verified_key_count": 2,
        }

        with tempfile.TemporaryDirectory() as directory:
            cert = Path(directory) / "client.crt"
            key = Path(directory) / "client.key"
            cert.write_text("test-cert", encoding="utf-8")
            key.write_text("test-key", encoding="utf-8")
            adapter = Mock()
            adapter.config.mtls_cert = str(cert)
            adapter.config.mtls_key = str(key)
            adapter.config.contract_id = "official-contract-v1"
            adapter._access_token.return_value = "opaque-oauth-token"

            with patch.object(preflight.persistence, "ENABLED", True), patch.object(
                preflight.persistence, "schema_version", return_value=40
            ), patch.object(
                preflight.S3KmsEnvelopeEvidenceStore,
                "from_environment",
                return_value=storage,
            ), patch.object(
                preflight.AwsKmsHmacKeyAuthority,
                "from_environment",
                return_value=scanner,
            ), patch.object(
                preflight.AuthorizedOfficialM2MAdapter,
                "from_environment",
                return_value=adapter,
            ), patch.object(preflight, "canonical_response_mapper", return_value={}):
                result = preflight.run_live_preflight()

        self.assertTrue(result["ready"])
        self.assertEqual(
            result["truth_boundary"],
            "LIVE_INFRASTRUCTURE_AUTHORITY_PROOF_NO_DOCUMENT_VERIFICATION",
        )
        transport = next(
            check for check in result["checks"] if check["key"] == "official_m2m_transport"
        )
        self.assertFalse(transport["detail"]["document_submitted"])
        self.assertTrue(transport["detail"]["oauth_token_acquired"])
        self.assertNotIn("opaque-oauth-token", repr(result))
        storage.preflight.assert_called_once_with()
        scanner.preflight.assert_called_once_with()
        adapter._access_token.assert_called_once_with()

    def test_v39_fails_before_external_authorities_are_touched(self):
        with patch.object(preflight.persistence, "ENABLED", True), patch.object(
            preflight.persistence, "schema_version", return_value=39
        ), patch.object(
            preflight.S3KmsEnvelopeEvidenceStore, "from_environment"
        ) as storage, patch.object(
            preflight.AwsKmsHmacKeyAuthority, "from_environment"
        ) as scanner, patch.object(
            preflight.AuthorizedOfficialM2MAdapter, "from_environment"
        ) as official:
            with self.assertRaisesRegex(ProductionAuthorityPreflightError, "PostgreSQL V40"):
                preflight.run_live_preflight()
        storage.assert_not_called()
        scanner.assert_not_called()
        official.assert_not_called()

    def test_aws_storage_failure_is_fail_closed_before_scanner_or_official_transport(self):
        with patch.object(preflight.persistence, "ENABLED", True), patch.object(
            preflight.persistence, "schema_version", return_value=40
        ), patch.object(
            preflight.S3KmsEnvelopeEvidenceStore,
            "from_environment",
            side_effect=EvidenceStorageError("Object Lock disabled"),
        ), patch.object(
            preflight.AwsKmsHmacKeyAuthority, "from_environment"
        ) as scanner, patch.object(
            preflight.AuthorizedOfficialM2MAdapter, "from_environment"
        ) as official:
            with self.assertRaisesRegex(ProductionAuthorityPreflightError, "Object Lock disabled"):
                preflight.run_live_preflight()
        scanner.assert_not_called()
        official.assert_not_called()


if __name__ == "__main__":
    unittest.main()
