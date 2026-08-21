from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .vision_retention import VisionRetentionStore
from .vision_review_lineage import VisionReviewDecisionStore

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))


class VisionEvidence(BaseModel):
    audit_id: str
    image_sha256: str
    source_uri_sha256: str | None = None
    evidence_chain_sha256: str
    retention_fingerprint: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    human_review_required: bool = True
    eligible_for_learning: bool = False


class VisionProvenanceStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.retention = VisionRetentionStore(db_path)
        self.reviews = VisionReviewDecisionStore(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS vision_evidence_provenance (
                    audit_id TEXT PRIMARY KEY,
                    image_sha256 TEXT NOT NULL,
                    source_uri_sha256 TEXT,
                    evidence_chain_sha256 TEXT NOT NULL UNIQUE,
                    metadata_json TEXT NOT NULL
                )
                """
            )

    def register(self, audit_id: str, metadata: dict[str, Any] | None = None) -> VisionEvidence:
        metadata = metadata or {}
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            audit = conn.execute("SELECT * FROM vision_audits WHERE id=?", (audit_id,)).fetchone()
            if audit is None:
                raise KeyError("audit_not_found")
            source_uri = audit["source_uri"] or ""
            source_hash = hashlib.sha256(source_uri.encode("utf-8")).hexdigest() if source_uri else None
            material = "|".join(
                [
                    audit["id"],
                    audit["image_sha256"],
                    source_hash or "NO_SOURCE_URI",
                    audit["store_id"],
                    audit["captured_at"],
                    audit["model_name"],
                    audit["model_version"],
                    hashlib.sha256(audit["findings_json"].encode("utf-8")).hexdigest(),
                ]
            )
            chain_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
            try:
                conn.execute(
                    """
                    INSERT INTO vision_evidence_provenance(
                        audit_id, image_sha256, source_uri_sha256,
                        evidence_chain_sha256, metadata_json
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        audit_id,
                        audit["image_sha256"],
                        source_hash,
                        chain_hash,
                        json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("vision_provenance_already_registered") from exc
            decision = audit["decision"]
            created_at = datetime.fromisoformat(audit["created_at"])
        retention = self.retention.ensure_policy(
            audit_id=audit_id,
            evidence_chain_sha256=chain_hash,
            created_at=created_at,
        )
        return VisionEvidence(
            audit_id=audit_id,
            image_sha256=audit["image_sha256"],
            source_uri_sha256=source_hash,
            evidence_chain_sha256=chain_hash,
            retention_fingerprint=retention.fingerprint,
            metadata=metadata,
            human_review_required=decision == "pending",
            eligible_for_learning=False,
        )

    def pending_reviews(self, limit: int = 100) -> list[dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, image_sha256, store_id, captured_at, model_name,
                       model_version, findings_json, source_uri, created_at
                FROM vision_audits
                WHERE decision='pending'
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "image_sha256": row["image_sha256"],
                "store_id": row["store_id"],
                "captured_at": row["captured_at"],
                "model_name": row["model_name"],
                "model_version": row["model_version"],
                "findings": json.loads(row["findings_json"]),
                "source_uri": row["source_uri"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def learning_eligibility(self, audit_id: str) -> bool:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                """
                SELECT a.decision, p.audit_id
                FROM vision_audits a
                LEFT JOIN vision_evidence_provenance p ON p.audit_id=a.id
                WHERE a.id=?
                """,
                (audit_id,),
            ).fetchone()
        if row is None:
            raise KeyError("audit_not_found")
        if row[0] != "accepted" or row[1] is None:
            return False
        try:
            if not self.retention.is_active(audit_id):
                return False
            review = self.reviews.verify(audit_id)
            return review.decision == "accepted"
        except (KeyError, ValueError):
            return False


store = VisionProvenanceStore(DB_PATH)
router = APIRouter(prefix="/v1/vision-provenance", tags=["vision-provenance"])


@router.post("/{audit_id}", response_model=VisionEvidence)
def register_provenance(audit_id: str, metadata: dict[str, Any] | None = None):
    try:
        return store.register(audit_id, metadata)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/review/pending")
def pending_reviews(limit: int = Query(default=100, ge=1, le=500)):
    return {"items": store.pending_reviews(limit), "human_review_required": True}


@router.get("/{audit_id}/learning-eligibility")
def learning_eligibility(audit_id: str):
    try:
        eligible = store.learning_eligibility(audit_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"audit_id": audit_id, "eligible_for_learning": eligible}
