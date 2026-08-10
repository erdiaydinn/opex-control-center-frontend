from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class LegalInteractionAuditRecord:
    interaction_id: str
    as_of: str
    temporal_resolution_fingerprint: str
    active_instrument_ids: tuple[str, ...]
    evidence_ids: tuple[str, ...]
    audit_fingerprint: str
    created_at: str


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _audit_fingerprint(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical(payload).encode("utf-8")).hexdigest()


class LegalInteractionAuditStore:
    """Immutable audit binding a model interaction to one resolved legal timeline."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS legal_interaction_audit (
                    interaction_id TEXT PRIMARY KEY,
                    as_of TEXT NOT NULL,
                    temporal_resolution_fingerprint TEXT NOT NULL,
                    active_instrument_ids_json TEXT NOT NULL,
                    evidence_ids_json TEXT NOT NULL,
                    audit_fingerprint TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                )
                """
            )

    def record(
        self,
        *,
        interaction_id: str,
        as_of: str,
        temporal_resolution_fingerprint: str,
        active_instrument_ids: list[str] | tuple[str, ...],
        evidence_ids: list[str] | tuple[str, ...],
    ) -> LegalInteractionAuditRecord:
        if len(temporal_resolution_fingerprint) != 64:
            raise ValueError("temporal_resolution_fingerprint_required")
        payload = {
            "interaction_id": interaction_id,
            "as_of": as_of,
            "temporal_resolution_fingerprint": temporal_resolution_fingerprint,
            "active_instrument_ids": sorted(set(active_instrument_ids)),
            "evidence_ids": list(evidence_ids),
        }
        digest = _audit_fingerprint(payload)
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT * FROM legal_interaction_audit WHERE interaction_id=?",
                (interaction_id,),
            ).fetchone()
            if existing is not None:
                if existing["audit_fingerprint"] != digest:
                    raise ValueError("immutable_legal_interaction_audit_conflict")
                return self._row(existing)
            conn.execute(
                """
                INSERT INTO legal_interaction_audit(
                    interaction_id, as_of, temporal_resolution_fingerprint,
                    active_instrument_ids_json, evidence_ids_json,
                    audit_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id,
                    as_of,
                    temporal_resolution_fingerprint,
                    _canonical({"items": payload["active_instrument_ids"]}),
                    _canonical({"items": payload["evidence_ids"]}),
                    digest,
                    now,
                ),
            )
            row = conn.execute(
                "SELECT * FROM legal_interaction_audit WHERE interaction_id=?",
                (interaction_id,),
            ).fetchone()
        assert row is not None
        return self._row(row)

    def get(self, interaction_id: str) -> LegalInteractionAuditRecord | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM legal_interaction_audit WHERE interaction_id=?",
                (interaction_id,),
            ).fetchone()
        return self._row(row) if row is not None else None

    @staticmethod
    def _row(row: sqlite3.Row) -> LegalInteractionAuditRecord:
        return LegalInteractionAuditRecord(
            interaction_id=row["interaction_id"],
            as_of=row["as_of"],
            temporal_resolution_fingerprint=row["temporal_resolution_fingerprint"],
            active_instrument_ids=tuple(json.loads(row["active_instrument_ids_json"])["items"]),
            evidence_ids=tuple(json.loads(row["evidence_ids_json"])["items"]),
            audit_fingerprint=row["audit_fingerprint"],
            created_at=row["created_at"],
        )
