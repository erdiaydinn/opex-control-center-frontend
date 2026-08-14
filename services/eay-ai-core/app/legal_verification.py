from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, model_validator

from .legal_knowledge import indexer
from .legal_promotion_gate import LegalPromotionCandidate, RelationType, evaluate_legal_promotion
from .legal_relations import LegalRelationStore
from .regulatory import SourceDefinition
from .regulatory_authority import assess_regulatory_authority

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))

VerificationDecision = Literal["pending", "verified", "rejected"]
AUTHORITATIVE_HOSTS = {
    "resmigazete.gov.tr",
    "www.resmigazete.gov.tr",
    "mevzuat.gov.tr",
    "www.mevzuat.gov.tr",
}


class VerificationCreate(BaseModel):
    instrument_id: str = Field(min_length=3, max_length=180)
    authoritative_url: HttpUrl
    authoritative_text: str = Field(min_length=20)
    publication_date: date
    effective_from: date
    official_gazette_number: str | None = Field(default=None, max_length=80)
    relation_type: RelationType = "new"
    related_instrument_id: str | None = Field(default=None, max_length=180)
    verifier_note: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def authoritative_source_only(self):
        host = (urlparse(str(self.authoritative_url)).hostname or "").lower()
        if host not in AUTHORITATIVE_HOSTS:
            raise ValueError("verification requires Resmi Gazete or Mevzuat Bilgi Sistemi source")
        if self.effective_from < self.publication_date:
            raise ValueError("effective_from cannot be before publication_date")
        if self.relation_type != "new" and not self.related_instrument_id:
            raise ValueError("related_instrument_required")
        if self.relation_type == "new" and self.related_instrument_id:
            raise ValueError("new_instrument_must_not_reference_relation_target")
        return self


class VerificationRecord(BaseModel):
    id: str
    instrument_id: str
    authoritative_url: str
    content_sha256: str
    publication_date: date
    effective_from: date
    official_gazette_number: str | None = None
    relation_type: RelationType = "new"
    related_instrument_id: str | None = None
    relation_record_id: str | None = None
    relation_fingerprint: str | None = None
    authority_level: str | None = None
    authority_assessment_fingerprint: str | None = None
    promotion_decision_fingerprint: str | None = None
    decision: VerificationDecision
    verifier_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None


class DecisionRequest(BaseModel):
    note: str | None = Field(default=None, max_length=2000)
    approval_ref: str | None = Field(default=None, min_length=3, max_length=180)


