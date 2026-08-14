from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RegulatoryLineageRecord:
    record_type: str
    record_id: str
    source_id: str
    content_hash: str
    parent_chain_hash: str | None
    metadata: dict[str, Any]
    chain_hash: str
    created_at: str


def _canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _chain_hash(
    *,
    record_type: str,
    record_id: str,
    source_id: str,
    content_hash: str,
    parent_chain_hash: str | None,
    metadata: dict[str, Any],
) -> str:
    payload = {
        "record_type": record_type,
        "record_id": record_id,
        "source_id": source_id,
        "content_hash": content_hash,
        "parent_chain_hash": parent_chain_hash,
        "metadata": metadata,
    }
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


class RegulatoryLineageStore:
    """Append-only provenance chain for regulatory watcher evidence.

    This store never changes the authority of an item. It only makes watcher evidence
    tamper-evident and auditable. Legal promotion remains a separate human-gated flow.
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
        # Keep this safe for callers that already own an explicit transaction.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS regulatory_evidence_lineage (
                record_type TEXT NOT NULL,
                record_id TEXT NOT NULL,
                source_id TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                parent_chain_hash TEXT,
                metadata_json TEXT NOT NULL,
                chain_hash TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL,
                PRIMARY KEY(record_type, record_id)
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_regulatory_lineage_source_time
            ON regulatory_evidence_lineage(source_id, created_at ASC)
            """
        )

    def _init_db(self) -> None:
        with self._connect() as conn:
            self.ensure_schema(conn)

    @classmethod
    def _latest_with_connection(
        cls, conn: sqlite3.Connection, source_id: str
    ) -> RegulatoryLineageRecord | None:
        cls.ensure_schema(conn)
        row = conn.execute(
            """
            SELECT * FROM regulatory_evidence_lineage
            WHERE source_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()
        return cls._row_to_record(row) if row else None

    def latest_for_source(self, source_id: str) -> RegulatoryLineageRecord | None:
        with self._connect() as conn:
            return self._latest_with_connection(conn, source_id)

    @classmethod
    def _get_with_connection(
        cls, conn: sqlite3.Connection, record_type: str, record_id: str
    ) -> RegulatoryLineageRecord | None:
        cls.ensure_schema(conn)
        row = conn.execute(
            "SELECT * FROM regulatory_evidence_lineage WHERE record_type = ? AND record_id = ?",
            (record_type, record_id),
        ).fetchone()
        return cls._row_to_record(row) if row else None

    def get(self, record_type: str, record_id: str) -> RegulatoryLineageRecord | None:
        with self._connect() as conn:
            return self._get_with_connection(conn, record_type, record_id)

    @classmethod
    def append_with_connection(
        cls,
        conn: sqlite3.Connection,
        *,
        record_type: str,
        record_id: str,
        source_id: str,
        content_hash: str,
        metadata: dict[str, Any],
        created_at: str | None = None,
    ) -> RegulatoryLineageRecord:
        """Append evidence using the caller's transaction without implicit commits."""
        existing = cls._get_with_connection(conn, record_type, record_id)
        if existing is not None:
            expected_metadata = json.loads(_canonical_json(metadata))
            if (
                existing.source_id != source_id
                or existing.content_hash != content_hash
                or existing.metadata != expected_metadata
            ):
                raise ValueError("immutable_regulatory_lineage_conflict")
            return existing

        parent = cls._latest_with_connection(conn, source_id)
        parent_hash = parent.chain_hash if parent else None
        normalized_metadata = json.loads(_canonical_json(metadata))
        digest = _chain_hash(
            record_type=record_type,
            record_id=record_id,
            source_id=source_id,
            content_hash=content_hash,
            parent_chain_hash=parent_hash,
            metadata=normalized_metadata,
        )
        timestamp = created_at or datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO regulatory_evidence_lineage(
                record_type, record_id, source_id, content_hash,
                parent_chain_hash, metadata_json, chain_hash, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_type,
                record_id,
                source_id,
                content_hash,
                parent_hash,
                _canonical_json(normalized_metadata),
                digest,
                timestamp,
            ),
        )
        return RegulatoryLineageRecord(
            record_type=record_type,
            record_id=record_id,
            source_id=source_id,
            content_hash=content_hash,
            parent_chain_hash=parent_hash,
            metadata=normalized_metadata,
            chain_hash=digest,
            created_at=timestamp,
        )

    def append(
        self,
        *,
        record_type: str,
        record_id: str,
        source_id: str,
        content_hash: str,
        metadata: dict[str, Any],
        created_at: str | None = None,
    ) -> RegulatoryLineageRecord:
        with self._connect() as conn:
            return self.append_with_connection(
                conn,
                record_type=record_type,
                record_id=record_id,
                source_id=source_id,
                content_hash=content_hash,
                metadata=metadata,
                created_at=created_at,
            )

    def verify_source_chain(self, source_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM regulatory_evidence_lineage
                WHERE source_id = ?
                ORDER BY created_at ASC, rowid ASC
                """,
                (source_id,),
            ).fetchall()

        previous: str | None = None
        for index, row in enumerate(rows):
            metadata = json.loads(row["metadata_json"])
            expected = _chain_hash(
                record_type=row["record_type"],
                record_id=row["record_id"],
                source_id=row["source_id"],
                content_hash=row["content_hash"],
                parent_chain_hash=previous,
                metadata=metadata,
            )
            if row["parent_chain_hash"] != previous or row["chain_hash"] != expected:
                return {
                    "verified": False,
                    "source_id": source_id,
                    "record_count": len(rows),
                    "broken_at_index": index,
                    "broken_record_id": row["record_id"],
                }
            previous = row["chain_hash"]
        return {
            "verified": True,
            "source_id": source_id,
            "record_count": len(rows),
            "head_chain_hash": previous,
        }

    def import_existing_watcher_rows(self) -> dict[str, int]:
        """Idempotently backfill the chain from the current watcher tables.

        Import order is deterministic per source. Existing records are immutable and
        re-running the import does not create duplicates.
        """
        imported_snapshots = 0
        imported_changes = 0
        with self._connect() as conn:
            tables = {
                row[0]
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            snapshots = []
            changes = []
            if "regulatory_snapshots" in tables:
                snapshots = conn.execute(
                    """
                    SELECT id, source_id, content_hash, fetched_at
                    FROM regulatory_snapshots
                    ORDER BY source_id ASC, fetched_at ASC, id ASC
                    """
                ).fetchall()
            if "regulatory_changes" in tables:
                changes = conn.execute(
                    """
                    SELECT id, source_id, old_hash, new_hash, source_role,
                           requires_binding_verification, detected_at
                    FROM regulatory_changes
                    ORDER BY source_id ASC, detected_at ASC, id ASC
                    """
                ).fetchall()

        events: list[tuple[str, str, str, str, dict[str, Any], str]] = []
        for row in snapshots:
            events.append((
                row["source_id"], row["fetched_at"], "snapshot", row["id"], row["content_hash"],
                {"origin": "regulatory_snapshots"},
            ))
        for row in changes:
            events.append((
                row["source_id"], row["detected_at"], "change", row["id"], row["new_hash"],
                {
                    "origin": "regulatory_changes",
                    "old_hash": row["old_hash"],
                    "source_role": row["source_role"],
                    "requires_binding_verification": bool(row["requires_binding_verification"]),
                },
            ))

        for source_id, timestamp, record_type, record_id, content_hash, metadata in sorted(events):
            existed = self.get(record_type, record_id) is not None
            self.append(
                record_type=record_type,
                record_id=record_id,
                source_id=source_id,
                content_hash=content_hash,
                metadata=metadata,
                created_at=timestamp,
            )
            if not existed:
                if record_type == "snapshot":
                    imported_snapshots += 1
                else:
                    imported_changes += 1
        return {"snapshots": imported_snapshots, "changes": imported_changes}

    @staticmethod
    def _row_to_record(row: sqlite3.Row) -> RegulatoryLineageRecord:
        return RegulatoryLineageRecord(
            record_type=row["record_type"],
            record_id=row["record_id"],
            source_id=row["source_id"],
            content_hash=row["content_hash"],
            parent_chain_hash=row["parent_chain_hash"],
            metadata=json.loads(row["metadata_json"]),
            chain_hash=row["chain_hash"],
            created_at=row["created_at"],
        )
