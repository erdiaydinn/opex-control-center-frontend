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
from .model_registry import EvalSummary, eval_summary_fingerprint
from .release_evidence_registry import ReleaseEvaluationEvidenceRegistry
from .training_execution import TrainingExecutionRegistry
from .training_job_registry import TrainingJobRegistry


def _sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def offline_eval_fingerprint(model: sqlite3.Row) -> str:
    evals = json.loads(model["evals_json"])
    return _sha256({"model_record_id": model["id"], "artifact_sha256": model["artifact_sha256"], "artifact_provenance_fingerprint": model["artifact_provenance_fingerprint"], "eval_dataset_sha256": model["eval_dataset_sha256"], "evals": evals})


class PromotionRequest(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    canary_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    release_evaluation_evidence_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=2, max_length=180)
    approval_reference: str = Field(min_length=2, max_length=300)


class PromotionRecord(BaseModel):
    id: str
    fingerprint: str
    release_proof_fingerprint: str
    offline_eval_fingerprint: str
    release_evaluation_evidence_fingerprint: str
    historical_legal_eval_fingerprint: str
    safety_eval_fingerprint: str
    eval_dataset_sha256: str
    training_manifest_chain_sha256: str
    model_record_id: str
    artifact_sha256: str
    artifact_provenance_fingerprint: str
    training_job_fingerprint: str
    training_execution_receipt_fingerprint: str
    canary_evidence_fingerprint: str
    approved_by: str
    approval_reference: str
    created_at: datetime


