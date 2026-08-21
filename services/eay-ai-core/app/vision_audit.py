from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))

AuditDecision = Literal["pending", "accepted", "rejected"]
Severity = Literal["info", "low", "medium", "high", "critical"]


class VisualFinding(BaseModel):
    finding_type: str = Field(min_length=2, max_length=120)
    description: str = Field(min_length=3, max_length=1500)
    severity: Severity = "info"
    confidence: float = Field(ge=0.0, le=1.0)
    region: list[float] | None = Field(default=None, min_length=4, max_length=4)
    rule_reference: str | None = Field(default=None, max_length=300)


class AuditCreate(BaseModel):
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    store_id: str = Field(min_length=1, max_length=180)
    captured_at: datetime
    model_name: str = Field(min_length=1, max_length=180)
    model_version: str = Field(min_length=1, max_length=100)
    findings: list[VisualFinding] = Field(default_factory=list, max_length=200)
    source_uri: str | None = Field(default=None, max_length=1000)


class AuditRecord(BaseModel):
    id: str
    image_sha256: str
    store_id: str
    captured_at: datetime
    model_name: str
    model_version: str
    findings: list[VisualFinding]
    decision: AuditDecision
    created_at: datetime
    decided_at: datetime | None = None


class VisionAuditStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vision_audits (
                    id TEXT PRIMARY KEY,
                    image_sha256 TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    captured_at TEXT NOT NULL,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    findings_json TEXT NOT NULL,
                    source_uri TEXT,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    reviewer_note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT,
                    UNIQUE(image_sha256, model_name, model_version)
                )
                """
            )

    def create(self, payload: AuditCreate) -> AuditRecord:
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO vision_audits(
                        id, image_sha256, store_id, captured_at, model_name,
                        model_version, findings_json, source_uri, decision, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?)
                    """,
                    (
                        record_id, payload.image_sha256, payload.store_id,
                        payload.captured_at.isoformat(), payload.model_name,
                        payload.model_version,
                        json.dumps([f.model_dump() for f in payload.findings], ensure_ascii=False),
                        payload.source_uri, now.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("duplicate_visual_audit") from exc
        return AuditRecord(
            id=record_id,
            image_sha256=payload.image_sha256,
            store_id=payload.store_id,
            captured_at=payload.captured_at,
            model_name=payload.model_name,
            model_version=payload.model_version,
            findings=payload.findings,
            decision="pending",
            created_at=now,
        )

    def decide(self, record_id: str, decision: Literal["accepted", "rejected"], note: str | None = None) -> AuditRecord:
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM vision_audits WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("audit_not_found")
            if row["decision"] != "pending":
                raise ValueError("audit_already_decided")
            conn.execute(
                "UPDATE vision_audits SET decision=?, reviewer_note=?, decided_at=? WHERE id=?",
                (decision, note, now.isoformat(), record_id),
            )
            row = conn.execute("SELECT * FROM vision_audits WHERE id=?", (record_id,)).fetchone()
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> AuditRecord:
        return AuditRecord(
            id=row["id"], image_sha256=row["image_sha256"], store_id=row["store_id"],
            captured_at=datetime.fromisoformat(row["captured_at"]), model_name=row["model_name"],
            model_version=row["model_version"], findings=[VisualFinding(**x) for x in json.loads(row["findings_json"])],
            decision=row["decision"], created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
        )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


store = VisionAuditStore(DB_PATH)
router = APIRouter(prefix="/v1/vision-audit", tags=["vision-audit"])


@router.post("", response_model=AuditRecord)
def create_audit(payload: AuditCreate):
    try:
        return store.create(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{record_id}/{decision}", response_model=AuditRecord)
def decide_audit(record_id: str, decision: Literal["accepted", "rejected"]):
    try:
        return store.decide(record_id, decision)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Audit not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
