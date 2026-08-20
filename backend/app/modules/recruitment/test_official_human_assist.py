from __future__ import annotations

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.modules.recruitment import production_evidence_router as security_router


class OfficialHumanAssistTests(unittest.TestCase):
    def evidence(self) -> dict:
        return {
            "id": "11111111-1111-1111-1111-111111111111",
            "sha256": "a" * 64,
            "storage_backend": "S3_KMS_ENVELOPE",
            "document_type": "CRIMINAL_RECORD",
            "requires_official_verification": True,
            "content_safety_state": "MALWARE_CLEARED",
            "content_safety_truth_boundary": "CRYPTOGRAPHIC_SCANNER_RECEIPT",
            "content_safety_receipt": {
                "signature_verified": True,
                "result": "CLEAN",
                "evidence_sha256": "a" * 64,
            },
        }

    def test_human_assist_returns_only_public_launch_contract_no_session_automation(self):
        evidence = self.evidence()
        request = SimpleNamespace()
        with patch.object(security_router, "_require"), patch.object(
            security_router,
            "_request_row",
            return_value={"id": "REQ-1", "warehouse_id": "WH-1"},
        ), patch.object(
            security_router, "_require_rows_in_scope"
        ), patch.object(
            security_router,
            "locate_candidate_evidence",
            return_value=({}, {"id": "CAND-1"}, evidence),
        ), patch.object(
            security_router, "require_candidate_evidence_released"
        ) as released, patch.object(
            security_router, "_identity", return_value=("hr-1", "HR")
        ), patch.object(
            security_router.persistence, "append_audit"
        ) as audit, patch.object(
            security_router, "_encrypted_mode", return_value=True
        ):
            result = security_router.official_document_human_assist(
                "REQ-1",
                "CAND-1",
                "a" * 64,
                request,
                x_opex_role="hr",
                x_opex_permissions="viewRecruitmentEvidence,approveRecruitmentRequest",
            )

        self.assertEqual(result["mode"], "HR_ASSISTED_OFFICIAL_PORTAL")
        self.assertEqual(
            result["launch_url"],
            "https://www.turkiye.gov.tr/belge-dogrulama",
        )
        self.assertFalse(result["credential_capture"])
        self.assertFalse(result["browser_automation"])
        self.assertFalse(result["captcha_automation"])
        self.assertFalse(result["session_import"])
        self.assertEqual(result["evidence_sha256"], "a" * 64)
        released.assert_called_once_with("REQ-1", "CAND-1", evidence)
        audit.assert_called_once()
        audit_kwargs = audit.call_args.kwargs
        self.assertFalse(audit_kwargs["credential_capture"])
        self.assertFalse(audit_kwargs["browser_automation"])

    def test_non_official_document_cannot_enter_e_devlet_assist_flow(self):
        evidence = {**self.evidence(), "requires_official_verification": False}
        with patch.object(security_router, "_require"), patch.object(
            security_router,
            "_request_row",
            return_value={"id": "REQ-1", "warehouse_id": "WH-1"},
        ), patch.object(
            security_router, "_require_rows_in_scope"
        ), patch.object(
            security_router,
            "locate_candidate_evidence",
            return_value=({}, {"id": "CAND-1"}, evidence),
        ):
            with self.assertRaisesRegex(Exception, "resmî doğrulama gerekmiyor"):
                security_router.official_document_human_assist(
                    "REQ-1",
                    "CAND-1",
                    "a" * 64,
                    SimpleNamespace(),
                    x_opex_role="hr",
                    x_opex_permissions="viewRecruitmentEvidence,approveRecruitmentRequest",
                )


if __name__ == "__main__":
    unittest.main()
