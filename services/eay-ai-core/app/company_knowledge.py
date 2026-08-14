from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, model_validator

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
PolicyStatus = Literal["draft", "approved", "superseded", "retired"]


class CompanyPolicyCreate(BaseModel):
    policy_id: str = Field(min_length=3, max_length=180)
    company: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=3, max_length=600)
    version: str = Field(min_length=1, max_length=80)
    content: str = Field(min_length=20)
    source_url: HttpUrl | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    owner: str | None = Field(default=None, max_length=200)
    approval_reference: str | None = Field(default=None, max_length=300)
    topics: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_dates(self):
        if self.effective_from and self.effective_to and self.effective_to < self.effective_from:
            raise ValueError("effective_to cannot be before effective_from")
        return self


class PolicyRecord(BaseModel):
    id: str
    policy_id: str
    company: str
    title: str
    version: str
    content_sha256: str
    status: PolicyStatus
    source_url: str | None = None
    effective_from: date | None = None
    effective_to: date | None = None
    owner: str | None = None
    approval_reference: str | None = None
    created_at: datetime
    approved_at: datetime | None = None


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=2, max_length=200)
    approval_reference: str = Field(min_length=2, max_length=300)


class CompanyKnowledgeStore:
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
                CREATE TABLE IF NOT EXISTS company_policy_versions (
                    id TEXT PRIMARY KEY,
                    policy_id TEXT NOT NULL,
                    company TEXT NOT NULL,
                    title TEXT NOT NULL,
                    version TEXT NOT NULL,
                    content TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    source_url TEXT,
                    effective_from TEXT,
                    effective_to TEXT,
                    owner TEXT,
                    approval_reference TEXT,
                    approved_by TEXT,
                    topics_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    UNIQUE(policy_id, version)
                );

                CREATE INDEX IF NOT EXISTS idx_company_policy_effective
                ON company_policy_versions(policy_id, company, status, effective_from, effective_to);
                """
            )

    @staticmethod
    def _record(row: sqlite3.Row) -> PolicyRecord:
        return PolicyRecord(
            id=row["id"],
            policy_id=row["policy_id"],
            company=row["company"],
            title=row["title"],
            version=row["version"],
            content_sha256=row["content_sha256"],
            status=row["status"],
            source_url=row["source_url"],
            effective_from=date.fromisoformat(row["effective_from"]) if row["effective_from"] else None,
            effective_to=date.fromisoformat(row["effective_to"]) if row["effective_to"] else None,
            owner=row["owner"],
            approval_reference=row["approval_reference"],
            created_at=datetime.fromisoformat(row["created_at"]),
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
        )

    def create(self, payload: CompanyPolicyCreate) -> PolicyRecord:
        now = datetime.now(timezone.utc).isoformat()
        record_id = str(uuid.uuid4())
        content_hash = hashlib.sha256(payload.content.encode("utf-8")).hexdigest()
        with self._connect() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO company_policy_versions(
                        id, policy_id, company, title, version, content, content_sha256,
                        status, source_url, effective_from, effective_to, owner,
                        approval_reference, topics_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id, payload.policy_id, payload.company, payload.title,
                        payload.version, payload.content, content_hash,
                        str(payload.source_url) if payload.source_url else None,
                        payload.effective_from.isoformat() if payload.effective_from else None,
                        payload.effective_to.isoformat() if payload.effective_to else None,
                        payload.owner, payload.approval_reference,
                        __import__('json').dumps(payload.topics, ensure_ascii=False), now,
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("policy_version_already_exists") from exc
            row = conn.execute("SELECT * FROM company_policy_versions WHERE id=?", (record_id,)).fetchone()
        assert row is not None
        return self._record(row)

    def approve(self, record_id: str, payload: ApprovalRequest) -> PolicyRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM company_policy_versions WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("policy_not_found")
            if row["status"] != "draft":
                raise ValueError("policy_not_draft")
            if not row["effective_from"]:
                raise ValueError("approved policy requires effective_from")

            # Close any previously-approved open version at the day before this version.
            new_from = date.fromisoformat(row["effective_from"])
            previous = conn.execute(
                """
                SELECT * FROM company_policy_versions
                WHERE policy_id=? AND company=? AND status='approved' AND id<>?
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY effective_from DESC LIMIT 1
                """,
                (row["policy_id"], row["company"], record_id, new_from.isoformat()),
            ).fetchone()
            if previous and previous["effective_from"] and date.fromisoformat(previous["effective_from"]) < new_from:
                from datetime import timedelta
                conn.execute(
                    "UPDATE company_policy_versions SET status='superseded', effective_to=? WHERE id=?",
                    ((new_from - timedelta(days=1)).isoformat(), previous["id"]),
                )

            conn.execute(
                """
                UPDATE company_policy_versions
                SET status='approved', approved_by=?, approval_reference=?, approved_at=?
                WHERE id=?
                """,
                (payload.approved_by, payload.approval_reference, now, record_id),
            )
            row = conn.execute("SELECT * FROM company_policy_versions WHERE id=?", (record_id,)).fetchone()
        assert row is not None
        return self._record(row)

    def index_approved(self, record_id: str, chunk_size: int = 1800) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM company_policy_versions WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("policy_not_found")
            if row["status"] != "approved":
                raise ValueError("only approved policy versions may enter company RAG")

            content = row["content"].strip()
            chunks = [content[i:i + chunk_size] for i in range(0, len(content), chunk_size)]
            for idx, chunk in enumerate(chunks):
                doc_id = f"company:{row['id']}:{idx}"
                title = f"{row['title']} — v{row['version']} — chunk {idx + 1}"
                existing = conn.execute(
                    "SELECT id FROM knowledge_documents WHERE id=?", (doc_id,)
                ).fetchone()
                if existing:
                    conn.execute("DELETE FROM knowledge_fts WHERE doc_id=?", (doc_id,))
                    conn.execute("DELETE FROM knowledge_documents WHERE id=?", (doc_id,))
                conn.execute(
                    """
                    INSERT INTO knowledge_documents(
                        id, layer, title, content, source_name, source_url,
                        jurisdiction, authority_level, effective_from, effective_to,
                        version, updated_at
                    ) VALUES (?, 'company', ?, ?, ?, ?, 'TR', 'company', ?, ?, ?, ?)
                    """,
                    (
                        doc_id, title, chunk, row["company"], row["source_url"],
                        row["effective_from"], row["effective_to"], row["version"],
                        datetime.now(timezone.utc).isoformat(),
                    ),
                )
                conn.execute(
                    "INSERT INTO knowledge_fts(doc_id, title, content) VALUES (?, ?, ?)",
                    (doc_id, title, chunk),
                )
            return len(chunks)

    def list_as_of(self, company: str, as_of: date) -> list[PolicyRecord]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM company_policy_versions
                WHERE company=? AND status IN ('approved','superseded')
                  AND effective_from <= ?
                  AND (effective_to IS NULL OR effective_to >= ?)
                ORDER BY policy_id, effective_from DESC
                """,
                (company, as_of.isoformat(), as_of.isoformat()),
            ).fetchall()
        return [self._record(row) for row in rows]


store = CompanyKnowledgeStore(DB_PATH)
router = APIRouter(prefix="/v1/company-knowledge", tags=["company-knowledge"])


@router.post("/policies", response_model=PolicyRecord)
def create_policy(payload: CompanyPolicyCreate):
    try:
        return store.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/policies/{record_id}/approve", response_model=PolicyRecord)
def approve_policy(record_id: str, payload: ApprovalRequest):
    try:
        return store.approve(record_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Policy not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/policies/{record_id}/index")
def index_policy(record_id: str):
    try:
        count = store.index_approved(record_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Policy not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"ok": True, "indexed_chunks": count}


@router.get("/policies", response_model=list[PolicyRecord])
def list_policies(company: str, as_of: date = Query(default_factory=date.today)):
    return store.list_as_of(company, as_of)
