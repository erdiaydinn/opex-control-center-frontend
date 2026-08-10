from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl

from .legal_engine import LegalEngine, LegalInstrumentUpsert


DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
CandidateStatus = Literal[
    "pending_review",
    "approved_for_verification",
    "rejected",
    "promoted_draft",
]


class CandidateProposal(BaseModel):
    change_id: str = Field(min_length=3)
    proposed_title: str | None = Field(default=None, max_length=600)
    proposed_instrument_type: Literal[
        "law", "regulation", "communique", "guideline", "decision", "other"
    ] | None = None
    proposed_publication_date: date | None = None
    proposed_effective_from: date | None = None
    proposed_transition_deadline: date | None = None
    proposed_official_gazette_number: str | None = Field(default=None, max_length=80)
    proposed_source_url: HttpUrl | None = None
    extraction_method: Literal["human", "deterministic", "local_model"] = "deterministic"
    extraction_notes: str | None = Field(default=None, max_length=2000)


class LegalCandidate(BaseModel):
    id: str
    change_id: str
    source_id: str
    source_name: str
    source_url: str
    source_role: str
    raw_diff: str
    raw_diff_sha256: str
    detected_at: datetime
    status: CandidateStatus
    proposed_title: str | None = None
    proposed_instrument_type: str | None = None
    proposed_publication_date: date | None = None
    proposed_effective_from: date | None = None
    proposed_transition_deadline: date | None = None
    proposed_official_gazette_number: str | None = None
    proposed_source_url: str | None = None
    extraction_method: str
    extraction_notes: str | None = None
    reviewer_note: str | None = None
    promoted_instrument_id: str | None = None
    created_at: datetime
    updated_at: datetime


class CandidateDecision(BaseModel):
    note: str | None = Field(default=None, max_length=2000)


class PromoteDraftRequest(BaseModel):
    instrument_id: str = Field(min_length=3, max_length=180)
    title: str = Field(min_length=3, max_length=600)
    instrument_type: Literal[
        "law", "regulation", "communique", "guideline", "decision", "other"
    ]
    source_url: HttpUrl
    publication_date: date | None = None
    effective_from: date | None = None
    transition_deadline: date | None = None
    official_gazette_number: str | None = Field(default=None, max_length=80)
    topics: list[str] = Field(default_factory=list)
    notes: str | None = Field(default=None, max_length=3000)


