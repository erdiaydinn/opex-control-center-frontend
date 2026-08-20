from copy import deepcopy
import unittest
from unittest.mock import patch

from . import service


class OfficialDocumentGovernanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.request = {
            "id": "REC-DOC-QA", "status": "APPROVED", "warehouse_id": "fulya",
            "revision": 7, "history": [], "candidates": [{
                "id": "CAND-DOC-QA", "status": "REVIEW_PENDING", "evidence": [{
                    "sha256": "a" * 64, "document_type": "RESIDENCE",
                    "requires_official_verification": True,
                    "verification_state": "BARCODE_EXTRACTION_PENDING",
                    "official_verification": None,
                }],
            }],
        }
        self.payload = {
            "evidence_sha256": "a" * 64, "result": "VERIFIED",
            "subject_match": "MATCH", "document_type": "RESIDENCE",
            "official_receipt_id": "EDV-QA-001",
            "official_response_sha256": "b" * 64,
            "issued_at": "2026-08-20", "note": "Official portal witnessed by HR.",
        }

    def verify(self, request: dict, payload: dict | None = None) -> dict:
        with (
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "_save_request") as save,
        ):
            result = service.record_candidate_document_verification(
                request["id"], "CAND-DOC-QA", payload or self.payload, "hr-qa",
                verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
            )
        self.assertEqual(save.call_args.args[1], 7)
        return result

    def test_subject_mismatch_never_becomes_officially_verified(self) -> None:
        payload = {**self.payload, "subject_match": "MISMATCH"}
        candidate = self.verify(self.request, payload)
        evidence = candidate["evidence"][0]
        self.assertEqual(evidence["verification_state"], "OFFICIAL_REVIEW_FAILED")
        self.assertFalse(evidence["official_verification"]["verified"])
        with patch.object(service, "list_requests", return_value=[self.request]):
            with self.assertRaisesRegex(service.RecruitmentRuleError, "Resmî doğrulama"):
                service.decide_candidate(
                    self.request["id"], "CAND-DOC-QA", "APPROVED", "approve", "hr-qa"
                )

    def test_verified_receipt_is_immutable_and_cannot_be_overwritten(self) -> None:
        self.verify(self.request)
        replacement = {
            **self.payload,
            "result": "FAILED",
            "subject_match": "NOT_CHECKED",
            "official_receipt_id": "EDV-QA-REPLACEMENT",
            "official_response_sha256": "c" * 64,
        }
        with (
            patch.object(service, "list_requests", return_value=[self.request]),
            patch.object(service, "_save_request"),
        ):
            with self.assertRaisesRegex(service.RecruitmentRuleError, "değiştirilemez"):
                service.record_candidate_document_verification(
                    self.request["id"], "CAND-DOC-QA", replacement, "hr-qa-2",
                    verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
                )

    def test_non_official_evidence_cannot_receive_official_receipt(self) -> None:
        request = deepcopy(self.request)
        evidence = request["candidates"][0]["evidence"][0]
        evidence.update({"document_type": "OTHER", "requires_official_verification": False})
        with patch.object(service, "list_requests", return_value=[request]):
            with self.assertRaisesRegex(service.RecruitmentRuleError, "resmî doğrulama"):
                service.record_candidate_document_verification(
                    request["id"], "CAND-DOC-QA", self.payload, "hr-qa",
                    verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
                )

    def test_official_receipt_cannot_be_replayed_across_candidates(self) -> None:
        request = deepcopy(self.request)
        request["candidates"].append({
            "id": "CAND-OTHER", "status": "REVIEW_PENDING", "evidence": [{
                "sha256": "f" * 64, "document_type": "RESIDENCE",
                "requires_official_verification": True,
                "verification_state": "HUMAN_WITNESSED_PENDING_ATTESTATION",
                "official_verification": {"official_receipt_id": self.payload["official_receipt_id"]},
            }],
        })
        with patch.object(service, "list_requests", return_value=[request]):
            with self.assertRaisesRegex(service.RecruitmentRuleError, "replay engellendi"):
                service.record_candidate_document_verification(
                    request["id"], "CAND-DOC-QA", self.payload, "hr-qa",
                    verification_method="HR_ASSISTED_OFFICIAL_PORTAL",
                )

    def test_authorized_api_result_uses_distinct_truth_state(self) -> None:
        request = deepcopy(self.request)
        with (
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "_save_request"),
        ):
            candidate = service.record_candidate_document_verification(
                request["id"], "CAND-DOC-QA", self.payload, "verifier-service",
                verification_method="AUTHORIZED_OFFICIAL_API", provider_signature_verified=True,
            )
        evidence = candidate["evidence"][0]
        self.assertEqual(evidence["verification_state"], "OFFICIAL_VERIFIED")
        self.assertEqual(
            evidence["official_verification"]["truth_boundary"],
            "AUTHORIZED_MACHINE_TO_MACHINE",
        )

    def test_authorized_api_rejects_unsigned_provider_claim(self) -> None:
        request = deepcopy(self.request)
        with patch.object(service, "list_requests", return_value=[request]):
            with self.assertRaisesRegex(service.RecruitmentRuleError, "servis imzası"):
                service.record_candidate_document_verification(
                    request["id"], "CAND-DOC-QA", self.payload, "untrusted-service",
                    verification_method="AUTHORIZED_OFFICIAL_API",
                )

    def test_legacy_non_official_evidence_remains_approvable(self) -> None:
        request = deepcopy(self.request)
        request["candidates"][0]["evidence"] = [{"sha256": "d" * 64}]
        with (
            patch.object(service, "list_requests", return_value=[request]),
            patch.object(service, "_save_request") as save,
        ):
            result = service.decide_candidate(
                request["id"], "CAND-DOC-QA", "APPROVED", "legacy CV reviewed", "hr-qa"
            )
        self.assertEqual(result["status"], "APPROVED")
        self.assertEqual(save.call_args.args[1], 7)


if __name__ == "__main__":
    unittest.main()
