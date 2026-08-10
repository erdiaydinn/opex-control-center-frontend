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

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))


class TrainingManifest(BaseModel):
    id: str
    dataset_sha256: str
    chain_sha256: str
    example_count: int
    approved_by: str
    approval_reference: str
    parent_manifest_id: str | None = None
    parent_chain_sha256: str | None = None
    created_at: datetime


class TrainingManifestCreate(BaseModel):
    examples: list[dict[str, Any]] = Field(min_length=1)
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

    def create(self, payload: TrainingManifestCreate) -> TrainingManifest:
        gate = validate_training_examples(payload.examples)
        if not gate.accepted:
            raise ValueError("training_gate_failed:" + ",".join(gate.violations))

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
                        id, dataset_sha256, chain_sha256, example_count,
                        approved_by, approval_reference, parent_manifest_id,
                        parent_chain_sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        manifest_id,
                        gate.dataset_sha256,
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