class LegalReviewStore:
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
                CREATE TABLE IF NOT EXISTS legal_candidates (
                    id TEXT PRIMARY KEY,
                    change_id TEXT NOT NULL UNIQUE,
                    source_id TEXT NOT NULL,
                    source_name TEXT NOT NULL,
                    source_url TEXT NOT NULL,
                    source_role TEXT NOT NULL,
                    raw_diff TEXT NOT NULL,
                    raw_diff_sha256 TEXT NOT NULL,
                    detected_at TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending_review',
                    proposed_title TEXT,
                    proposed_instrument_type TEXT,
                    proposed_publication_date TEXT,
                    proposed_effective_from TEXT,
                    proposed_transition_deadline TEXT,
                    proposed_official_gazette_number TEXT,
                    proposed_source_url TEXT,
                    extraction_method TEXT NOT NULL,
                    extraction_notes TEXT,
                    reviewer_note TEXT,
                    promoted_instrument_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_legal_candidates_status_time
                ON legal_candidates(status, created_at DESC);
                """
            )

    def create_from_change(self, proposal: CandidateProposal) -> LegalCandidate:
        with self._connect() as conn:
            change = conn.execute(
                "SELECT * FROM regulatory_changes WHERE id = ?",
                (proposal.change_id,),
            ).fetchone()
            if change is None:
                raise KeyError("regulatory_change_not_found")
            existing = conn.execute(
                "SELECT * FROM legal_candidates WHERE change_id = ?",
                (proposal.change_id,),
            ).fetchone()
            if existing is not None:
                return self._row(existing)

            raw_diff = change["diff_excerpt"]
            now = datetime.now(timezone.utc).isoformat()
            candidate_id = str(uuid.uuid4())
            conn.execute(
                """
                INSERT INTO legal_candidates(
                    id, change_id, source_id, source_name, source_url, source_role,
                    raw_diff, raw_diff_sha256, detected_at, status,
                    proposed_title, proposed_instrument_type, proposed_publication_date,
                    proposed_effective_from, proposed_transition_deadline,
                    proposed_official_gazette_number, proposed_source_url,
                    extraction_method, extraction_notes, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending_review', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    candidate_id,
                    proposal.change_id,
                    change["source_id"],
                    change["source_name"],
                    change["source_url"],
                    change["source_role"],
                    raw_diff,
                    hashlib.sha256(raw_diff.encode("utf-8")).hexdigest(),
                    change["detected_at"],
                    proposal.proposed_title,
                    proposal.proposed_instrument_type,
                    proposal.proposed_publication_date.isoformat() if proposal.proposed_publication_date else None,
                    proposal.proposed_effective_from.isoformat() if proposal.proposed_effective_from else None,
                    proposal.proposed_transition_deadline.isoformat() if proposal.proposed_transition_deadline else None,
                    proposal.proposed_official_gazette_number,
                    str(proposal.proposed_source_url) if proposal.proposed_source_url else None,
                    proposal.extraction_method,
                    proposal.extraction_notes,
                    now,
                    now,
                ),
            )
            row = conn.execute("SELECT * FROM legal_candidates WHERE id = ?", (candidate_id,)).fetchone()
        assert row is not None
        return self._row(row)

    @staticmethod
    def _row(row: sqlite3.Row) -> LegalCandidate:
        data = dict(row)
        for key in (
            "proposed_publication_date",
            "proposed_effective_from",
            "proposed_transition_deadline",
        ):
            data[key] = date.fromisoformat(data[key]) if data[key] else None
        data["detected_at"] = datetime.fromisoformat(data["detected_at"])
        data["created_at"] = datetime.fromisoformat(data["created_at"])
        data["updated_at"] = datetime.fromisoformat(data["updated_at"])
        return LegalCandidate(**data)

    def list(self, status: CandidateStatus | None, limit: int) -> list[LegalCandidate]:
        where = "WHERE status = ?" if status else ""
        params: tuple[object, ...] = (status, limit) if status else (limit,)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM legal_candidates {where} ORDER BY created_at DESC LIMIT ?",
                params,
            ).fetchall()
        return [self._row(row) for row in rows]

    def get(self, candidate_id: str) -> LegalCandidate | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM legal_candidates WHERE id = ?", (candidate_id,)).fetchone()
        return self._row(row) if row else None

    def decide(self, candidate_id: str, status: Literal["approved_for_verification", "rejected"], note: str | None) -> LegalCandidate:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            count = conn.execute(
                "UPDATE legal_candidates SET status = ?, reviewer_note = ?, updated_at = ? WHERE id = ? AND status = 'pending_review'",
                (status, note, now, candidate_id),
            ).rowcount
            if count == 0:
                row = conn.execute("SELECT id FROM legal_candidates WHERE id = ?", (candidate_id,)).fetchone()
                if row is None:
                    raise KeyError("candidate_not_found")
                raise ValueError("candidate_not_pending")
        result = self.get(candidate_id)
        assert result is not None
        return result

    def mark_promoted(self, candidate_id: str, instrument_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as conn:
            count = conn.execute(
                "UPDATE legal_candidates SET status='promoted_draft', promoted_instrument_id=?, updated_at=? WHERE id=? AND status='approved_for_verification'",
                (instrument_id, now, candidate_id),
            ).rowcount
        if count == 0:
            raise ValueError("candidate_not_approved_for_verification")


review_store = LegalReviewStore(DB_PATH)
legal_engine = LegalEngine(DB_PATH)
router = APIRouter(prefix="/v1/legal/review", tags=["legal-review"])


@router.post("/candidates", response_model=LegalCandidate)
def create_candidate(payload: CandidateProposal):
    try:
        return review_store.create_from_change(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Regulatory change not found") from exc


@router.get("/candidates", response_model=list[LegalCandidate])
def list_candidates(
    status: CandidateStatus | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
):
    return review_store.list(status, limit)


@router.post("/candidates/{candidate_id}/approve", response_model=LegalCandidate)
def approve_candidate(candidate_id: str, payload: CandidateDecision):
    try:
        return review_store.decide(candidate_id, "approved_for_verification", payload.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/reject", response_model=LegalCandidate)
def reject_candidate(candidate_id: str, payload: CandidateDecision):
    try:
        return review_store.decide(candidate_id, "rejected", payload.note)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Candidate not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/candidates/{candidate_id}/promote-draft")
def promote_candidate_to_draft(candidate_id: str, payload: PromoteDraftRequest):
    candidate = review_store.get(candidate_id)
    if candidate is None:
        raise HTTPException(status_code=404, detail="Candidate not found")
    if candidate.status != "approved_for_verification":
        raise HTTPException(status_code=409, detail="Candidate must be approved for verification first")

    # Promotion is deliberately DRAFT-only. The separate legal verification gate
    # remains the only path to a binding verified instrument.
    instrument = LegalInstrumentUpsert(
        id=payload.instrument_id,
        title=payload.title,
        instrument_type=payload.instrument_type,
        publication_date=payload.publication_date,
        effective_from=payload.effective_from,
        transition_deadline=payload.transition_deadline,
        official_gazette_number=payload.official_gazette_number,
        source_url=payload.source_url,
        verification_status="draft",
        topics=payload.topics,
        notes=(payload.notes or "") + f"\nProvenance candidate: {candidate.id}; regulatory change: {candidate.change_id}; raw diff sha256: {candidate.raw_diff_sha256}",
    )
    legal_engine.upsert_instrument(instrument)
    review_store.mark_promoted(candidate_id, payload.instrument_id)
    return {
        "ok": True,
        "instrument_id": payload.instrument_id,
        "verification_status": "draft",
        "binding": False,
        "provenance": {
            "candidate_id": candidate.id,
            "regulatory_change_id": candidate.change_id,
            "raw_diff_sha256": candidate.raw_diff_sha256,
        },
    }
