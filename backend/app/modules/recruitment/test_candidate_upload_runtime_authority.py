from __future__ import annotations

import inspect
from pathlib import Path
import unittest

from app.modules.recruitment import candidate_upload_authority


ROUTER_SOURCE = (Path(__file__).with_name("router.py")).read_text(encoding="utf-8")


class CandidateUploadRuntimeAuthorityTests(unittest.TestCase):
    def test_malformed_token_fails_before_database_lookup(self) -> None:
        with self.assertRaises(candidate_upload_authority.CandidateUploadAuthorityError):
            candidate_upload_authority._token_digest("short")

    def test_finalize_locks_authority_before_terminal_transition(self) -> None:
        source = inspect.getsource(candidate_upload_authority.finalize)
        evidence_at = source.index("finalize_candidate_evidence_upload")
        aggregate_at = source.index("SELECT payload,revision")
        commit_at = source.index("database.commit()")
        self.assertLess(evidence_at, aggregate_at)
        self.assertLess(aggregate_at, commit_at)
        self.assertNotIn("UPDATE recruitment.candidate_upload_capabilities", source)

    def test_issue_uses_security_definer_boundary(self) -> None:
        source = inspect.getsource(candidate_upload_authority.issue)
        self.assertIn("issue_candidate_upload_capability", source)
        self.assertNotIn("INSERT INTO recruitment.candidate_upload_capabilities", source)

    def test_router_validates_bytes_before_postgres_finalize(self) -> None:
        source = ROUTER_SOURCE[ROUTER_SOURCE.index("async def upload_candidate_evidence_with_capability"):]
        validate_at = source.index("_validate_candidate_document_bytes")
        finalize_at = source.index("candidate_upload_authority.finalize")
        legacy_consume_at = source.index("consume_candidate_upload_capability")
        self.assertLess(validate_at, finalize_at)
        self.assertLess(finalize_at, legacy_consume_at)

    def test_production_runtime_has_no_legacy_fallback(self) -> None:
        source = ROUTER_SOURCE[ROUTER_SOURCE.index("def _require_candidate_upload_authority_runtime"):]
        self.assertIn('mode == "postgres"', source)
        self.assertIn('environment != "production" and mode == "legacy-development"', source)

    def test_authority_uses_constant_public_error_for_secret_states(self) -> None:
        self.assertEqual(str(candidate_upload_authority._invalid()),
                         "Aday yükleme yetkisi geçersiz veya süresi dolmuş.")

    def test_ambiguous_commit_never_deletes_authoritative_object(self) -> None:
        source = inspect.getsource(candidate_upload_authority.finalize)
        temp_cleanup_at = source.index("staged_path.unlink")
        commit_marker_at = source.index("commit_started = True")
        commit_at = source.index("database.commit()")
        self.assertLess(temp_cleanup_at, commit_marker_at)
        self.assertLess(commit_marker_at, commit_at)
        self.assertIn("authoritative_path is not None and not commit_started", source)


if __name__ == "__main__":
    unittest.main()
