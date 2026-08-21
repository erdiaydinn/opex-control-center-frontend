from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.modules.recruitment import production_evidence_router as security_router
from app.modules.recruitment.schemas import (
    RecruitmentCandidateDocumentAttestation,
    RecruitmentCandidateDocumentVerification,
)


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

    def common_patches(self, evidence: dict):
        return (
            patch.object(security_router, "_require"),
            patch.object(
                security_router,
                "_request_row",
                return_value={"id": "REQ-1", "warehouse_id": "WH-1"},
            ),
            patch.object(security_router, "_require_rows_in_scope"),
            patch.object(
                security_router,
                "locate_candidate_evidence",
                return_value=({}, {"id": "CAND-1"}, evidence),
            ),
            patch.object(security_router, "_encrypted_mode", return_value=True),
            patch.object(security_router, "_identity", return_value=("hr-1", "HR")),
        )

    def test_human_assist_returns_only_public_launch_contract_no_session_automation(self):
        evidence = self.evidence()
        patches = self.common_patches(evidence)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
            security_router, "require_candidate_evidence_released"
        ) as released, patch.object(
            security_router.persistence, "append_audit"
        ) as audit:
            result = security_router.official_document_human_assist(
                "REQ-1",
                "CAND-1",
                "a" * 64,
                SimpleNamespace(),
                x_opex_role="hr",
                x_opex_permissions="viewRecruitmentEvidence,approveRecruitmentRequest",
            )

        self.assertEqual(result["mode"], "HR_ASSISTED_OFFICIAL_PORTAL")
        self.assertEqual(result["launch_url"], "https://www.turkiye.gov.tr/belge-dogrulama")
        self.assertFalse(result["credential_capture"])
        self.assertFalse(result["browser_automation"])
        self.assertFalse(result["captcha_automation"])
        self.assertFalse(result["session_import"])
        self.assertEqual(result["evidence_sha256"], "a" * 64)
        released.assert_called_once_with("REQ-1", "CAND-1", evidence)
        audit.assert_called_once()
        self.assertFalse(audit.call_args.kwargs["credential_capture"])
        self.assertFalse(audit.call_args.kwargs["browser_automation"])

    def test_candidate_portal_uses_user_assisted_official_handoff_without_session_capture(self):
        portal = (
            Path(__file__).resolve().parents[4]
            / "src"
            / "modules"
            / "recruitment"
            / "CandidateDocumentPortal.jsx"
        ).read_text(encoding="utf-8")
        self.assertIn('const EDEVLET_HOME = "https://www.turkiye.gov.tr/"', portal)
        self.assertIn('href={EDEVLET_HOME} target="_blank" rel="noopener noreferrer"', portal)
        self.assertIn("sessionStorage.setItem(SESSION_KEY, capability)", portal)
        self.assertIn('window.addEventListener("focus", markReturned)', portal)
        self.assertIn("EAY bu sekmeyi okuyamaz ve yönetmez", portal)
        self.assertIn("Tarayıcı güvenliği gereği", portal)
        self.assertIn("İndirilenler klasörü otomatik okunamaz", portal)
        self.assertNotIn("window.open", portal)
        self.assertNotIn("document.cookie", portal)
        self.assertNotIn("localStorage.setItem", portal)
        self.assertNotIn("captcha_automation", portal)
        self.assertNotIn("session_import", portal)
        self.assertLess(portal.index("if (!result?.accepted)"), portal.index("sessionStorage.removeItem(SESSION_KEY)"))

    def test_non_official_document_cannot_enter_e_devlet_assist_flow(self):
        evidence = {**self.evidence(), "requires_official_verification": False}
        patches = self.common_patches(evidence)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            with self.assertRaisesRegex(Exception, "resmî doğrulama gerekmiyor"):
                security_router.official_document_human_assist(
                    "REQ-1",
                    "CAND-1",
                    "a" * 64,
                    SimpleNamespace(),
                    x_opex_role="hr",
                    x_opex_permissions="viewRecruitmentEvidence,approveRecruitmentRequest",
                )

    def test_human_verification_cannot_bypass_scanner_release(self):
        evidence = self.evidence()
        patches = self.common_patches(evidence)
        payload = RecruitmentCandidateDocumentVerification(
            evidence_sha256="a" * 64,
            result="VERIFIED",
            subject_match="MATCH",
            document_type="CRIMINAL_RECORD",
            official_receipt_id="official-receipt-1",
            official_response_sha256="b" * 64,
            note="Official portal result witnessed by HR.",
        )
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
            security_router,
            "require_candidate_evidence_released",
            side_effect=security_router.EvidenceReleaseAuthorityError("release denied"),
        ), patch.object(
            security_router, "record_candidate_document_verification"
        ) as record:
            with self.assertRaisesRegex(Exception, "release denied"):
                security_router.secure_human_document_verification(
                    "REQ-1",
                    "CAND-1",
                    payload,
                    SimpleNamespace(),
                    x_opex_role="hr",
                    x_opex_permissions="viewRecruitmentEvidence,approveRecruitmentRequest",
                )
        record.assert_not_called()

    def test_four_eyes_attestation_rechecks_current_scanner_release(self):
        evidence = self.evidence()
        patches = self.common_patches(evidence)
        payload = RecruitmentCandidateDocumentAttestation(
            evidence_sha256="a" * 64,
            note="Second-authority confirmation.",
        )
        call_order: list[str] = []

        def release(*_args):
            call_order.append("release")

        def attest(*_args, **_kwargs):
            call_order.append("attest")
            return {"status": "ok"}

        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patch.object(
            security_router, "require_candidate_evidence_released", side_effect=release
        ), patch.object(
            security_router, "attest_candidate_document_verification", side_effect=attest
        ):
            result = security_router.secure_human_document_attestation(
                "REQ-1",
                "CAND-1",
                payload,
                SimpleNamespace(),
                x_opex_role="hr",
                x_opex_permissions="approveRecruitmentRequest",
            )
        self.assertEqual(result, {"status": "ok"})
        self.assertEqual(call_order, ["release", "attest"])


if __name__ == "__main__":
    unittest.main()
