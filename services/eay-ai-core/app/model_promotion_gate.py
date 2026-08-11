from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .model_artifact_provenance import ModelArtifactProvenanceRegistry
from .model_artifact_registry import ModelArtifactRegistry
from .training_job_registry import TrainingJobRegistry


def _sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PromotionRequest(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    canary_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=2, max_length=180)
    approval_reference: str = Field(min_length=2, max_length=300)


class PromotionRecord(BaseModel):
    id: str
    fingerprint: str
    model_record_id: str
    artifact_sha256: str
    training_job_fingerprint: str | None
    canary_evidence_fingerprint: str
    approved_by: str
    approval_reference: str
    created_at: datetime


class ModelPromotionGate:
    """Final fail-closed gate for production status.

    Promotion is append-only evidence first, then a single local status update. The proof
    binds model artifact, training job, passing canary evidence and an explicit human approval.
    Fine-tuned models cannot reach production from caller supplied hashes alone.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.artifacts = ModelArtifactProvenanceRegistry(db_path)
        self.primary_artifacts = ModelArtifactRegistry(db_path)
        self.training_jobs = TrainingJobRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_production_promotions (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                model_record_id TEXT NOT NULL UNIQUE, artifact_sha256 TEXT NOT NULL,
                training_job_fingerprint TEXT, canary_evidence_fingerprint TEXT NOT NULL,
                approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL,
                created_at TEXT NOT NULL)"""
            )

    def promote(self, payload: PromotionRequest) -> PromotionRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            model = conn.execute("SELECT * FROM model_registry WHERE id=?", (payload.model_record_id,)).fetchone()
        if model is None:
            raise KeyError("model_not_found")
        if model["status"] != "canary":
            raise ValueError("production_promotion_requires_canary_status")
        if not model["approved_by"] or not model["approved_at"]:
            raise ValueError("production_promotion_requires_prior_human_approval")

        training_job_fingerprint = model["training_job_fingerprint"]
        if training_job_fingerprint:
            self.training_jobs.verify_model_lineage(
                fingerprint=training_job_fingerprint,
                base_model=model["base_model"],
                license_id=model["license_id"],
                training_dataset_sha256=model["training_dataset_sha256"],
                training_manifest_chain_sha256=model["training_manifest_chain_sha256"],
                eval_dataset_sha256=model["eval_dataset_sha256"],
            )
            primary_artifact = self.primary_artifacts.verify(
                artifact_sha256=model["artifact_sha256"],
                training_job_fingerprint=training_job_fingerprint,
            )
            if model["artifact_provenance_fingerprint"] != primary_artifact.provenance_fingerprint:
                raise ValueError("production_promotion_artifact_provenance_mismatch")
            self.artifacts.verify_artifact(
                artifact_sha256=model["artifact_sha256"],
                training_job_fingerprint=training_job_fingerprint,
            )
        else:
            raise ValueError("production_promotion_requires_registered_training_job")

        canary = self.artifacts.require_passing_canary(
            model_record_id=payload.model_record_id,
            fingerprint=payload.canary_evidence_fingerprint,
        )
        if canary.artifact_sha256 != model["artifact_sha256"]:
            raise ValueError("production_promotion_canary_artifact_mismatch")
        if canary.eval_dataset_sha256 != model["eval_dataset_sha256"]:
            raise ValueError("production_promotion_canary_eval_dataset_mismatch")

        canonical = {
            "model_record_id": payload.model_record_id,
            "artifact_sha256": model["artifact_sha256"],
            "artifact_provenance_fingerprint": model["artifact_provenance_fingerprint"],
            "training_job_fingerprint": training_job_fingerprint,
            "canary_evidence_fingerprint": payload.canary_evidence_fingerprint,
            "approved_by": payload.approved_by.strip(),
            "approval_reference": payload.approval_reference.strip(),
        }
        fingerprint = _sha256(canonical)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                current = conn.execute(
                    "SELECT status, artifact_sha256, artifact_provenance_fingerprint FROM model_registry WHERE id=?",
                    (payload.model_record_id,),
                ).fetchone()
                if current is None:
                    raise KeyError("model_not_found")
                if (
                    current[0] != "canary"
                    or current[1] != model["artifact_sha256"]
                    or current[2] != model["artifact_provenance_fingerprint"]
                ):
                    raise ValueError("production_promotion_stale_model_state")
                conn.execute(
                    "INSERT INTO model_production_promotions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record_id, fingerprint, payload.model_record_id, model["artifact_sha256"],
                     training_job_fingerprint, payload.canary_evidence_fingerprint,
                     payload.approved_by.strip(), payload.approval_reference.strip(),
                     created_at.isoformat()),
                )
                conn.execute(
                    "UPDATE model_registry SET status='production' WHERE id=? AND status='canary'",
                    (payload.model_record_id,),
                )
                if conn.total_changes < 2:
                    raise ValueError("production_promotion_atomic_update_failed")
            except Exception:
                conn.rollback()
                raise

        return PromotionRecord(
            id=record_id, fingerprint=fingerprint, model_record_id=payload.model_record_id,
            artifact_sha256=model["artifact_sha256"],
            training_job_fingerprint=training_job_fingerprint,
            canary_evidence_fingerprint=payload.canary_evidence_fingerprint,
            approved_by=payload.approved_by.strip(), approval_reference=payload.approval_reference.strip(),
            created_at=created_at,
        )
