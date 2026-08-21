from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class VisionRetentionRecord:
    audit_id: str
    evidence_chain_sha256: str
    policy_id: str
    retain_until: str
    state: str
    tombstone_fingerprint: str | None
    fingerprint: str


class VisionRetentionStore:
    """Append-preserving retention state for visual evidence.

    Raw/source evidence may be retired for privacy or retention reasons, but the system
    never deletes the provenance identity silently. A tombstone preserves the exact
    evidence-chain hash and policy lineage while making the audit ineligible for learning.
    """

    DEFAULT_RETENTION_DAYS = 365

    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS vision_evidence_retention (
                audit_id TEXT PRIMARY KEY,
                evidence_chain_sha256 TEXT NOT NULL,
                policy_id TEXT NOT NULL,
                retain_until TEXT NOT NULL,
                state TEXT NOT NULL,
                tombstone_reason TEXT,
                tombstoned_at TEXT,
                tombstone_fingerprint TEXT,
                fingerprint TEXT NOT NULL
                )"""
            )

    def ensure_policy(
        self,
        *,
        audit_id: str,
        evidence_chain_sha256: str,
        created_at: datetime | None = None,
        retention_days: int = DEFAULT_RETENTION_DAYS,
        policy_id: str = "vision-evidence-v1",
    ) -> VisionRetentionRecord:
        if retention_days < 1 or retention_days > 3650:
            raise ValueError("vision_retention_days_out_of_range")
        created = created_at or datetime.now(timezone.utc)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        retain_until = created + timedelta(days=retention_days)
        fingerprint = _sha256({
            "audit_id": audit_id,
            "evidence_chain_sha256": evidence_chain_sha256,
            "policy_id": policy_id,
            "retain_until": retain_until.isoformat(),
        })
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO vision_evidence_retention(
                    audit_id,evidence_chain_sha256,policy_id,retain_until,state,fingerprint
                    ) VALUES (?,?,?,?,?,?)""",
                    (audit_id, evidence_chain_sha256, policy_id, retain_until.isoformat(), "active", fingerprint),
                )
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT evidence_chain_sha256 FROM vision_evidence_retention WHERE audit_id=?",
                    (audit_id,),
                ).fetchone()
                if row is None or row[0] != evidence_chain_sha256:
                    raise ValueError("vision_retention_evidence_chain_drift")
        return self.get(audit_id)

    def tombstone(self, audit_id: str, *, reason: str, tombstoned_at: datetime | None = None) -> VisionRetentionRecord:
        reason = reason.strip()
        if len(reason) < 3:
            raise ValueError("vision_tombstone_reason_required")
        now = tombstoned_at or datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM vision_evidence_retention WHERE audit_id=?", (audit_id,)).fetchone()
            if row is None:
                raise KeyError("vision_retention_not_found")
            if row["state"] == "tombstoned":
                raise ValueError("vision_evidence_already_tombstoned")
            tombstone_fp = _sha256({
                "audit_id": audit_id,
                "evidence_chain_sha256": row["evidence_chain_sha256"],
                "policy_fingerprint": row["fingerprint"],
                "reason": reason,
                "tombstoned_at": now.isoformat(),
            })
            conn.execute(
                """UPDATE vision_evidence_retention
                SET state='tombstoned',tombstone_reason=?,tombstoned_at=?,tombstone_fingerprint=?
                WHERE audit_id=?""",
                (reason, now.isoformat(), tombstone_fp, audit_id),
            )
        return self.get(audit_id)

    def is_active(self, audit_id: str, *, as_of: datetime | None = None) -> bool:
        record = self.get(audit_id)
        if record.state != "active":
            return False
        now = as_of or datetime.now(timezone.utc)
        retain_until = datetime.fromisoformat(record.retain_until)
        return now <= retain_until

    def get(self, audit_id: str) -> VisionRetentionRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM vision_evidence_retention WHERE audit_id=?", (audit_id,)).fetchone()
        if row is None:
            raise KeyError("vision_retention_not_found")
        expected = _sha256({
            "audit_id": row["audit_id"],
            "evidence_chain_sha256": row["evidence_chain_sha256"],
            "policy_id": row["policy_id"],
            "retain_until": row["retain_until"],
        })
        if expected != row["fingerprint"]:
            raise ValueError("vision_retention_fingerprint_drift")
        return VisionRetentionRecord(
            audit_id=row["audit_id"],
            evidence_chain_sha256=row["evidence_chain_sha256"],
            policy_id=row["policy_id"],
            retain_until=row["retain_until"],
            state=row["state"],
            tombstone_fingerprint=row["tombstone_fingerprint"],
            fingerprint=row["fingerprint"],
        )
