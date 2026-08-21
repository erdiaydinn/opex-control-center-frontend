from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .training_job_registry import TrainingJobRegistry


class ArtifactRegistration(BaseModel):
    training_job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_format: str = Field(min_length=2, max_length=80)
    local_path_reference: str = Field(min_length=2, max_length=500)
    produced_by: str = Field(min_length=2, max_length=180)
    approval_reference: str = Field(min_length=2, max_length=300)


class ArtifactRecord(BaseModel):
    id: str
    training_job_fingerprint: str
    artifact_sha256: str
    artifact_format: str
    local_path_reference: str
    produced_by: str
    approval_reference: str
    provenance_fingerprint: str
    created_at: datetime


def artifact_provenance_fingerprint(payload: ArtifactRegistration) -> str:
    canonical = json.dumps(
        {
            "training_job_fingerprint": payload.training_job_fingerprint,
            "artifact_sha256": payload.artifact_sha256,
            "artifact_format": payload.artifact_format.strip().lower(),
            "local_path_reference": payload.local_path_reference.strip(),
            "produced_by": payload.produced_by.strip(),
            "approval_reference": payload.approval_reference.strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelArtifactRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.training_jobs = TrainingJobRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_artifact_registry (
                id TEXT PRIMARY KEY,
                training_job_fingerprint TEXT NOT NULL,
                artifact_sha256 TEXT NOT NULL UNIQUE,
                artifact_format TEXT NOT NULL,
                local_path_reference TEXT NOT NULL,
                produced_by TEXT NOT NULL,
                approval_reference TEXT NOT NULL,
                provenance_fingerprint TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL)"""
            )

    def register(self, payload: ArtifactRegistration) -> ArtifactRecord:
        self.training_jobs.get_by_fingerprint(payload.training_job_fingerprint)
        provenance = artifact_provenance_fingerprint(payload)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO model_artifact_registry(
                    id,training_job_fingerprint,artifact_sha256,artifact_format,
                    local_path_reference,produced_by,approval_reference,
                    provenance_fingerprint,created_at) VALUES (?,?,?,?,?,?,?,?,?)""",
                    (
                        record_id,
                        payload.training_job_fingerprint,
                        payload.artifact_sha256,
                        payload.artifact_format,
                        payload.local_path_reference,
                        payload.produced_by,
                        payload.approval_reference,
                        provenance,
                        created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("model_artifact_already_registered") from exc
        return ArtifactRecord(
            id=record_id,
            training_job_fingerprint=payload.training_job_fingerprint,
            artifact_sha256=payload.artifact_sha256,
            artifact_format=payload.artifact_format,
            local_path_reference=payload.local_path_reference,
            produced_by=payload.produced_by,
            approval_reference=payload.approval_reference,
            provenance_fingerprint=provenance,
            created_at=created_at,
        )

    def get_by_sha256(self, artifact_sha256: str) -> ArtifactRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM model_artifact_registry WHERE artifact_sha256=?",
                (artifact_sha256,),
            ).fetchone()
        if row is None:
            raise KeyError("model_artifact_not_found")
        return ArtifactRecord(
            id=row["id"],
            training_job_fingerprint=row["training_job_fingerprint"],
            artifact_sha256=row["artifact_sha256"],
            artifact_format=row["artifact_format"],
            local_path_reference=row["local_path_reference"],
            produced_by=row["produced_by"],
            approval_reference=row["approval_reference"],
            provenance_fingerprint=row["provenance_fingerprint"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def verify(self, *, artifact_sha256: str, training_job_fingerprint: str) -> ArtifactRecord:
        record = self.get_by_sha256(artifact_sha256)
        if record.training_job_fingerprint != training_job_fingerprint:
            raise ValueError("model_artifact_training_job_mismatch")
        return record
