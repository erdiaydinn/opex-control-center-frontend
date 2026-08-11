from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .training_gate import validate_training_examples
from .training_integrity import validate_split_leakage

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))


class TrainingManifest(BaseModel):
    id: str
    dataset_sha256: str
    dataset_integrity_sha256: str
    quality_lineage_sha256: str
    eval_dataset_sha256: str | None = None
    eval_example_count: int = 0
    chain_sha256: str
    example_count: int
    approved_by: str
    approval_reference: str
    parent_manifest_id: str | None = None
    parent_chain_sha256: str | None = None
    created_at: datetime


class TrainingManifestCreate(BaseModel):
    examples: list[dict[str, Any]] = Field(min_length=1)
    eval_examples: list[dict[str, Any]] = Field(default_factory=list)
    approved_by: str = Field(min_length=2, max_length=200)
    approval_reference: str = Field(min_length=2, max_length=300)
    parent_manifest_id: str | None = Field(default=None, max_length=64)


class TrainingManifestStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS training_dataset_manifests (
                    id TEXT PRIMARY KEY,
                    dataset_sha256 TEXT NOT NULL UNIQUE,
                    dataset_integrity_sha256 TEXT,
                    quality_lineage_sha256 TEXT,
                    eval_dataset_sha256 TEXT,
                    eval_example_count INTEGER NOT NULL DEFAULT 0,
                    chain_sha256 TEXT NOT NULL UNIQUE,
                    example_count INTEGER NOT NULL,
                    approved_by TEXT NOT NULL,
                    approval_reference TEXT NOT NULL,
                    parent_manifest_id TEXT,
                    parent_chain_sha256 TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            existing = {row[1] for row in conn.execute("PRAGMA table_info(training_dataset_manifests)")}
            migrations = {
                "dataset_integrity_sha256": "TEXT",
                "quality_lineage_sha256": "TEXT",
                "eval_dataset_sha256": "TEXT",
                "eval_example_count": "INTEGER NOT NULL DEFAULT 0",
            }
            for name, sql_type in migrations.items():
                if name not in existing:
                    conn.execute(
                        f"ALTER TABLE training_dataset_manifests ADD COLUMN {name} {sql_type}"
                    )

    def create(self, payload: TrainingManifestCreate) -> TrainingManifest:
        gate = validate_training_examples(payload.examples)
        if not gate.accepted:
            raise ValueError("training_gate_failed:" + ",".join(gate.violations))
        if not gate.integrity_sha256:
            raise ValueError("training_integrity_fingerprint_required")

        eval_gate = None
        eval_dataset_sha = None
        if payload.eval_examples:
            eval_gate = validate_training_examples(payload.eval_examples)
            if not eval_gate.accepted:
                raise ValueError("eval_gate_failed:" + ",".join(eval_gate.violations))
            leakage = validate_split_leakage(payload.examples, payload.eval_examples)
            if leakage:
                raise ValueError("training_eval_leakage:" + ",".join(leakage))
            eval_dataset_sha = eval_gate.dataset_sha256

        quality_material = "|".join(
            [
                *gate.quality_fingerprints,
                *gate.teacher_quality_fingerprints,
            ]
        )
        quality_lineage_sha = hashlib.sha256(quality_material.encode("utf-8")).hexdigest()

        parent_chain = None
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            if payload.parent_manifest_id:
                parent = conn.execute(
                    "SELECT * FROM training_dataset_manifests WHERE id=?",
                    (payload.parent_manifest_id,),
                ).fetchone()
                if parent is None:
                    raise KeyError("parent_manifest_not_found")
                parent_chain = parent["chain_sha256"]

            chain_material = "|".join(
                [
                    parent_chain or "ROOT",
                    gate.dataset_sha256,
                    gate.integrity_sha256,
                    quality_lineage_sha,
                    eval_dataset_sha or "NO_EVAL",
                    payload.approved_by,
                    payload.approval_reference,
                ]
            )
            chain_sha = hashlib.sha256(chain_material.encode("utf-8")).hexdigest()
            manifest_id = str(uuid.uuid4())
            created_at = datetime.now(timezone.utc)
            try:
                conn.execute(
                    """
                    INSERT INTO training_dataset_manifests(
                        id, dataset_sha256, dataset_integrity_sha256, quality_lineage_sha256,
                        eval_dataset_sha256, eval_example_count, chain_sha256, example_count,
                        approved_by, approval_reference, parent_manifest_id,
                        parent_chain_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest_id,
                        gate.dataset_sha256,
                        gate.integrity_sha256,
                        quality_lineage_sha,
                        eval_dataset_sha,
                        len(payload.eval_examples),
                        chain_sha,
                        gate.example_count,
                        payload.approved_by,
                        payload.approval_reference,
                        payload.parent_manifest_id,
                        parent_chain,
                        created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("dataset_manifest_already_exists") from exc

        return TrainingManifest(
            id=manifest_id,
            dataset_sha256=gate.dataset_sha256,
            dataset_integrity_sha256=gate.integrity_sha256,
            quality_lineage_sha256=quality_lineage_sha,
            eval_dataset_sha256=eval_dataset_sha,
            eval_example_count=len(payload.eval_examples),
            chain_sha256=chain_sha,
            example_count=gate.example_count,
            approved_by=payload.approved_by,
            approval_reference=payload.approval_reference,
            parent_manifest_id=payload.parent_manifest_id,
            parent_chain_sha256=parent_chain,
            created_at=created_at,
        )


store = TrainingManifestStore(DB_PATH)
router = APIRouter(prefix="/v1/training-manifests", tags=["training-manifests"])


@router.post("", response_model=TrainingManifest)
def create_manifest(payload: TrainingManifestCreate):
    try:
        return store.create(payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
