from pathlib import Path
import unittest


class CandidateUploadMigrationContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.sql = (
            Path(__file__).resolve().parents[3]
            / "migrations"
            / "023_recruitment_candidate_upload_authority.sql"
        ).read_text(encoding="utf-8")

    def test_authority_tables_are_tenant_forced_and_not_public(self) -> None:
        for table in (
            "candidate_upload_capabilities",
            "candidate_evidence_objects",
            "candidate_evidence_scan_receipts",
        ):
            self.assertIn(f"ALTER TABLE recruitment.{table} FORCE ROW LEVEL SECURITY", self.sql)
        self.assertIn("REVOKE ALL ON ALL TABLES IN SCHEMA recruitment FROM PUBLIC", self.sql)
        self.assertIn("REVOKE ALL ON ALL FUNCTIONS IN SCHEMA recruitment FROM PUBLIC", self.sql)

    def test_secret_and_evidence_bindings_are_database_enforced(self) -> None:
        self.assertIn("UNIQUE (token_sha256)", self.sql)
        self.assertIn("CHECK (octet_length(token_sha256) = 32)", self.sql)
        self.assertIn("UNIQUE (tenant_id, capability_id)", self.sql)
        self.assertIn("REFERENCES recruitment.candidate_upload_capabilities", self.sql)
        self.assertIn("candidate_capability_consumed_evidence_fk", self.sql)
        self.assertIn("DEFERRABLE INITIALLY DEFERRED", self.sql)
        self.assertIn("candidate upload authority records are append-only", self.sql)
        self.assertIn("candidate upload capability authority is immutable", self.sql)
        self.assertIn("capability must transition to exactly one terminal state", self.sql)

    def test_signed_scanner_receipt_is_separate_append_only_authority(self) -> None:
        self.assertIn("candidate_evidence_scan_receipts", self.sql)
        self.assertIn("signature_verified boolean NOT NULL CHECK (signature_verified)", self.sql)
        self.assertIn("UNIQUE (tenant_id, provider, receipt_id)", self.sql)
        self.assertIn("FOREIGN KEY (tenant_id, evidence_id, evidence_sha256)", self.sql)
        self.assertIn("scan_receipt_id uuid NOT NULL", self.sql)

    def test_legacy_public_runtime_is_fail_closed_in_production(self) -> None:
        router_source = (Path(__file__).resolve().parent / "router.py").read_text(encoding="utf-8")
        self.assertIn('environment == "production"', router_source)
        self.assertIn('mode != "legacy-development"', router_source)
        self.assertIn("CANDIDATE_UPLOAD_AUTHORITY_NOT_READY", router_source)


if __name__ == "__main__":
    unittest.main()
