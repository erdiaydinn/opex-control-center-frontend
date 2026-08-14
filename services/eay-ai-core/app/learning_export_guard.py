from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

candidate_store = None


def _candidate_store():
    if candidate_store is not None:
        return candidate_store
    from .main import store

    return store
from .teacher_quality import evaluate_teacher_review
from .training_gate import DatasetGateResult, validate_training_examples


class ExportReviewCreate(BaseModel):
    reviewed_by: str = Field(min_length=2, max_length=200)
    privacy_safe: bool
    evidence_reviewed: bool = False
    review_reference: str = Field(min_length=2, max_length=300)


class ExportReview(BaseModel):
    candidate_id: str
    reviewed_by: str
    privacy_safe: bool
    evidence_reviewed: bool
    review_reference: str
    reviewed_at: datetime


class GatedLearningExport(BaseModel):
    format: str = "chat_sft"
    examples: list[dict[str, Any]]
    gate: DatasetGateResult


class LearningExportReviewStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS learning_export_reviews (
                    candidate_id TEXT PRIMARY KEY,
                    reviewed_by TEXT NOT NULL,
                    privacy_safe INTEGER NOT NULL,
                    evidence_reviewed INTEGER NOT NULL,
                    review_reference TEXT NOT NULL,
                    reviewed_at TEXT NOT NULL
                )
                """
            )

    def save(self, candidate_id: str, payload: ExportReviewCreate) -> ExportReview:
        row = _candidate_store().candidate_context(candidate_id)
        if row is None:
            raise KeyError("candidate_not_found")
        if row["status"] != "approved":
            raise ValueError("learning_export_candidate_must_be_approved")
        if not payload.privacy_safe:
            raise ValueError("learning_export_privacy_review_failed")

        reviewed_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO learning_export_reviews(
                    candidate_id, reviewed_by, privacy_safe, evidence_reviewed,
                    review_reference, reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    reviewed_by=excluded.reviewed_by,
                    privacy_safe=excluded.privacy_safe,
                    evidence_reviewed=excluded.evidence_reviewed,
                    review_reference=excluded.review_reference,
                    reviewed_at=excluded.reviewed_at
                """,
                (
                    candidate_id,
                    payload.reviewed_by,
                    int(payload.privacy_safe),
                    int(payload.evidence_reviewed),
                    payload.review_reference,
                    reviewed_at.isoformat(),
                ),
            )
        return ExportReview(
            candidate_id=candidate_id,
            reviewed_by=payload.reviewed_by,
            privacy_safe=payload.privacy_safe,
            evidence_reviewed=payload.evidence_reviewed,
            review_reference=payload.review_reference,
            reviewed_at=reviewed_at,
        )

    def get(self, candidate_id: str) -> ExportReview | None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM learning_export_reviews WHERE candidate_id=?",
                (candidate_id,),
            ).fetchone()
        if row is None:
            return None
        return ExportReview(
            candidate_id=row["candidate_id"],
            reviewed_by=row["reviewed_by"],
            privacy_safe=bool(row["privacy_safe"]),
            evidence_reviewed=bool(row["evidence_reviewed"]),
            review_reference=row["review_reference"],
            reviewed_at=datetime.fromisoformat(row["reviewed_at"]),
        )


def _evidence_provenance(row: sqlite3.Row) -> dict[str, str]:
    try:
        evidence = json.loads(row["evidence_json"] or "[]")
    except json.JSONDecodeError as exc:
        raise ValueError("learning_export_invalid_evidence_json") from exc
    if not isinstance(evidence, list):
        raise ValueError("learning_export_invalid_evidence_json")
    result: dict[str, str] = {}
    for index, item in enumerate(evidence):
        if not isinstance(item, dict):
            continue
        evidence_id = str(item.get("id") or "").strip()
        if evidence_id:
            result[f"evidence_{index}"] = evidence_id
    return result


def _teacher_quality(row: sqlite3.Row, evidence_ids: list[str]):
    raw = row["teacher_review_json"]
    if not raw:
        return None
    try:
        review = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("learning_export_invalid_teacher_review_json") from exc
    if not isinstance(review, dict):
        raise ValueError("learning_export_invalid_teacher_review_json")
    return evaluate_teacher_review(
        model_answer=str(row["model_answer"] or ""),
        review=review,
        evidence_ids=evidence_ids,
    )


def build_gated_export(
    *,
    review_store: LearningExportReviewStore,
) -> GatedLearningExport:
    active_store = _candidate_store()
    exported = active_store.export_approved()
    examples: list[dict[str, Any]] = []
    preflight_violations: list[str] = []

    for index, item in enumerate(exported):
        metadata = item.get("metadata") or {}
        candidate_id = str(metadata.get("candidate_id") or "")
        row = _candidate_store().candidate_context(candidate_id)
        if row is None:
            preflight_violations.append(f"example_{index}:candidate_not_found")
            continue
        review = review_store.get(candidate_id)
        if review is None:
            preflight_violations.append(f"example_{index}:export_review_required")
            continue
        if not review.privacy_safe:
            preflight_violations.append(f"example_{index}:privacy_review_required")
            continue

        provenance = _evidence_provenance(row)
        teacher_quality = _teacher_quality(row, list(provenance.values()))
        teacher_reviewed = teacher_quality is not None
        if teacher_quality is not None and not teacher_quality.accepted:
            preflight_violations.extend(
                f"example_{index}:{violation}" for violation in teacher_quality.violations
            )
            continue

        target = str(item["messages"][-1].get("content") or "")
        assistant_lower = target.casefold()
        legal_claim = any(
            token in assistant_lower
            for token in ("kanunen", "mevzuata göre", "yasal olarak", "resmî gazete")
        )
        if legal_claim and not review.evidence_reviewed:
            preflight_violations.append(f"example_{index}:legal_evidence_review_required")
            continue

        examples.append(
            {
                "messages": item["messages"],
                "metadata": {
                    "candidate_id": candidate_id,
                    "reason": row["reason"],
                    "teacher_reviewed": teacher_reviewed,
                    "teacher_quality_accepted": (
                        teacher_quality.accepted if teacher_quality is not None else None
                    ),
                    "teacher_quality_score": (
                        teacher_quality.score if teacher_quality is not None else None
                    ),
                    "teacher_quality_sha256": (
                        teacher_quality.review_sha256 if teacher_quality is not None else None
                    ),
                    "human_approved": True,
                    "contains_personal_data": False,
                    "original_model_answer": row["model_answer"],
                    "legal_provenance": provenance or None,
                    "export_reviewed_by": review.reviewed_by,
                    "export_review_reference": review.review_reference,
                    "export_reviewed_at": review.reviewed_at.isoformat(),
                },
            }
        )

    if preflight_violations:
        raise ValueError("learning_export_gate_failed:" + ",".join(preflight_violations))

    gate = validate_training_examples(examples)
    if not gate.accepted:
        raise ValueError("learning_export_gate_failed:" + ",".join(gate.violations))
    return GatedLearningExport(examples=examples, gate=gate)


review_store = LearningExportReviewStore(
    Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
)
router = APIRouter(tags=["learning-export"])


@router.post(
    "/v1/learning/export-reviews/{candidate_id}",
    response_model=ExportReview,
)
def review_candidate_for_export(candidate_id: str, payload: ExportReviewCreate):
    try:
        return review_store.save(candidate_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
