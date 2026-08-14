from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


def _sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


LifecycleAction = Literal["retire", "rollback_authorized"]


class RetirementRequest(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    release_proof_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=2, max_length=180)
    approval_reference: str = Field(min_length=2, max_length=300)
    reason: str = Field(min_length=3, max_length=1000)


class RollbackAuthorizationRequest(RetirementRequest):
    target_model_record_id: str = Field(min_length=1, max_length=180)
    target_release_proof_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class LifecycleRecord(BaseModel):
    id: str
    fingerprint: str
    previous_fingerprint: str | None
    sequence_no: int
    action: LifecycleAction
    model_record_id: str
    source_release_proof_fingerprint: str
    target_model_record_id: str | None = None
    target_release_proof_fingerprint: str | None = None
    approved_by: str
    approval_reference: str
    reason: str
    created_at: datetime


@dataclass(frozen=True)
class LifecycleVerificationResult:
    record_count: int
    head_fingerprint: str | None
    verified_release_proofs: int
    passed: bool = True


class ModelLifecycleLedger:
    """Append-only retirement/rollback audit bound to immutable release proofs.

    A rollback authorization deliberately does *not* reactivate an older model. It retires
    the current production record and binds the human rollback decision to both source and
    target release proofs. Re-activation of the target still requires the normal fresh
    promotion/eval/canary process, preventing an old release proof from becoming a bypass.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_lifecycle_ledger (
                id TEXT PRIMARY KEY,
                fingerprint TEXT NOT NULL UNIQUE,
                previous_fingerprint TEXT,
                sequence_no INTEGER NOT NULL UNIQUE,
                action TEXT NOT NULL,
                model_record_id TEXT NOT NULL,
                source_release_proof_fingerprint TEXT NOT NULL,
                target_model_record_id TEXT,
                target_release_proof_fingerprint TEXT,
                approved_by TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT NOT NULL)"""
            )

    @staticmethod
    def _load_promotion(conn: sqlite3.Connection, model_record_id: str, release_proof: str):
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """SELECT * FROM model_production_promotions
            WHERE model_record_id=? AND release_proof_fingerprint=?""",
            (model_record_id, release_proof),
        ).fetchone()
        if row is None:
            raise KeyError("production_release_proof_not_found")
        return row

    @staticmethod
    def _load_model(conn: sqlite3.Connection, model_record_id: str):
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM model_registry WHERE id=?", (model_record_id,)).fetchone()
        if row is None:
            raise KeyError("model_not_found")
        return row

    @staticmethod
    def _head(conn: sqlite3.Connection) -> tuple[int, str | None]:
        row = conn.execute(
            "SELECT sequence_no, fingerprint FROM model_lifecycle_ledger ORDER BY sequence_no DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return 0, None
        return int(row[0]), str(row[1])

    @staticmethod
    def _canonical_row(row: sqlite3.Row) -> dict[str, object]:
        return {
            "sequence_no": int(row["sequence_no"]),
            "previous_fingerprint": row["previous_fingerprint"],
            "action": row["action"],
            "model_record_id": row["model_record_id"],
            "source_release_proof_fingerprint": row["source_release_proof_fingerprint"],
            "target_model_record_id": row["target_model_record_id"],
            "target_release_proof_fingerprint": row["target_release_proof_fingerprint"],
            "approved_by": str(row["approved_by"]).strip(),
            "approval_reference": str(row["approval_reference"]).strip(),
            "reason": str(row["reason"]).strip(),
        }

    def verify_chain(self) -> LifecycleVerificationResult:
        """Replay the append-only ledger and fail closed on tampering or broken release lineage."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM model_lifecycle_ledger ORDER BY sequence_no ASC"
            ).fetchall()
            previous: str | None = None
            expected_sequence = 1
            release_proofs = 0
            for row in rows:
                if int(row["sequence_no"]) != expected_sequence:
                    raise ValueError("model_lifecycle_sequence_gap")
                if row["previous_fingerprint"] != previous:
                    raise ValueError("model_lifecycle_previous_fingerprint_mismatch")
                expected = _sha256(self._canonical_row(row))
                if row["fingerprint"] != expected:
                    raise ValueError("model_lifecycle_fingerprint_mismatch")
                if row["action"] not in {"retire", "rollback_authorized"}:
                    raise ValueError("model_lifecycle_unknown_action")
                self._load_promotion(
                    conn,
                    str(row["model_record_id"]),
                    str(row["source_release_proof_fingerprint"]),
                )
                release_proofs += 1
                if row["action"] == "rollback_authorized":
                    if not row["target_model_record_id"] or not row["target_release_proof_fingerprint"]:
                        raise ValueError("model_lifecycle_rollback_target_missing")
                    self._load_promotion(
                        conn,
                        str(row["target_model_record_id"]),
                        str(row["target_release_proof_fingerprint"]),
                    )
                    release_proofs += 1
                elif row["target_model_record_id"] or row["target_release_proof_fingerprint"]:
                    raise ValueError("model_lifecycle_unexpected_target")
                previous = str(row["fingerprint"])
                expected_sequence += 1

        return LifecycleVerificationResult(
            record_count=len(rows),
            head_fingerprint=previous,
            verified_release_proofs=release_proofs,
        )

    def _record(
        self,
        *,
        action: LifecycleAction,
        model_record_id: str,
        source_release_proof_fingerprint: str,
        approved_by: str,
        approval_reference: str,
        reason: str,
        target_model_record_id: str | None = None,
        target_release_proof_fingerprint: str | None = None,
    ) -> LifecycleRecord:
        created_at = datetime.now(timezone.utc)
        record_id = str(uuid.uuid4())
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                source_model = self._load_model(conn, model_record_id)
                self._load_promotion(conn, model_record_id, source_release_proof_fingerprint)
                if source_model["status"] != "production":
                    raise ValueError("model_lifecycle_requires_current_production_status")

                if action == "rollback_authorized":
                    if not target_model_record_id or not target_release_proof_fingerprint:
                        raise ValueError("rollback_target_required")
                    if target_model_record_id == model_record_id:
                        raise ValueError("rollback_target_must_differ_from_source")
                    self._load_model(conn, target_model_record_id)
                    self._load_promotion(conn, target_model_record_id, target_release_proof_fingerprint)

                sequence_no, previous_fingerprint = self._head(conn)
                sequence_no += 1
                canonical = {
                    "sequence_no": sequence_no,
                    "previous_fingerprint": previous_fingerprint,
                    "action": action,
                    "model_record_id": model_record_id,
                    "source_release_proof_fingerprint": source_release_proof_fingerprint,
                    "target_model_record_id": target_model_record_id,
                    "target_release_proof_fingerprint": target_release_proof_fingerprint,
                    "approved_by": approved_by.strip(),
                    "approval_reference": approval_reference.strip(),
                    "reason": reason.strip(),
                }
                fingerprint = _sha256(canonical)

                updated = conn.execute(
                    "UPDATE model_registry SET status='retired' WHERE id=? AND status='production'",
                    (model_record_id,),
                )
                if updated.rowcount != 1:
                    raise ValueError("model_lifecycle_stale_production_state")

                conn.execute(
                    """INSERT INTO model_lifecycle_ledger(
                    id,fingerprint,previous_fingerprint,sequence_no,action,model_record_id,
                    source_release_proof_fingerprint,target_model_record_id,
                    target_release_proof_fingerprint,approved_by,approval_reference,reason,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record_id, fingerprint, previous_fingerprint, sequence_no, action,
                        model_record_id, source_release_proof_fingerprint, target_model_record_id,
                        target_release_proof_fingerprint, approved_by.strip(),
                        approval_reference.strip(), reason.strip(), created_at.isoformat(),
                    ),
                )
            except Exception:
                conn.rollback()
                raise

        return LifecycleRecord(
            id=record_id,
            fingerprint=fingerprint,
            previous_fingerprint=previous_fingerprint,
            sequence_no=sequence_no,
            action=action,
            model_record_id=model_record_id,
            source_release_proof_fingerprint=source_release_proof_fingerprint,
            target_model_record_id=target_model_record_id,
            target_release_proof_fingerprint=target_release_proof_fingerprint,
            approved_by=approved_by.strip(),
            approval_reference=approval_reference.strip(),
            reason=reason.strip(),
            created_at=created_at,
        )

    def retire(self, payload: RetirementRequest) -> LifecycleRecord:
        return self._record(
            action="retire",
            model_record_id=payload.model_record_id,
            source_release_proof_fingerprint=payload.release_proof_fingerprint,
            approved_by=payload.approved_by,
            approval_reference=payload.approval_reference,
            reason=payload.reason,
        )

    def authorize_rollback(self, payload: RollbackAuthorizationRequest) -> LifecycleRecord:
        return self._record(
            action="rollback_authorized",
            model_record_id=payload.model_record_id,
            source_release_proof_fingerprint=payload.release_proof_fingerprint,
            target_model_record_id=payload.target_model_record_id,
            target_release_proof_fingerprint=payload.target_release_proof_fingerprint,
            approved_by=payload.approved_by,
            approval_reference=payload.approval_reference,
            reason=payload.reason,
        )
