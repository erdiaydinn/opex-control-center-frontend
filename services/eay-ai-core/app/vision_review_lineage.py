from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VisionReviewDecision:
    audit_id: str
    decision: str
    evidence_chain_sha256: str
    retention_fingerprint: str
    reviewer: str
    approval_reference: str
    decided_at: str
    reviewer_note_sha256: str | None
    fingerprint: str


class VisionReviewDecisionStore:
    """Seal an accepted/rejected human review against exact vision evidence lineage.

    Learning eligibility must never rely only on a mutable decision flag. This store
    binds the human identity/reference, decision timestamp, reviewer note hash, exact
    evidence chain and retention policy fingerprint into one immutable decision hash.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS vision_review_decisions (
                audit_id TEXT PRIMARY KEY,
                decision TEXT NOT NULL,
                evidence_chain_sha256 TEXT NOT NULL,
                retention_fingerprint TEXT NOT NULL,
                reviewer TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                decided_at TEXT NOT NULL,
                reviewer_note_sha256 TEXT,
                fingerprint TEXT NOT NULL UNIQUE,
                sealed_at TEXT NOT NULL
                )"""
            )

    def seal(self, audit_id: str, *, reviewer: str, approval_reference: str) -> VisionReviewDecision:
        reviewer = reviewer.strip()
        approval_reference = approval_reference.strip()
        if len(reviewer) < 2:
            raise ValueError("vision_review_reviewer_required")
        if len(approval_reference) < 2:
            raise ValueError("vision_review_approval_reference_required")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            audit = conn.execute("SELECT * FROM vision_audits WHERE id=?", (audit_id,)).fetchone()
            if audit is None:
                raise KeyError("audit_not_found")
            if audit["decision"] not in {"accepted", "rejected"} or not audit["decided_at"]:
                raise ValueError("vision_review_decision_not_final")
            provenance = conn.execute(
                "SELECT evidence_chain_sha256 FROM vision_evidence_provenance WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            if provenance is None:
                raise ValueError("vision_review_provenance_required")
            retention = conn.execute(
                "SELECT fingerprint,evidence_chain_sha256 FROM vision_evidence_retention WHERE audit_id=?",
                (audit_id,),
            ).fetchone()
            if retention is None:
                raise ValueError("vision_review_retention_required")
            if retention["evidence_chain_sha256"] != provenance["evidence_chain_sha256"]:
                raise ValueError("vision_review_evidence_chain_drift")

            note = (audit["reviewer_note"] or "").strip()
            note_sha256 = hashlib.sha256(note.encode("utf-8")).hexdigest() if note else None
            payload = {
                "audit_id": audit_id,
                "decision": audit["decision"],
                "evidence_chain_sha256": provenance["evidence_chain_sha256"],
                "retention_fingerprint": retention["fingerprint"],
                "reviewer": reviewer,
                "approval_reference": approval_reference,
                "decided_at": audit["decided_at"],
                "reviewer_note_sha256": note_sha256,
            }
            fingerprint = _sha256(payload)
            sealed_at = datetime.now(timezone.utc).isoformat()
            try:
                conn.execute(
                    """INSERT INTO vision_review_decisions(
                    audit_id,decision,evidence_chain_sha256,retention_fingerprint,
                    reviewer,approval_reference,decided_at,reviewer_note_sha256,fingerprint,sealed_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                    (
                        audit_id, audit["decision"], provenance["evidence_chain_sha256"],
                        retention["fingerprint"], reviewer, approval_reference,
                        audit["decided_at"], note_sha256, fingerprint, sealed_at,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("vision_review_decision_already_sealed") from exc
        return self.verify(audit_id)

    def verify(self, audit_id: str) -> VisionReviewDecision:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM vision_review_decisions WHERE audit_id=?", (audit_id,)).fetchone()
            if row is None:
                raise KeyError("vision_review_decision_not_found")
            audit = conn.execute("SELECT * FROM vision_audits WHERE id=?", (audit_id,)).fetchone()
            provenance = conn.execute(
                "SELECT evidence_chain_sha256 FROM vision_evidence_provenance WHERE audit_id=?", (audit_id,)
            ).fetchone()
            retention = conn.execute(
                "SELECT fingerprint,evidence_chain_sha256 FROM vision_evidence_retention WHERE audit_id=?", (audit_id,)
            ).fetchone()
        if audit is None or provenance is None or retention is None:
            raise ValueError("vision_review_lineage_missing")
        note = (audit["reviewer_note"] or "").strip()
        note_sha256 = hashlib.sha256(note.encode("utf-8")).hexdigest() if note else None
        if audit["decision"] != row["decision"] or audit["decided_at"] != row["decided_at"]:
            raise ValueError("vision_review_audit_decision_drift")
        if provenance["evidence_chain_sha256"] != row["evidence_chain_sha256"]:
            raise ValueError("vision_review_provenance_drift")
        if retention["fingerprint"] != row["retention_fingerprint"]:
            raise ValueError("vision_review_retention_drift")
        if retention["evidence_chain_sha256"] != row["evidence_chain_sha256"]:
            raise ValueError("vision_review_retention_evidence_drift")
        if note_sha256 != row["reviewer_note_sha256"]:
            raise ValueError("vision_review_note_drift")
        expected = _sha256({
            "audit_id": row["audit_id"],
            "decision": row["decision"],
            "evidence_chain_sha256": row["evidence_chain_sha256"],
            "retention_fingerprint": row["retention_fingerprint"],
            "reviewer": row["reviewer"],
            "approval_reference": row["approval_reference"],
            "decided_at": row["decided_at"],
            "reviewer_note_sha256": row["reviewer_note_sha256"],
        })
        if expected != row["fingerprint"]:
            raise ValueError("vision_review_fingerprint_drift")
        return VisionReviewDecision(
            audit_id=row["audit_id"], decision=row["decision"],
            evidence_chain_sha256=row["evidence_chain_sha256"],
            retention_fingerprint=row["retention_fingerprint"], reviewer=row["reviewer"],
            approval_reference=row["approval_reference"], decided_at=row["decided_at"],
            reviewer_note_sha256=row["reviewer_note_sha256"], fingerprint=row["fingerprint"],
        )