class ModelPromotionGate:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.artifacts = ModelArtifactProvenanceRegistry(db_path)
        self.primary_artifacts = ModelArtifactRegistry(db_path)
        self.training_jobs = TrainingJobRegistry(db_path)
        self.training_executions = TrainingExecutionRegistry(db_path)
        self.release_evidence = ReleaseEvaluationEvidenceRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS model_production_promotions (id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE, release_proof_fingerprint TEXT, offline_eval_fingerprint TEXT, release_evaluation_evidence_fingerprint TEXT, historical_legal_eval_fingerprint TEXT, safety_eval_fingerprint TEXT, eval_dataset_sha256 TEXT, training_manifest_chain_sha256 TEXT, model_record_id TEXT NOT NULL UNIQUE, artifact_sha256 TEXT NOT NULL, artifact_provenance_fingerprint TEXT, training_job_fingerprint TEXT, training_execution_receipt_fingerprint TEXT, canary_evidence_fingerprint TEXT NOT NULL, approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL, created_at TEXT NOT NULL)""")
            existing = {row[1] for row in conn.execute("PRAGMA table_info(model_production_promotions)")}
            for name in ("release_proof_fingerprint", "offline_eval_fingerprint", "release_evaluation_evidence_fingerprint", "historical_legal_eval_fingerprint", "safety_eval_fingerprint", "eval_dataset_sha256", "training_manifest_chain_sha256", "artifact_provenance_fingerprint", "training_execution_receipt_fingerprint"):
                if name not in existing:
                    conn.execute(f"ALTER TABLE model_production_promotions ADD COLUMN {name} TEXT")

    @staticmethod
    def _record(row: sqlite3.Row) -> PromotionRecord:
        return PromotionRecord(id=row["id"], fingerprint=row["fingerprint"], release_proof_fingerprint=row["release_proof_fingerprint"], offline_eval_fingerprint=row["offline_eval_fingerprint"], release_evaluation_evidence_fingerprint=row["release_evaluation_evidence_fingerprint"], historical_legal_eval_fingerprint=row["historical_legal_eval_fingerprint"], safety_eval_fingerprint=row["safety_eval_fingerprint"], eval_dataset_sha256=row["eval_dataset_sha256"], training_manifest_chain_sha256=row["training_manifest_chain_sha256"], model_record_id=row["model_record_id"], artifact_sha256=row["artifact_sha256"], artifact_provenance_fingerprint=row["artifact_provenance_fingerprint"], training_job_fingerprint=row["training_job_fingerprint"], training_execution_receipt_fingerprint=row["training_execution_receipt_fingerprint"], canary_evidence_fingerprint=row["canary_evidence_fingerprint"], approved_by=row["approved_by"], approval_reference=row["approval_reference"], created_at=datetime.fromisoformat(row["created_at"]))

    def require_current_production(self, *, model_record_id: str) -> PromotionRecord:
        """Re-verify the immutable production proof against the live model registry head."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM model_production_promotions WHERE model_record_id=?", (model_record_id,)).fetchone()
            model = conn.execute("SELECT * FROM model_registry WHERE id=?", (model_record_id,)).fetchone()
        if row is None:
            raise KeyError("production_promotion_not_found")
        if model is None or model["status"] != "production":
            raise ValueError("production_promotion_model_not_currently_production")
        if row["artifact_sha256"] != model["artifact_sha256"] or row["artifact_provenance_fingerprint"] != model["artifact_provenance_fingerprint"]:
            raise ValueError("production_promotion_current_artifact_drift")
        if row["training_job_fingerprint"] != model["training_job_fingerprint"] or row["training_manifest_chain_sha256"] != model["training_manifest_chain_sha256"] or row["eval_dataset_sha256"] != model["eval_dataset_sha256"]:
            raise ValueError("production_promotion_current_lineage_drift")
        current_offline = offline_eval_fingerprint(model)
        if row["offline_eval_fingerprint"] != current_offline:
            raise ValueError("production_promotion_current_offline_eval_drift")
        evidence = self.release_evidence.verify_for_lineage(fingerprint=row["release_evaluation_evidence_fingerprint"], eval_dataset_sha256=row["eval_dataset_sha256"], training_manifest_chain_sha256=row["training_manifest_chain_sha256"])
        if evidence.historical_legal_fingerprint != row["historical_legal_eval_fingerprint"] or evidence.safety_eval_fingerprint != row["safety_eval_fingerprint"]:
            raise ValueError("production_promotion_release_evidence_drift")
        self.training_jobs.verify_model_lineage(fingerprint=row["training_job_fingerprint"], base_model=model["base_model"], license_id=model["license_id"], training_dataset_sha256=model["training_dataset_sha256"], training_manifest_chain_sha256=row["training_manifest_chain_sha256"], eval_dataset_sha256=row["eval_dataset_sha256"])
        self.artifacts.verify_artifact(artifact_sha256=row["artifact_sha256"], training_job_fingerprint=row["training_job_fingerprint"])
        receipt = self.training_executions.require_verified_artifact(
            training_job_fingerprint=row["training_job_fingerprint"],
            artifact_sha256=row["artifact_sha256"],
        )
        if row["training_execution_receipt_fingerprint"] != receipt.fingerprint:
            raise ValueError("production_promotion_training_execution_receipt_drift")
        release_proof = _sha256({"model_record_id": model_record_id, "training_job_fingerprint": row["training_job_fingerprint"], "training_manifest_chain_sha256": row["training_manifest_chain_sha256"], "artifact_sha256": row["artifact_sha256"], "artifact_provenance_fingerprint": row["artifact_provenance_fingerprint"], "training_execution_receipt_fingerprint": receipt.fingerprint, "eval_dataset_sha256": row["eval_dataset_sha256"], "offline_eval_fingerprint": current_offline, "release_evaluation_evidence_fingerprint": row["release_evaluation_evidence_fingerprint"], "historical_legal_eval_fingerprint": row["historical_legal_eval_fingerprint"], "safety_eval_fingerprint": row["safety_eval_fingerprint"], "canary_evidence_fingerprint": row["canary_evidence_fingerprint"], "approved_by": row["approved_by"], "approval_reference": row["approval_reference"]})
        if release_proof != row["release_proof_fingerprint"] or _sha256({"kind": "production_promotion", "release_proof": release_proof}) != row["fingerprint"]:
            raise ValueError("production_promotion_proof_fingerprint_drift")
        return self._record(row)

    def promote(self, payload: PromotionRequest) -> PromotionRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            model = conn.execute("SELECT * FROM model_registry WHERE id=?", (payload.model_record_id,)).fetchone()
        if model is None: raise KeyError("model_not_found")
        if model["status"] != "canary": raise ValueError("production_promotion_requires_canary_status")
        if not model["approved_by"] or not model["approved_at"]: raise ValueError("production_promotion_requires_prior_human_approval")
        eval_dataset_sha256 = str(model["eval_dataset_sha256"] or "")
        training_manifest_chain_sha256 = str(model["training_manifest_chain_sha256"] or "")
        if not eval_dataset_sha256 or not training_manifest_chain_sha256: raise ValueError("production_promotion_requires_complete_eval_lineage")
        release_evidence = self.release_evidence.verify_for_lineage(fingerprint=payload.release_evaluation_evidence_fingerprint, eval_dataset_sha256=eval_dataset_sha256, training_manifest_chain_sha256=training_manifest_chain_sha256)
        training_job_fingerprint = model["training_job_fingerprint"]
        if not training_job_fingerprint: raise ValueError("production_promotion_requires_registered_training_job")
        self.training_jobs.verify_model_lineage(fingerprint=training_job_fingerprint, base_model=model["base_model"], license_id=model["license_id"], training_dataset_sha256=model["training_dataset_sha256"], training_manifest_chain_sha256=training_manifest_chain_sha256, eval_dataset_sha256=eval_dataset_sha256)
        primary_artifact = self.primary_artifacts.verify(artifact_sha256=model["artifact_sha256"], training_job_fingerprint=training_job_fingerprint)
        artifact_provenance_fingerprint = model["artifact_provenance_fingerprint"]
        if artifact_provenance_fingerprint != primary_artifact.provenance_fingerprint: raise ValueError("production_promotion_artifact_provenance_mismatch")
        self.artifacts.verify_artifact(artifact_sha256=model["artifact_sha256"], training_job_fingerprint=training_job_fingerprint)
        training_execution_receipt = self.training_executions.require_verified_artifact(
            training_job_fingerprint=training_job_fingerprint,
            artifact_sha256=model["artifact_sha256"],
        )
        canary = self.artifacts.require_passing_canary(model_record_id=payload.model_record_id, fingerprint=payload.canary_evidence_fingerprint)
        if canary.artifact_sha256 != model["artifact_sha256"]: raise ValueError("production_promotion_canary_artifact_mismatch")
        if canary.eval_dataset_sha256 != eval_dataset_sha256: raise ValueError("production_promotion_canary_eval_dataset_mismatch")
        stored_eval_fingerprint = eval_summary_fingerprint(
            EvalSummary.model_validate(json.loads(model["evals_json"]))
        )
        if model["offline_eval_fingerprint"] != stored_eval_fingerprint:
            raise ValueError("model_offline_eval_provenance_mismatch")
        eval_fingerprint = offline_eval_fingerprint(model)
        release_proof = _sha256({"model_record_id": payload.model_record_id, "training_job_fingerprint": training_job_fingerprint, "training_manifest_chain_sha256": training_manifest_chain_sha256, "artifact_sha256": model["artifact_sha256"], "artifact_provenance_fingerprint": artifact_provenance_fingerprint, "training_execution_receipt_fingerprint": training_execution_receipt.fingerprint, "eval_dataset_sha256": eval_dataset_sha256, "offline_eval_fingerprint": eval_fingerprint, "release_evaluation_evidence_fingerprint": release_evidence.fingerprint, "historical_legal_eval_fingerprint": release_evidence.historical_legal_fingerprint, "safety_eval_fingerprint": release_evidence.safety_eval_fingerprint, "canary_evidence_fingerprint": payload.canary_evidence_fingerprint, "approved_by": payload.approved_by.strip(), "approval_reference": payload.approval_reference.strip()})
        fingerprint = _sha256({"kind": "production_promotion", "release_proof": release_proof})
        record_id, created_at = str(uuid.uuid4()), datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE"); conn.row_factory = sqlite3.Row
                current = conn.execute("SELECT * FROM model_registry WHERE id=?", (payload.model_record_id,)).fetchone()
                if current is None: raise KeyError("model_not_found")
                if current["status"] != "canary" or current["artifact_sha256"] != model["artifact_sha256"] or current["artifact_provenance_fingerprint"] != artifact_provenance_fingerprint: raise ValueError("production_promotion_stale_model_state")
                if str(current["eval_dataset_sha256"] or "") != eval_dataset_sha256: raise ValueError("production_promotion_stale_eval_dataset")
                if str(current["training_manifest_chain_sha256"] or "") != training_manifest_chain_sha256: raise ValueError("production_promotion_stale_training_manifest")
                current_stored_eval = eval_summary_fingerprint(
                    EvalSummary.model_validate(json.loads(current["evals_json"]))
                )
                if current["offline_eval_fingerprint"] != current_stored_eval:
                    raise ValueError("production_promotion_stale_offline_eval")
                if offline_eval_fingerprint(current) != eval_fingerprint:
                    raise ValueError("production_promotion_stale_offline_eval")
                self.release_evidence.verify_for_lineage(fingerprint=release_evidence.fingerprint, eval_dataset_sha256=eval_dataset_sha256, training_manifest_chain_sha256=training_manifest_chain_sha256)
                conn.execute("INSERT INTO model_production_promotions(id,fingerprint,release_proof_fingerprint,offline_eval_fingerprint,release_evaluation_evidence_fingerprint,historical_legal_eval_fingerprint,safety_eval_fingerprint,eval_dataset_sha256,training_manifest_chain_sha256,model_record_id,artifact_sha256,artifact_provenance_fingerprint,training_job_fingerprint,training_execution_receipt_fingerprint,canary_evidence_fingerprint,approved_by,approval_reference,created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (record_id,fingerprint,release_proof,eval_fingerprint,release_evidence.fingerprint,release_evidence.historical_legal_fingerprint,release_evidence.safety_eval_fingerprint,eval_dataset_sha256,training_manifest_chain_sha256,payload.model_record_id,model["artifact_sha256"],artifact_provenance_fingerprint,training_job_fingerprint,training_execution_receipt.fingerprint,payload.canary_evidence_fingerprint,payload.approved_by.strip(),payload.approval_reference.strip(),created_at.isoformat()))
                updated = conn.execute("UPDATE model_registry SET status='production' WHERE id=? AND status='canary'", (payload.model_record_id,))
                if updated.rowcount != 1: raise ValueError("production_promotion_atomic_update_failed")
            except Exception:
                conn.rollback(); raise
        return PromotionRecord(id=record_id,fingerprint=fingerprint,release_proof_fingerprint=release_proof,offline_eval_fingerprint=eval_fingerprint,release_evaluation_evidence_fingerprint=release_evidence.fingerprint,historical_legal_eval_fingerprint=release_evidence.historical_legal_fingerprint,safety_eval_fingerprint=release_evidence.safety_eval_fingerprint,eval_dataset_sha256=eval_dataset_sha256,training_manifest_chain_sha256=training_manifest_chain_sha256,model_record_id=payload.model_record_id,artifact_sha256=model["artifact_sha256"],artifact_provenance_fingerprint=artifact_provenance_fingerprint,training_job_fingerprint=training_job_fingerprint,training_execution_receipt_fingerprint=training_execution_receipt.fingerprint,canary_evidence_fingerprint=payload.canary_evidence_fingerprint,approved_by=payload.approved_by.strip(),approval_reference=payload.approval_reference.strip(),created_at=created_at)
