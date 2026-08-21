from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .regulatory_lineage import RegulatoryLineageStore


@dataclass(frozen=True)
class AtomicObservationResult:
    snapshot_id: str
    snapshot_chain_hash: str
    change_id: str | None
    change_chain_hash: str | None
    observed_at: str


class AtomicRegulatoryPersistence:
    """Persist watcher evidence and provenance in one SQLite transaction.

    The watcher may calculate a diff before entering this component, but it must pass
    the hash it observed as the previous head. The transaction re-checks that head
    under BEGIN IMMEDIATE before writing anything. This prevents a concurrent watcher
    from committing a snapshot/change pair against stale evidence.

    No authority promotion happens here. Authority metadata is stored only as evidence
    and binding-law promotion remains a separate human-gated legal-verification flow.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _latest_snapshot(conn: sqlite3.Connection, source_id: str) -> sqlite3.Row | None:
        return conn.execute(
            """
            SELECT id, content_hash, fetched_at
            FROM regulatory_snapshots
            WHERE source_id = ?
            ORDER BY fetched_at DESC, rowid DESC
            LIMIT 1
            """,
            (source_id,),
        ).fetchone()

    def persist_observation(
        self,
        *,
        source_id: str,
        source_name: str,
        source_url: str,
        source_role: str,
        jurisdiction: str,
        content_hash: str,
        content_text: str,
        expected_previous_hash: str | None,
        diff_excerpt: str | None = None,
        relevance_hits: list[str] | None = None,
        authority_assessment: dict[str, Any] | None = None,
        observed_at: str | None = None,
    ) -> AtomicObservationResult:
        """Commit snapshot and optional relevant-change evidence atomically.

        `authority_assessment` controls whether a change row is created. Baselines and
        irrelevant changes pass None and therefore persist only snapshot + lineage.
        Relevant changes must provide diff/relevance/authority together.
        """
        if not source_id.strip():
            raise ValueError("regulatory_source_id_required")
        if len(content_hash) != 64:
            raise ValueError("regulatory_content_sha256_required")
        has_change = authority_assessment is not None
        if has_change and diff_excerpt is None:
            raise ValueError("regulatory_change_diff_required")
        if has_change and relevance_hits is None:
            raise ValueError("regulatory_change_relevance_required")

        timestamp = observed_at or datetime.now(timezone.utc).isoformat()
        snapshot_id = str(uuid.uuid4())
        change_id = str(uuid.uuid4()) if has_change else None

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            RegulatoryLineageStore.ensure_schema(conn)
            current = self._latest_snapshot(conn, source_id)
            current_hash = current["content_hash"] if current is not None else None
            if current_hash != expected_previous_hash:
                raise ValueError("stale_regulatory_observation_head")

            conn.execute(
                """
                INSERT INTO regulatory_snapshots(
                    id, source_id, content_hash, content_text, fetched_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (snapshot_id, source_id, content_hash, content_text, timestamp),
            )
            snapshot_lineage = RegulatoryLineageStore.append_with_connection(
                conn,
                record_type="snapshot",
                record_id=snapshot_id,
                source_id=source_id,
                content_hash=content_hash,
                metadata={
                    "origin": "regulatory_watcher",
                    "source_role": source_role,
                    "jurisdiction": jurisdiction,
                },
                created_at=timestamp,
            )

            change_chain_hash: str | None = None
            if has_change:
                assert change_id is not None
                assert authority_assessment is not None
                authority_fingerprint = str(
                    authority_assessment.get("assessment_fingerprint") or ""
                )
                if len(authority_fingerprint) != 64:
                    raise ValueError("regulatory_authority_fingerprint_required")
                conn.execute(
                    """
                    INSERT INTO regulatory_changes(
                        id, source_id, source_name, source_url, source_role,
                        old_hash, new_hash, diff_excerpt, relevance_hits_json,
                        status, requires_binding_verification,
                        authority_assessment_json, authority_fingerprint,
                        lineage_chain_hash, detected_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', 1, ?, ?, NULL, ?)
                    """,
                    (
                        change_id,
                        source_id,
                        source_name,
                        source_url,
                        source_role,
                        expected_previous_hash or "",
                        content_hash,
                        diff_excerpt,
                        json.dumps(relevance_hits or [], ensure_ascii=False),
                        json.dumps(
                            authority_assessment,
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                        authority_fingerprint,
                        timestamp,
                    ),
                )
                change_lineage = RegulatoryLineageStore.append_with_connection(
                    conn,
                    record_type="change",
                    record_id=change_id,
                    source_id=source_id,
                    content_hash=content_hash,
                    metadata={
                        "origin": "regulatory_watcher",
                        "old_hash": expected_previous_hash,
                        "source_role": source_role,
                        "relevance_hits": relevance_hits or [],
                        "requires_binding_verification": True,
                        "authority_level": authority_assessment.get("authority_level"),
                        "authority_fingerprint": authority_fingerprint,
                        "snapshot_chain_hash": snapshot_lineage.chain_hash,
                    },
                    created_at=timestamp,
                )
                change_chain_hash = change_lineage.chain_hash
                conn.execute(
                    "UPDATE regulatory_changes SET lineage_chain_hash=? WHERE id=?",
                    (change_chain_hash, change_id),
                )

        return AtomicObservationResult(
            snapshot_id=snapshot_id,
            snapshot_chain_hash=snapshot_lineage.chain_hash,
            change_id=change_id,
            change_chain_hash=change_chain_hash,
            observed_at=timestamp,
        )
