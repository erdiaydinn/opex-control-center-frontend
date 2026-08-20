from __future__ import annotations

import os
import unittest
from unittest.mock import Mock, patch

from app.modules.recruitment import official_document_m2m_runtime as runtime
from app.modules.recruitment.evidence_release_authority import EvidenceReleaseAuthorityError
from app.modules.recruitment.official_document_m2m_runtime import (
    OfficialM2MRuntimeError,
    OfficialM2MVerificationRequest,
)


class OfficialM2MRuntimeTests(unittest.TestCase):
    def payload(self):
        return OfficialM2MVerificationRequest(
            evidence_sha256="a" * 64,
            document_type="RESIDENCE",
            barcode="official-barcode",
            subject_reference="subject-reference",
            note="official verification",
        )

    def evidence(self, **updates):
        value = {
            "id": "11111111-1111-1111-1111-111111111111",
            "sha256": "a" * 64,
            "document_type": "RESIDENCE",
            "requires_official_verification": True,
            "official_verification": None,
            "content_safety_state": "MALWARE_CLEARED",
            "content_safety_truth_boundary": "CRYPTOGRAPHIC_SCANNER_RECEIPT",
            "content_safety_receipt": {
                "signature_verified": True,
                "result": "CLEAN",
                "evidence_sha256": "a" * 64,
            },
            "storage_backend": "S3_KMS_ENVELOPE",
            "encryption_scheme": "AES-256-GCM+AWS-KMS-DATA-KEY",
        }
        value.update(updates)
        return value

    def adapter(self):
        adapter = Mock()
        adapter.verify_document.return_value = {
            "official_receipt_id": "official-receipt-1",
            "result": "VERIFIED",
            "subject_match": "MATCH",
            "document_type": "RESIDENCE",
            "evidence_sha256": "a" * 64,
            "official_response_sha256": "b" * 64,
            "provider_signature_verified": True,
            "verification_method": "AUTHORIZED_OFFICIAL_API",
            "truth_boundary": "AUTHORIZED_MACHINE_TO_MACHINE",
        }
        return adapter

    def test_production_rejects_legacy_evidence_before_external_call(self):
        adapter = self.adapter()
        with patch.object(
            runtime,
            "locate_candidate_evidence",
            return_value=({}, {}, self.evidence(storage_backend="LEGACY_LOCAL")),
        ), patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False), patch.object(
            runtime.persistence, "ENABLED", True
        ), patch.object(runtime.persistence, "schema_version", return_value=42):
            with self.assertRaises(OfficialM2MRuntimeError):
                runtime.verify_authorized_candidate_document(
                    "REQ-1",
                    "CAND-1",
                    self.payload(),
                    actor="hr-user",
                    correlation_id="correlation",
                    adapter=adapter,
                )
        adapter.verify_document.assert_not_called()

    def test_production_aggregate_clean_cannot_bypass_v42_release_authority(self):
        adapter = self.adapter()
        with patch.object(
            runtime, "locate_candidate_evidence", return_value=({}, {}, self.evidence())
        ), patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False), patch.object(
            runtime.persistence, "ENABLED", True
        ), patch.object(
            runtime.persistence, "schema_version", return_value=42
        ), patch.object(
            runtime,
            "require_candidate_evidence_released",
            side_effect=EvidenceReleaseAuthorityError("release denied"),
        ) as release:
            with self.assertRaisesRegex(OfficialM2MRuntimeError, "append-only scanner authority"):
                runtime.verify_authorized_candidate_document(
                    "REQ-1",
                    "CAND-1",
                    self.payload(),
                    actor="hr-user",
                    correlation_id="correlation",
                    adapter=adapter,
                )
        release.assert_called_once()
        adapter.verify_document.assert_not_called()

    def test_production_release_is_checked_before_external_provider_call(self):
        adapter = self.adapter()
        recorded_candidate = {"id": "CAND-1", "status": "REVIEW_PENDING"}
        order: list[str] = []

        def released(*_args):
            order.append("release")

        def verify_document(**_kwargs):
            order.append("provider")
            return self.adapter().verify_document.return_value

        adapter.verify_document.side_effect = verify_document
        with patch.object(
            runtime, "locate_candidate_evidence", return_value=({}, {}, self.evidence())
        ), patch.dict(os.environ, {"DOCKOS_ENV": "production"}, clear=False), patch.object(
            runtime.persistence, "ENABLED", True
        ), patch.object(
            runtime.persistence, "schema_version", return_value=42
        ), patch.object(
            runtime, "require_candidate_evidence_released", side_effect=released
        ), patch(
            "app.modules.recruitment.service.record_candidate_document_verification",
            return_value=recorded_candidate,
        ):
            result = runtime.verify_authorized_candidate_document(
                "REQ-1",
                "CAND-1",
                self.payload(),
                actor="hr-user",
                correlation_id="correlation",
                adapter=adapter,
            )
        self.assertEqual(result, recorded_candidate)
        self.assertEqual(order, ["release", "provider"])

    def test_unscanned_evidence_does_not_leave_eay(self):
        adapter = self.adapter()
        with patch.object(
            runtime,
            "locate_candidate_evidence",
            return_value=({}, {}, self.evidence(content_safety_state="STATIC_FORMAT_ACCEPTED_AV_PENDING")),
        ):
            with self.assertRaises(OfficialM2MRuntimeError):
                runtime.verify_authorized_candidate_document(
                    "REQ-1",
                    "CAND-1",
                    self.payload(),
                    actor="hr-user",
                    correlation_id="correlation",
                    adapter=adapter,
                )
        adapter.verify_document.assert_not_called()

    def test_existing_official_verification_blocks_replay(self):
        adapter = self.adapter()
        with patch.object(
            runtime,
            "locate_candidate_evidence",
            return_value=({}, {}, self.evidence(official_verification={"official_receipt_id": "existing"})),
        ):
            with self.assertRaises(OfficialM2MRuntimeError):
                runtime.verify_authorized_candidate_document(
                    "REQ-1",
                    "CAND-1",
                    self.payload(),
                    actor="hr-user",
                    correlation_id="correlation",
                    adapter=adapter,
                )
        adapter.verify_document.assert_not_called()

    def test_verified_provider_result_is_sealed_without_transport_pii(self):
        adapter = self.adapter()
        recorded_candidate = {"id": "CAND-1", "status": "REVIEW_PENDING"}
        with patch.object(
            runtime, "locate_candidate_evidence", return_value=({}, {}, self.evidence())
        ), patch(
            "app.modules.recruitment.service.record_candidate_document_verification",
            return_value=recorded_candidate,
        ) as record:
            result = runtime.verify_authorized_candidate_document(
                "REQ-1",
                "CAND-1",
                self.payload(),
                actor="hr-user",
                correlation_id="correlation",
                adapter=adapter,
            )
        self.assertEqual(result, recorded_candidate)
        service_payload = record.call_args.args[2]
        self.assertNotIn("barcode", service_payload)
        self.assertNotIn("subject_reference", service_payload)
        self.assertEqual(service_payload["official_receipt_id"], "official-receipt-1")
        self.assertEqual(service_payload["official_response_sha256"], "b" * 64)
        self.assertTrue(record.call_args.kwargs["provider_signature_verified"])


if __name__ == "__main__":
    unittest.main()
