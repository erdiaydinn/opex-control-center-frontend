from __future__ import annotations

import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.modules.recruitment import scanner_callback_router as router


class ScannerCallbackRouterTests(unittest.TestCase):
    def envelope(self):
        return router.ScannerReceiptEnvelope(
            payload={"evidence_id": "11111111-1111-1111-1111-111111111111"},
            signature="signed-receipt",
        )

    def test_candidate_callback_permission_is_checked_before_kms_or_database(self):
        with patch.object(router, "_require", side_effect=HTTPException(status_code=403, detail="forbidden")), patch.object(
            router, "record_verified_scan"
        ) as scanner:
            with self.assertRaises(HTTPException) as raised:
                router.candidate_scanner_receipt(
                    self.envelope(),
                    x_opex_role="hr",
                    x_opex_permissions="viewRecruitmentEvidence",
                )
        self.assertEqual(raised.exception.status_code, 403)
        scanner.assert_not_called()

    def test_request_callback_permission_is_checked_before_kms_or_database(self):
        with patch.object(router, "_require", side_effect=HTTPException(status_code=403, detail="forbidden")), patch.object(
            router, "record_verified_request_scan"
        ) as scanner:
            with self.assertRaises(HTTPException) as raised:
                router.request_scanner_receipt(
                    "REQ-1",
                    self.envelope(),
                    x_opex_role="hr",
                    x_opex_permissions="approveRecruitmentRequest",
                )
        self.assertEqual(raised.exception.status_code, 403)
        scanner.assert_not_called()

    def test_explicit_service_permission_reaches_crypto_authority(self):
        evidence = {"id": "11111111-1111-1111-1111-111111111111", "content_safety_state": "MALWARE_CLEARED"}
        with patch.object(router, "_require") as require, patch.object(
            router, "record_verified_scan", return_value=evidence
        ) as scanner:
            result = router.candidate_scanner_receipt(
                self.envelope(),
                x_opex_role="service",
                x_opex_permissions="submitRecruitmentScannerReceipt",
            )
        require.assert_called_once_with(
            "service", "submitRecruitmentScannerReceipt", "submitRecruitmentScannerReceipt"
        )
        scanner.assert_called_once()
        self.assertTrue(result["accepted"])

    def test_main_mounts_priority_scanner_router_before_other_recruitment_routers(self):
        from pathlib import Path

        source = (Path(__file__).resolve().parents[2] / "main.py").read_text(encoding="utf-8")
        scanner_at = source.index('app.include_router(recruitment_scanner_callback_router, prefix="/api")')
        evidence_at = source.index('app.include_router(recruitment_production_evidence_router, prefix="/api")')
        legacy_at = source.index('app.include_router(recruitment_router, prefix="/api")')
        self.assertLess(scanner_at, evidence_at)
        self.assertLess(evidence_at, legacy_at)


if __name__ == "__main__":
    unittest.main()