class LegalVerificationStore:
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
                CREATE TABLE IF NOT EXISTS legal_verifications (
                    id TEXT PRIMARY KEY,
                    instrument_id TEXT NOT NULL,
                    authoritative_url TEXT NOT NULL,
                    authoritative_text TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    publication_date TEXT NOT NULL,
                    effective_from TEXT NOT NULL,
                    official_gazette_number TEXT,
                    decision TEXT NOT NULL DEFAULT 'pending',
                    verifier_note TEXT,
                    created_at TEXT NOT NULL,
                    decided_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_legal_verifications_instrument
                ON legal_verifications(instrument_id, created_at DESC);
                """
            )
            columns = {
                row[1]
                for row in conn.execute("PRAGMA table_info(legal_verifications)").fetchall()
            }
            migrations = {
                "relation_type": "ALTER TABLE legal_verifications ADD COLUMN relation_type TEXT NOT NULL DEFAULT 'new'",
                "related_instrument_id": "ALTER TABLE legal_verifications ADD COLUMN related_instrument_id TEXT",
                "relation_record_id": "ALTER TABLE legal_verifications ADD COLUMN relation_record_id TEXT",
                "relation_fingerprint": "ALTER TABLE legal_verifications ADD COLUMN relation_fingerprint TEXT",
                "authority_level": "ALTER TABLE legal_verifications ADD COLUMN authority_level TEXT",
                "authority_assessment_fingerprint": "ALTER TABLE legal_verifications ADD COLUMN authority_assessment_fingerprint TEXT",
                "promotion_decision_fingerprint": "ALTER TABLE legal_verifications ADD COLUMN promotion_decision_fingerprint TEXT",
            }
            for column, sql in migrations.items():
                if column not in columns:
                    conn.execute(sql)

    @staticmethod
    def _row(row: sqlite3.Row) -> VerificationRecord:
        keys = set(row.keys())
        return VerificationRecord(
            id=row["id"],
            instrument_id=row["instrument_id"],
            authoritative_url=row["authoritative_url"],
            content_sha256=row["content_sha256"],
            publication_date=date.fromisoformat(row["publication_date"]),
            effective_from=date.fromisoformat(row["effective_from"]),
            official_gazette_number=row["official_gazette_number"],
            relation_type=row["relation_type"] if "relation_type" in keys else "new",
            related_instrument_id=row["related_instrument_id"] if "related_instrument_id" in keys else None,
            relation_record_id=row["relation_record_id"] if "relation_record_id" in keys else None,
            relation_fingerprint=row["relation_fingerprint"] if "relation_fingerprint" in keys else None,
            authority_level=row["authority_level"] if "authority_level" in keys else None,
            authority_assessment_fingerprint=row["authority_assessment_fingerprint"] if "authority_assessment_fingerprint" in keys else None,
            promotion_decision_fingerprint=row["promotion_decision_fingerprint"] if "promotion_decision_fingerprint" in keys else None,
            decision=row["decision"],
            verifier_note=row["verifier_note"],
            created_at=datetime.fromisoformat(row["created_at"]),
            decided_at=datetime.fromisoformat(row["decided_at"]) if row["decided_at"] else None,
        )

    @staticmethod
    def _authority_assessment(authoritative_url: str, authoritative_text: str):
        host = (urlparse(authoritative_url).hostname or "").lower()
        if host not in {"resmigazete.gov.tr", "www.resmigazete.gov.tr"}:
            raise ValueError("exact_resmi_gazete_instrument_required_for_promotion")
        source = SourceDefinition(
            id="tr-resmi-gazete-verification",
            name="T.C. Resmi Gazete verification source",
            url="https://www.resmigazete.gov.tr/",
            role="binding_publication_index",
        )
        return assess_regulatory_authority(
            source,
            document_url=authoritative_url,
            text=authoritative_text,
        )

    def create(self, payload: VerificationCreate) -> VerificationRecord:
        assessment = self._authority_assessment(str(payload.authoritative_url), payload.authoritative_text)
        with self._connect() as conn:
            instrument = conn.execute(
                "SELECT id, verification_status FROM legal_instruments WHERE id = ?",
                (payload.instrument_id,),
            ).fetchone()
            if instrument is None:
                raise KeyError("instrument_not_found")
            if instrument["verification_status"] not in {"draft", "superseded"}:
                raise ValueError("instrument_not_verifiable")
            if payload.related_instrument_id:
                target = conn.execute(
                    "SELECT verification_status FROM legal_instruments WHERE id = ?",
                    (payload.related_instrument_id,),
                ).fetchone()
                if target is None:
                    raise KeyError("related_instrument_not_found")
                if target["verification_status"] == "draft":
                    raise ValueError("related_instrument_must_not_be_draft")
            pending = conn.execute(
                "SELECT id FROM legal_verifications WHERE instrument_id = ? AND decision = 'pending' LIMIT 1",
                (payload.instrument_id,),
            ).fetchone()
            if pending is not None:
                raise ValueError("pending_verification_already_exists")

            record_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc).isoformat()
            content_hash = hashlib.sha256(payload.authoritative_text.encode("utf-8")).hexdigest()
            conn.execute(
                """
                INSERT INTO legal_verifications(
                    id, instrument_id, authoritative_url, authoritative_text,
                    content_sha256, publication_date, effective_from,
                    official_gazette_number, relation_type, related_instrument_id,
                    authority_level, authority_assessment_fingerprint,
                    decision, verifier_note, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?)
                """,
                (
                    record_id,
                    payload.instrument_id,
                    str(payload.authoritative_url),
                    payload.authoritative_text,
                    content_hash,
                    payload.publication_date.isoformat(),
                    payload.effective_from.isoformat(),
                    payload.official_gazette_number,
                    payload.relation_type,
                    payload.related_instrument_id,
                    assessment.authority_level,
                    assessment.assessment_fingerprint,
                    payload.verifier_note,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM legal_verifications WHERE id = ?", (record_id,)).fetchone()
        assert row is not None
        return self._row(row)

    def list(self, instrument_id: str | None, decision: VerificationDecision | None, limit: int) -> list[VerificationRecord]:
        clauses = []
        params: list[object] = []
        if instrument_id:
            clauses.append("instrument_id = ?")
            params.append(instrument_id)
        if decision:
            clauses.append("decision = ?")
            params.append(decision)
        where = "WHERE " + " AND ".join(clauses) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM legal_verifications {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def reject(self, record_id: str, note: str | None) -> VerificationRecord:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM legal_verifications WHERE id = ?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("verification_not_found")
            if row["decision"] != "pending":
                raise ValueError("verification_not_pending")
            conn.execute(
                "UPDATE legal_verifications SET decision='rejected', verifier_note=COALESCE(?, verifier_note), decided_at=? WHERE id=?",
                (note, now, record_id),
            )
            row = conn.execute("SELECT * FROM legal_verifications WHERE id = ?", (record_id,)).fetchone()
        assert row is not None
        return self._row(row)

    def verify_and_apply(
        self,
        record_id: str,
        note: str | None,
        human_approval_ref: str | None = None,
    ) -> VerificationRecord:
        """Atomically promote evidence and stage any legal relation for separate review."""
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            record = conn.execute(
                "SELECT * FROM legal_verifications WHERE id = ?",
                (record_id,),
            ).fetchone()
            if record is None:
                raise KeyError("verification_not_found")
            if record["decision"] != "pending":
                raise ValueError("verification_not_pending")

            instrument = conn.execute(
                "SELECT * FROM legal_instruments WHERE id = ?",
                (record["instrument_id"],),
            ).fetchone()
            if instrument is None:
                raise KeyError("instrument_not_found")
            if instrument["verification_status"] not in {"draft", "superseded"}:
                raise ValueError("instrument_not_verifiable")

            assessment = self._authority_assessment(
                record["authoritative_url"], record["authoritative_text"]
            )
            if record["authority_assessment_fingerprint"] and record["authority_assessment_fingerprint"] != assessment.assessment_fingerprint:
                raise ValueError("authority_assessment_fingerprint_mismatch")

            approval_ref = human_approval_ref or note
            candidate = LegalPromotionCandidate(
                instrument_id=record["instrument_id"],
                authoritative_url=record["authoritative_url"],
                authoritative_text=record["authoritative_text"],
                expected_content_sha256=record["content_sha256"],
                publication_date=date.fromisoformat(record["publication_date"]),
                effective_from=date.fromisoformat(record["effective_from"]),
                authority_assessment=assessment,
                relation_type=record["relation_type"],
                related_instrument_id=record["related_instrument_id"],
                human_approval_ref=approval_ref,
            )
            promotion = evaluate_legal_promotion(candidate)
            if not promotion.eligible:
                raise ValueError("legal_promotion_blocked:" + ",".join(promotion.blockers))

            if record["related_instrument_id"]:
                target = conn.execute(
                    "SELECT verification_status FROM legal_instruments WHERE id = ?",
                    (record["related_instrument_id"],),
                ).fetchone()
                if target is None:
                    raise KeyError("related_instrument_not_found")
                if target["verification_status"] == "draft":
                    raise ValueError("related_instrument_must_not_be_draft")

            notes = instrument["notes"] or ""
            audit_line = (
                f"Verified content sha256: {record['content_sha256']}; "
                f"verification record: {record['id']}; "
                f"promotion decision: {promotion.decision_fingerprint}"
            )
            if audit_line not in notes:
                notes = (notes + "\n" + audit_line).strip()

            conn.execute(
                """
                UPDATE legal_instruments
                SET publication_date=?, effective_from=?,
                    official_gazette_number=COALESCE(?, official_gazette_number),
                    source_url=?, verification_status='verified', notes=?, updated_at=?
                WHERE id=?
                """,
                (
                    record["publication_date"],
                    record["effective_from"],
                    record["official_gazette_number"],
                    record["authoritative_url"],
                    notes,
                    now,
                    record["instrument_id"],
                ),
            )

            relation_record_id: str | None = None
            relation_fingerprint: str | None = None
            if record["relation_type"] != "new":
                if not record["related_instrument_id"]:
                    raise ValueError("related_instrument_required")
                relation = LegalRelationStore.propose_with_connection(
                    conn,
                    source_instrument_id=record["instrument_id"],
                    relation_type=record["relation_type"],
                    target_instrument_id=record["related_instrument_id"],
                    evidence_ref=(
                        f"verification:{record['id']}:promotion:{promotion.decision_fingerprint}"
                    ),
                    created_at=now,
                )
                relation_record_id = relation.id
                relation_fingerprint = relation.relation_fingerprint

            conn.execute(
                """
                UPDATE legal_verifications
                SET decision='verified', verifier_note=COALESCE(?, verifier_note),
                    promotion_decision_fingerprint=?, relation_record_id=?,
                    relation_fingerprint=?, decided_at=?
                WHERE id=?
                """,
                (
                    note,
                    promotion.decision_fingerprint,
                    relation_record_id,
                    relation_fingerprint,
                    now,
                    record_id,
                ),
            )
            row = conn.execute("SELECT * FROM legal_verifications WHERE id = ?", (record_id,)).fetchone()
        assert row is not None
        return self._row(row)

    def decide(
        self,
        record_id: str,
        decision: Literal["verified", "rejected"],
        note: str | None,
    ) -> VerificationRecord:
        """Backward-compatible decision API; note acts as approval ref for legacy callers."""
        if decision == "verified":
            return self.verify_and_apply(record_id, note, human_approval_ref=note)
        return self.reject(record_id, note)


store = LegalVerificationStore(DB_PATH)
router = APIRouter(prefix="/v1/legal/verification", tags=["legal-verification"])


@router.post("", response_model=VerificationRecord)
def create_verification(payload: VerificationCreate):
    try:
        return store.create(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("", response_model=list[VerificationRecord])
def list_verifications(
    instrument_id: str | None = Query(default=None),
    decision: VerificationDecision | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return store.list(instrument_id, decision, limit)


@router.post("/{record_id}/verify", response_model=VerificationRecord)
def verify(record_id: str, payload: DecisionRequest):
    try:
        if not payload.approval_ref:
            raise ValueError("human_approval_required")
        record = store.verify_and_apply(
            record_id, payload.note, human_approval_ref=payload.approval_ref
        )
        indexer.sync_verified(record.instrument_id)
        return record
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{record_id}/reject", response_model=VerificationRecord)
def reject(record_id: str, payload: DecisionRequest):
    try:
        return store.reject(record_id, payload.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Verification record not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
