from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))


class LegalKnowledgeChunk(BaseModel):
    id: str
    instrument_id: str
    verification_id: str
    ordinal: int
    heading: str | None = None
    content_sha256: str
    chunk_sha256: str
    source_url: str
    publication_date: date
    effective_from: date
    effective_to: date | None = None
    text: str


class LegalKnowledgeIndexer:
    """Indexes only already-verified legal text into the shared RAG store.

    The authoritative full-text SHA remains the provenance root. Chunks are
    deterministic and idempotent, so re-indexing the same verification cannot
    silently create a different legal corpus.
    """

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
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS legal_knowledge_chunks (
                    id TEXT PRIMARY KEY,
                    instrument_id TEXT NOT NULL,
                    verification_id TEXT NOT NULL,
                    ordinal INTEGER NOT NULL,
                    heading TEXT,
                    content_sha256 TEXT NOT NULL,
                    chunk_sha256 TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    publication_date TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    effective_to TEXT,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(verification_id, ordinal)
                );

                CREATE INDEX IF NOT EXISTS idx_legal_knowledge_instrument
                ON legal_knowledge_chunks(instrument_id, ordinal);

                CREATE INDEX IF NOT EXISTS idx_legal_knowledge_effective
                ON legal_knowledge_chunks(effective_from, effective_to);
                """
            )

    @staticmethod
    def _normalize(text: str) -> str:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    @classmethod
    def _chunks(cls, text: str, target_chars: int = 1800) -> list[tuple[str | None, str]]:
        normalized = cls._normalize(text)
        blocks = [block.strip() for block in re.split(r"\n\s*\n", normalized) if block.strip()]
        if not blocks:
            return []

        output: list[tuple[str | None, str]] = []
        current: list[str] = []
        current_len = 0
        current_heading: str | None = None

        heading_re = re.compile(
            r"^(?:MADDE\s+\d+|GEÇİCİ\s+MADDE\s+\d+|BİRİNCİ|İKİNCİ|ÜÇÜNCÜ|DÖRDÜNCÜ|BEŞİNCİ|ALTINCI|YEDİNCİ|SEKİZİNCİ|DOKUZUNCU|ONUNCU)\b",
            re.IGNORECASE,
        )

        def flush() -> None:
            nonlocal current, current_len, current_heading
            if current:
                output.append((current_heading, "\n\n".join(current).strip()))
                current = []
                current_len = 0
                current_heading = None

        for block in blocks:
            first_line = block.splitlines()[0].strip()
            is_heading = bool(heading_re.search(first_line)) or (
                len(first_line) <= 120 and first_line.isupper() and len(first_line.split()) <= 12
            )
            if is_heading and current:
                flush()
            if is_heading:
                current_heading = first_line[:240]
            if current and current_len + len(block) + 2 > target_chars:
                flush()
                if is_heading:
                    current_heading = first_line[:240]
            current.append(block)
            current_len += len(block) + 2
        flush()
        return output

    def sync_verified(self, instrument_id: str) -> list[LegalKnowledgeChunk]:
        with self._connect() as conn:
            instrument = conn.execute(
                "SELECT * FROM legal_instruments WHERE id = ? AND verification_status = 'verified'",
                (instrument_id,),
            ).fetchone()
            if instrument is None:
                raise ValueError("instrument_not_verified")

            verification = conn.execute(
                """
                SELECT * FROM legal_verifications
                WHERE instrument_id = ? AND decision = 'verified'
                ORDER BY decided_at DESC, created_at DESC
                LIMIT 1
                """,
                (instrument_id,),
            ).fetchone()
            if verification is None:
                raise ValueError("verified_record_missing")

            full_text = verification["authoritative_text"]
            expected_hash = verification["content_sha256"]
            actual_hash = hashlib.sha256(full_text.encode("utf-8")).hexdigest()
            if actual_hash != expected_hash:
                raise ValueError("authoritative_text_hash_mismatch")

            chunks = self._chunks(full_text)
            if not chunks:
                raise ValueError("authoritative_text_has_no_indexable_chunks")

            now = datetime.now(timezone.utc).isoformat()
            effective_to = instrument["effective_to"]
            publication_date = verification["publication_date"]
            effective_from = verification["effective_from"]
            source_url = verification["authoritative_url"]
            title = instrument["title"]
            verification_id = verification["id"]

            old_ids = [
                row["id"]
                for row in conn.execute(
                    "SELECT id FROM legal_knowledge_chunks WHERE instrument_id = ?",
                    (instrument_id,),
                ).fetchall()
            ]
            for doc_id in old_ids:
                conn.execute("DELETE FROM knowledge_fts WHERE doc_id = ?", (doc_id,))
                conn.execute("DELETE FROM knowledge_documents WHERE id = ?", (doc_id,))
            conn.execute("DELETE FROM legal_knowledge_chunks WHERE instrument_id = ?", (instrument_id,))

            for ordinal, (heading, chunk_text) in enumerate(chunks, start=1):
                chunk_hash = hashlib.sha256(chunk_text.encode("utf-8")).hexdigest()
                chunk_id = f"legal:{instrument_id}:{expected_hash[:12]}:{ordinal:04d}"
                citation_title = f"{title} — {heading}" if heading else f"{title} — Bölüm {ordinal}"
                provenance_prefix = (
                    f"[EAY LEGAL PROVENANCE] instrument={instrument_id}; verification={verification_id}; "
                    f"full_sha256={expected_hash}; chunk_sha256={chunk_hash}; ordinal={ordinal}\n"
                )
                indexed_content = provenance_prefix + chunk_text

                conn.execute(
                    """
                    INSERT INTO legal_knowledge_chunks(
                        id, instrument_id, verification_id, ordinal, heading,
                        content_sha256, chunk_sha256, source_url, publication_date,
                        effective_from, effective_to, text, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        chunk_id,
                        instrument_id,
                        verification_id,
                        ordinal,
                        heading,
                        expected_hash,
                        chunk_hash,
                        source_url,
                        publication_date,
                        effective_from,
                        effective_to,
                        chunk_text,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO knowledge_documents(
                        id, layer, title, content, source_name, source_url,
                        jurisdiction, authority_level, effective_from, effective_to,
                        version, updated_at
                    ) VALUES (?, 'legal', ?, ?, ?, ?, 'TR', 'binding', ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title,
                        content=excluded.content,
                        source_name=excluded.source_name,
                        source_url=excluded.source_url,
                        effective_from=excluded.effective_from,
                        effective_to=excluded.effective_to,
                        version=excluded.version,
                        updated_at=excluded.updated_at
                    """,
                    (
                        chunk_id,
                        citation_title,
                        indexed_content,
                        title,
                        source_url,
                        effective_from,
                        effective_to,
                        expected_hash,
                        now,
                    ),
                )
                conn.execute(
                    "INSERT INTO knowledge_fts(doc_id, title, content) VALUES (?, ?, ?)",
                    (chunk_id, citation_title, indexed_content),
                )

            rows = conn.execute(
                "SELECT * FROM legal_knowledge_chunks WHERE instrument_id = ? ORDER BY ordinal",
                (instrument_id,),
            ).fetchall()
        return [self._row(row) for row in rows]

    @staticmethod
    def _row(row: sqlite3.Row) -> LegalKnowledgeChunk:
        return LegalKnowledgeChunk(
            id=row["id"],
            instrument_id=row["instrument_id"],
            verification_id=row["verification_id"],
            ordinal=row["ordinal"],
            heading=row["heading"],
            content_sha256=row["content_sha256"],
            chunk_sha256=row["chunk_sha256"],
            source_url=row["source_url"],
            publication_date=date.fromisoformat(row["publication_date"]),
            effective_from=date.fromisoformat(row["effective_from"]),
            effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
            text=row["text"],
        )

    def list_chunks(self, instrument_id: str, as_of: date | None = None) -> list[LegalKnowledgeChunk]:
        clauses = ["instrument_id = ?"]
        params: list[object] = [instrument_id]
        if as_of:
            clauses.append("effective_from <= ?")
            params.append(as_of.isoformat())
            clauses.append("(effective_to IS NULL OR effective_to >= ?)")
            params.append(as_of.isoformat())
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM legal_knowledge_chunks WHERE {' AND '.join(clauses)} ORDER BY ordinal",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]


indexer = LegalKnowledgeIndexer(DB_PATH)
router = APIRouter(prefix="/v1/legal/knowledge", tags=["legal-knowledge"])


@router.post("/sync/{instrument_id}", response_model=list[LegalKnowledgeChunk])
def sync_legal_knowledge(instrument_id: str):
    try:
        return indexer.sync_verified(instrument_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/{instrument_id}", response_model=list[LegalKnowledgeChunk])
def list_legal_knowledge(
    instrument_id: str,
    as_of: date | None = Query(default=None),
):
    return indexer.list_chunks(instrument_id, as_of)
