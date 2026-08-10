from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

RelationType = Literal["amends", "repeals", "supersedes"]
RelationStatus = Literal["pending", "approved", "rejected"]


@dataclass(frozen=True)
class LegalRelationRecord:
    id: str
    source_instrument_id: str
    relation_type: RelationType
    target_instrument_id: str
    status: RelationStatus
    evidence_ref: str
    relation_fingerprint: str
    reviewer_ref: str | None
    created_at: str
    decided_at: str | None


def _fingerprint(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class LegalRelationStore:
    """Human-gated amendment/repeal/supersession relationships.

    Approval records the verified relationship only. It intentionally does not mutate
    effective dates or instrument verification status; those remain separate legal
    review decisions.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def ensure_schema(conn: sqlite3.Connection) -> None:
        # Do not use executescript here: callers may already hold BEGIN IMMEDIATE and
        # sqlite3.executescript can implicitly commit before running the script.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_instrument_relations (
                id TEXT PRIMARY KEY,
                source_instrument_id TEXT NOT NULL,
                relation_type TEXT NOT NULL,
                target_instrument_id TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                evidence_ref TEXT NOT NULL,
                relation_fingerprint TEXT NOT NULL,
                reviewer_ref TEXT,
                created_at TEXT NOT NULL,
                decided_at TEXT,
                UNIQUE(source_instrument_id, relation_type, target_instrument_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_legal_relations_status
            ON legal_instrument_relations(status, created_at DESC)
            """
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            self.ensure_schema(conn)

    @staticmethod
    def _row(row: sqlite3.Row) -> LegalRelationRecord:
        return LegalRelationRecord(
            id=row["id"],
            source_instrument_id=row["source_instrument_id"],
            relation_type=row["relation_type"],
            target_instrument_id=row["target_instrument_id"],
            status=row["status"],
            evidence_ref=row["evidence_ref"],
            relation_fingerprint=row["relation_fingerprint"],
            reviewer_ref=row["reviewer_ref"],
            created_at=row["created_at"],
            decided_at=row["decided_at"],
        )

    @classmethod
    def propose_with_connection(
        cls,
        conn: sqlite3.Connection,
        *,
        source_instrument_id: str,
        relation_type: RelationType,
        target_instrument_id: str,
        evidence_ref: str,
        created_at: str | None = None,
    ) -> LegalRelationRecord:
        """Create an immutable pending relation using the caller's transaction."""
        cls.ensure_schema(conn)
        if source_instrument_id == target_instrument_id:
            raise ValueError("legal_relation_self_reference_forbidden")
        if not evidence_ref.strip():
            raise ValueError("legal_relation_evidence_required")

        source = conn.execute(
            "SELECT id, verification_status FROM legal_instruments WHERE id = ?",
            (source_instrument_id,),
        ).fetchone()
        target = conn.execute(
            "SELECT id, verification_status FROM legal_instruments WHERE id = ?",
            (target_instrument_id,),
        ).fetchone()
        if source is None:
            raise KeyError("source_instrument_not_found")
        if target is None:
            raise KeyError("target_instrument_not_found")
        if target["verification_status"] == "draft":
            raise ValueError("legal_relation_target_must_not_be_draft")

        payload = {
            "source_instrument_id": source_instrument_id,
            "relation_type": relation_type,
            "target_instrument_id": target_instrument_id,
            "evidence_ref": evidence_ref,
        }
        digest = _fingerprint(payload)
        existing = conn.execute(
            """
            SELECT * FROM legal_instrument_relations
            WHERE source_instrument_id=? AND relation_type=? AND target_instrument_id=?
            """,
            (source_instrument_id, relation_type, target_instrument_id),
        ).fetchone()
        if existing is not None:
            if existing["relation_fingerprint"] != digest:
                raise ValueError("immutable_legal_relation_conflict")
            return cls._row(existing)

        record_id = str(uuid.uuid4())
        now = created_at or datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO legal_instrument_relations(
                id, source_instrument_id, relation_type, target_instrument_id,
                status, evidence_ref, relation_fingerprint, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, ?, ?)
            """,
            (
                record_id,
                source_instrument_id,
                relation_type,
                target_instrument_id,
                evidence_ref,
                digest,
                now,
            ),
        )
        row = conn.execute(
            "SELECT * FROM legal_instrument_relations WHERE id = ?",
            (record_id,),
        ).fetchone()
        assert row is not None
        return cls._row(row)

    def propose(
        self,
        *,
        source_instrument_id: str,
        relation_type: RelationType,
        target_instrument_id: str,
        evidence_ref: str,
    ) -> LegalRelationRecord:
        with self._connect() as conn:
            return self.propose_with_connection(
                conn,
                source_instrument_id=source_instrument_id,
                relation_type=relation_type,
                target_instrument_id=target_instrument_id,
                evidence_ref=evidence_ref,
            )

    def decide(
        self,
        record_id: str,
        *,
        decision: Literal["approved", "rejected"],
        reviewer_ref: str,
    ) -> LegalRelationRecord:
        if not reviewer_ref.strip():
            raise ValueError("legal_relation_reviewer_required")
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                "SELECT * FROM legal_instrument_relations WHERE id = ?",
                (record_id,),
            ).fetchone()
            if row is None:
                raise KeyError("legal_relation_not_found")
            if row["status"] != "pending":
                raise ValueError("legal_relation_not_pending")
            if decision == "approved":
                source = conn.execute(
                    "SELECT verification_status FROM legal_instruments WHERE id = ?",
                    (row["source_instrument_id"],),
                ).fetchone()
                target = conn.execute(
                    "SELECT verification_status FROM legal_instruments WHERE id = ?",
                    (row["target_instrument_id"],),
                ).fetchone()
                if source is None or source["verification_status"] != "verified":
                    raise ValueError("verified_source_instrument_required_for_relation_approval")
                if target is None or target["verification_status"] == "draft":
                    raise ValueError("non_draft_target_instrument_required_for_relation_approval")
            conn.execute(
                """
                UPDATE legal_instrument_relations
                SET status=?, reviewer_ref=?, decided_at=?
                WHERE id=?
                """,
                (decision, reviewer_ref, now, record_id),
            )
            row = conn.execute(
                "SELECT * FROM legal_instrument_relations WHERE id = ?",
                (record_id,),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def approved_targets(self, source_instrument_id: str) -> list[LegalRelationRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM legal_instrument_relations
                WHERE source_instrument_id=? AND status='approved'
                ORDER BY created_at ASC, id ASC
                """,
                (source_instrument_id,),
            ).fetchall()
        return [self._row(row) for row in rows]
