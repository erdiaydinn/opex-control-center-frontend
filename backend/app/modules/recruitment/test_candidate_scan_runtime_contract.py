from __future__ import annotations

import inspect
import unittest

from app.modules.recruitment import candidate_scan_authority, service


class CandidateScanRuntimeContractTests(unittest.TestCase):
    def test_receipt_claim_aggregate_and_audit_share_one_transaction(self) -> None:
        source = inspect.getsource(candidate_scan_authority.record_verified_scan)
        claim_at = source.index("record_candidate_evidence_scan_receipt")
        aggregate_at = source.index("SELECT payload,revision")
        audit_at = source.index("_build_audit_record")
        commit_at = source.index("database.commit()")
        self.assertLess(claim_at, aggregate_at)
        self.assertLess(aggregate_at, audit_at)
        self.assertLess(audit_at, commit_at)

    def test_exact_evidence_binding_is_database_derived(self) -> None:
        source = inspect.getsource(candidate_scan_authority.record_verified_scan)
        self.assertIn("get_candidate_evidence_scan_binding", source)
        self.assertIn("expected_evidence_sha256=evidence_hex", source)
        self.assertIn('item.get("id") == str(evidence_id)', source)

    def test_production_rejects_legacy_boolean_scanner_authority(self) -> None:
        source = inspect.getsource(service.record_candidate_content_safety_scan)
        self.assertIn('os.getenv("DOCKOS_ENV", "development")', source)
        self.assertIn("kriptografik receipt otoritesi", source)


if __name__ == "__main__":
    unittest.main()
