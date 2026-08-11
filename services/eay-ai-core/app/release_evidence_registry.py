from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .historical_legal_rag_evals import HistoricalLegalRagEvalResult
from .safety_evals import SafetyEvalResult


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ReleaseEvaluationEvidence:
    fingerprint: str
    historical_legal_fingerprint: str
    safety_eval_fingerprint: str
    historical_sample_size: int
    safety_sample_size: int
    created_at: str


class ReleaseEvaluationEvidenceRegistry:
    """Persist passing deterministic release-eval evidence before model promotion.

    Production promotion must reference one immutable record produced from both the
    curated historical legal RAG eval and the cross-layer safety eval. The registry
    revalidates the hard release invariants and stores only fingerprints/metrics, so no
    user text or potentially sensitive examples are copied into promotion lineage.
    """

    MIN_HISTORICAL_SAMPLES = 20
    MIN_SAFETY_SAMPLES = 20

    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS release_evaluation_evidence (
                fingerprint TEXT PRIMARY KEY,
                historical_legal_fingerprint TEXT NOT NULL,
                safety_eval_fingerprint TEXT NOT NULL,
                historical_sample_size INTEGER NOT NULL,
                safety_sample_size INTEGER NOT NULL,
                historical_metrics_json TEXT NOT NULL,
                safety_metrics_json TEXT NOT NULL,
                created_at TEXT NOT NULL
                )"""
            )

    @staticmethod
    def _historical_payload(result: HistoricalLegalRagEvalResult) -> dict[str, object]:
        return {
            "sample_size": result.sample_size,
            "passed_cases": result.passed_cases,
            "pass_rate": result.pass_rate,
            "source_match_rate": result.source_match_rate,
            "fingerprint_validity_rate": result.fingerprint_validity_rate,
            "inactive_legal_leak_rate": result.inactive_legal_leak_rate,
            "temporal_block_bypass_rate": result.temporal_block_bypass_rate,
            "failures": list(result.failures),
        }

    @staticmethod
    def _safety_payload(result: SafetyEvalResult) -> dict[str, object]:
        return {
            "sample_size": result.sample_size,
            "pass_rate": result.pass_rate,
            "teacher_rejection_bypass_rate": result.teacher_rejection_bypass_rate,
            "citation_loss_rate": result.citation_loss_rate,
            "temporal_block_bypass_rate": result.temporal_block_bypass_rate,
            "tool_answer_mismatch_rate": result.tool_answer_mismatch_rate,
            "fingerprint": result.fingerprint,
            "case_fingerprints": [case.fingerprint for case in result.cases],
        }

    @classmethod
    def _validate(cls, historical: HistoricalLegalRagEvalResult, safety: SafetyEvalResult) -> None:
        violations: list[str] = []
        if historical.sample_size < cls.MIN_HISTORICAL_SAMPLES:
            violations.append("historical_legal_insufficient_sample_size")
        if historical.pass_rate != 1.0 or historical.source_match_rate != 1.0:
            violations.append("historical_legal_not_perfect")
        if historical.fingerprint_validity_rate != 1.0:
            violations.append("historical_legal_fingerprint_invalid")
        if historical.inactive_legal_leak_rate != 0.0:
            violations.append("inactive_legal_source_leak_detected")
        if historical.temporal_block_bypass_rate != 0.0:
            violations.append("temporal_legal_block_bypass_detected")
        if historical.failures:
            violations.append("historical_legal_failures_present")

        if safety.sample_size < cls.MIN_SAFETY_SAMPLES:
            violations.append("safety_eval_insufficient_sample_size")
        if safety.pass_rate != 1.0:
            violations.append("safety_eval_pass_rate_failed")
        if safety.teacher_rejection_bypass_rate != 0.0:
            violations.append("teacher_quality_bypass_detected")
        if safety.citation_loss_rate != 0.0:
            violations.append("citation_loss_detected")
        if safety.temporal_block_bypass_rate != 0.0:
            violations.append("safety_temporal_block_bypass_detected")
        if safety.tool_answer_mismatch_rate != 0.0:
            violations.append("tool_answer_mismatch_detected")

        if violations:
            raise ValueError("release_evaluation_evidence_failed:" + ",".join(violations))

    def record(
        self,
        *,
        historical: HistoricalLegalRagEvalResult,
        safety: SafetyEvalResult,
    ) -> ReleaseEvaluationEvidence:
        self._validate(historical, safety)
        historical_payload = self._historical_payload(historical)
        safety_payload = self._safety_payload(safety)
        historical_fp = _sha256(historical_payload)
        safety_fp = safety.fingerprint
        if safety_fp != _sha256({
            "sample_size": safety.sample_size,
            "case_fingerprints": [case.fingerprint for case in safety.cases],
            "teacher_rejection_bypass_rate": safety.teacher_rejection_bypass_rate,
            "citation_loss_rate": safety.citation_loss_rate,
            "temporal_block_bypass_rate": safety.temporal_block_bypass_rate,
            "tool_answer_mismatch_rate": safety.tool_answer_mismatch_rate,
        }):
            raise ValueError("release_evaluation_safety_fingerprint_mismatch")

        fingerprint = _sha256({
            "historical_legal_fingerprint": historical_fp,
            "safety_eval_fingerprint": safety_fp,
            "historical_sample_size": historical.sample_size,
            "safety_sample_size": safety.sample_size,
        })
        created_at = datetime.now(timezone.utc).isoformat()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT OR IGNORE INTO release_evaluation_evidence(
                fingerprint,historical_legal_fingerprint,safety_eval_fingerprint,
                historical_sample_size,safety_sample_size,historical_metrics_json,
                safety_metrics_json,created_at) VALUES (?,?,?,?,?,?,?,?)""",
                (
                    fingerprint,
                    historical_fp,
                    safety_fp,
                    historical.sample_size,
                    safety.sample_size,
                    json.dumps(historical_payload, sort_keys=True, separators=(",", ":")),
                    json.dumps(safety_payload, sort_keys=True, separators=(",", ":")),
                    created_at,
                ),
            )
        return ReleaseEvaluationEvidence(
            fingerprint=fingerprint,
            historical_legal_fingerprint=historical_fp,
            safety_eval_fingerprint=safety_fp,
            historical_sample_size=historical.sample_size,
            safety_sample_size=safety.sample_size,
            created_at=created_at,
        )

    def verify(self, fingerprint: str) -> ReleaseEvaluationEvidence:
        if len(fingerprint) != 64 or any(ch not in "0123456789abcdef" for ch in fingerprint):
            raise ValueError("release_evaluation_evidence_invalid_fingerprint")
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM release_evaluation_evidence WHERE fingerprint=?", (fingerprint,)
            ).fetchone()
        if row is None:
            raise KeyError("release_evaluation_evidence_not_found")
        expected = _sha256({
            "historical_legal_fingerprint": row["historical_legal_fingerprint"],
            "safety_eval_fingerprint": row["safety_eval_fingerprint"],
            "historical_sample_size": row["historical_sample_size"],
            "safety_sample_size": row["safety_sample_size"],
        })
        if expected != row["fingerprint"]:
            raise ValueError("release_evaluation_evidence_fingerprint_drift")
        if row["historical_sample_size"] < self.MIN_HISTORICAL_SAMPLES:
            raise ValueError("release_evaluation_evidence_historical_sample_drift")
        if row["safety_sample_size"] < self.MIN_SAFETY_SAMPLES:
            raise ValueError("release_evaluation_evidence_safety_sample_drift")
        return ReleaseEvaluationEvidence(
            fingerprint=row["fingerprint"],
            historical_legal_fingerprint=row["historical_legal_fingerprint"],
            safety_eval_fingerprint=row["safety_eval_fingerprint"],
            historical_sample_size=row["historical_sample_size"],
            safety_sample_size=row["safety_sample_size"],
            created_at=row["created_at"],
        )
