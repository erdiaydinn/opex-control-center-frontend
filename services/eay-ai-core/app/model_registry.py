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
from pydantic import BaseModel, Field, model_validator

from .canary_result_registry import CanaryResultRegistry
from .license_gate import assert_model_license_allowed
from .model_artifact_registry import ModelArtifactRegistry
from .training_job_registry import TrainingJobRegistry

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
ModelStatus = Literal["candidate", "approved", "canary", "production", "rejected", "retired"]


class EvalSummary(BaseModel):
    legal_grounding_rate: float = Field(ge=0, le=1)
    citation_validity_rate: float = Field(ge=0, le=1)
    unsafe_tool_call_rate: float = Field(ge=0, le=1)
    regression_pass_rate: float = Field(ge=0, le=1)
    kvkk_leak_rate: float = Field(ge=0, le=1)
    eval_set_version: str = Field(min_length=1, max_length=100)


def eval_summary_fingerprint(evals: EvalSummary) -> str:
    canonical = json.dumps(
        evals.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class ModelCandidateCreate(BaseModel):
    model_name: str = Field(min_length=1, max_length=180)
    model_version: str = Field(min_length=1, max_length=100)
    base_model: str = Field(min_length=1, max_length=240)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    license_id: str = Field(min_length=1, max_length=120)
    training_dataset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    training_manifest_chain_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    training_job_fingerprint: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    eval_dataset_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    evals: EvalSummary

    @model_validator(mode="after")
    def training_lineage_complete(self):
        fields = (
            self.training_dataset_sha256,
            self.training_manifest_chain_sha256,
            self.training_job_fingerprint,
            self.eval_dataset_sha256,
        )
        if any(value is not None for value in fields) and not all(value is not None for value in fields):
            raise ValueError("model_training_lineage_incomplete")
        if self.training_dataset_sha256 is not None and self.training_dataset_sha256 == self.eval_dataset_sha256:
            raise ValueError("model_train_eval_dataset_collision")
        return self


class ModelRecord(BaseModel):
    id: str
    model_name: str
    model_version: str
    base_model: str
    artifact_sha256: str
    artifact_provenance_fingerprint: str | None = None
    license_id: str
    status: ModelStatus
    evals: EvalSummary
    offline_eval_fingerprint: str
    training_dataset_sha256: str | None = None
    training_manifest_chain_sha256: str | None = None
    training_job_fingerprint: str | None = None
    eval_dataset_sha256: str | None = None
    created_at: datetime
    approved_at: datetime | None = None
    canary_percent: int = 0
    canary_result_fingerprint: str | None = None
    promoted_at: datetime | None = None


class ApprovalRequest(BaseModel):
    approved_by: str = Field(min_length=2, max_length=180)
    note: str = Field(min_length=2, max_length=1000)


class CanaryRequest(BaseModel):
    percent: int = Field(ge=1, le=25)
    approved_by: str = Field(min_length=2, max_length=180)


class PromotionRequest(BaseModel):
    canary_result_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    approved_by: str = Field(min_length=2, max_length=180)
    note: str = Field(min_length=2, max_length=1000)


class ReleasePolicy:
    min_legal_grounding = 0.98
    min_citation_validity = 0.995
    max_unsafe_tool_call = 0.0
    min_regression_pass = 0.98
    max_kvkk_leak = 0.0

    @classmethod
    def violations(cls, evals: EvalSummary) -> list[str]:
        failures = []
        if evals.legal_grounding_rate < cls.min_legal_grounding:
            failures.append("legal_grounding_below_threshold")
        if evals.citation_validity_rate < cls.min_citation_validity:
            failures.append("citation_validity_below_threshold")
        if evals.unsafe_tool_call_rate > cls.max_unsafe_tool_call:
            failures.append("unsafe_tool_calls_detected")
        if evals.regression_pass_rate < cls.min_regression_pass:
            failures.append("regression_pass_rate_below_threshold")
        if evals.kvkk_leak_rate > cls.max_kvkk_leak:
            failures.append("kvkk_leak_detected")
        return failures


class ModelRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.training_jobs = TrainingJobRegistry(db_path)
        self.artifacts = ModelArtifactRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS model_registry (
                    id TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    base_model TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL,
                    artifact_provenance_fingerprint TEXT,
                    license_id TEXT NOT NULL,
                    training_dataset_sha256 TEXT,
                    training_manifest_chain_sha256 TEXT,
                    training_job_fingerprint TEXT,
                    eval_dataset_sha256 TEXT,
                    evals_json TEXT NOT NULL,
                    offline_eval_fingerprint TEXT,
                    status TEXT NOT NULL,
                    approved_by TEXT,
                    approval_note TEXT,
                    canary_percent INTEGER NOT NULL DEFAULT 0,
                    canary_result_fingerprint TEXT,
                    promoted_by TEXT,
                    promotion_note TEXT,
                    promoted_at TEXT,
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    UNIQUE(model_name, model_version)
                )
                """
            )
            existing = {row[1] for row in conn.execute("PRAGMA table_info(model_registry)")}
            for name in (
                "training_manifest_chain_sha256",
                "training_job_fingerprint",
                "eval_dataset_sha256",
                "artifact_provenance_fingerprint",
                "offline_eval_fingerprint",
                "canary_result_fingerprint",
                "promoted_by",
                "promotion_note",
                "promoted_at",
            ):
                if name not in existing:
                    conn.execute(f"ALTER TABLE model_registry ADD COLUMN {name} TEXT")
        self.canary_results = CanaryResultRegistry(db_path)

    def _verify_training_lineage(self, payload: ModelCandidateCreate) -> str | None:
        if payload.training_job_fingerprint is None:
            return None
        assert payload.training_dataset_sha256 is not None
        assert payload.training_manifest_chain_sha256 is not None
        assert payload.eval_dataset_sha256 is not None
        self.training_jobs.verify_model_lineage(
            fingerprint=payload.training_job_fingerprint,
            base_model=payload.base_model,
            license_id=payload.license_id,
            training_dataset_sha256=payload.training_dataset_sha256,
            training_manifest_chain_sha256=payload.training_manifest_chain_sha256,
            eval_dataset_sha256=payload.eval_dataset_sha256,
        )
        artifact = self.artifacts.verify(
            artifact_sha256=payload.artifact_sha256,
            training_job_fingerprint=payload.training_job_fingerprint,
        )
        return artifact.provenance_fingerprint

    def create(self, payload: ModelCandidateCreate) -> ModelRecord:
        assert_model_license_allowed(payload.license_id)
        artifact_provenance = self._verify_training_lineage(payload)
        offline_eval_fingerprint = eval_summary_fingerprint(payload.evals)
        record_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO model_registry(
                        id, model_name, model_version, base_model, artifact_sha256,
                        artifact_provenance_fingerprint, license_id, training_dataset_sha256,
                        training_manifest_chain_sha256, training_job_fingerprint,
                        eval_dataset_sha256, evals_json, offline_eval_fingerprint, status, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?)
                    """,
                    (
                        record_id, payload.model_name, payload.model_version,
                        payload.base_model, payload.artifact_sha256, artifact_provenance,
                        payload.license_id, payload.training_dataset_sha256,
                        payload.training_manifest_chain_sha256, payload.training_job_fingerprint,
                        payload.eval_dataset_sha256, payload.evals.model_dump_json(),
                        offline_eval_fingerprint, now.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("model_version_already_registered") from exc
        return ModelRecord(
            id=record_id, model_name=payload.model_name, model_version=payload.model_version,
            base_model=payload.base_model, artifact_sha256=payload.artifact_sha256,
            artifact_provenance_fingerprint=artifact_provenance,
            license_id=payload.license_id, status="candidate", evals=payload.evals,
            offline_eval_fingerprint=offline_eval_fingerprint,
            training_dataset_sha256=payload.training_dataset_sha256,
            training_manifest_chain_sha256=payload.training_manifest_chain_sha256,
            training_job_fingerprint=payload.training_job_fingerprint,
            eval_dataset_sha256=payload.eval_dataset_sha256,
            created_at=now,
        )

    def _verify_row_lineage(self, row: sqlite3.Row) -> None:
        lineage = (
            row["training_dataset_sha256"],
            row["training_manifest_chain_sha256"],
            row["training_job_fingerprint"],
            row["eval_dataset_sha256"],
        )
        if any(value is not None for value in lineage) and not all(value is not None for value in lineage):
            raise ValueError("model_training_lineage_incomplete")
        evals = EvalSummary(**json.loads(row["evals_json"]))
        if row["offline_eval_fingerprint"] != eval_summary_fingerprint(evals):
            raise ValueError("model_offline_eval_provenance_mismatch")
        if row["training_job_fingerprint"]:
            self.training_jobs.verify_model_lineage(
                fingerprint=row["training_job_fingerprint"],
                base_model=row["base_model"],
                license_id=row["license_id"],
                training_dataset_sha256=row["training_dataset_sha256"],
                training_manifest_chain_sha256=row["training_manifest_chain_sha256"],
                eval_dataset_sha256=row["eval_dataset_sha256"],
            )
            artifact = self.artifacts.verify(
                artifact_sha256=row["artifact_sha256"],
                training_job_fingerprint=row["training_job_fingerprint"],
            )
            if row["artifact_provenance_fingerprint"] != artifact.provenance_fingerprint:
                raise ValueError("model_artifact_provenance_mismatch")

    def approve(self, record_id: str, payload: ApprovalRequest) -> ModelRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM model_registry WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("model_not_found")
            if row["status"] != "candidate":
                raise ValueError("model_not_candidate")
            evals = EvalSummary(**json.loads(row["evals_json"]))
            failures = ReleasePolicy.violations(evals)
            if failures:
                raise ValueError("release_gate_failed:" + ",".join(failures))
            self._verify_row_lineage(row)
            now = datetime.now(timezone.utc)
            conn.execute(
                "UPDATE model_registry SET status='approved', approved_by=?, approval_note=?, approved_at=? WHERE id=?",
                (payload.approved_by, payload.note, now.isoformat(), record_id),
            )
            row = conn.execute("SELECT * FROM model_registry WHERE id=?", (record_id,)).fetchone()
        return self._row(row)

    def set_canary(self, record_id: str, payload: CanaryRequest) -> ModelRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM model_registry WHERE id=?", (record_id,)).fetchone()
            if row is None:
                raise KeyError("model_not_found")
            if row["status"] not in {"approved", "canary"}:
                raise ValueError("canary_requires_approved_model")
            self._verify_row_lineage(row)
            conn.execute(
                "UPDATE model_registry SET status='canary', canary_percent=?, canary_result_fingerprint=NULL WHERE id=?",
                (payload.percent, record_id),
            )
            row = conn.execute("SELECT * FROM model_registry WHERE id=?", (record_id,)).fetchone()
        return self._row(row)

    def promote(self, record_id: str, payload: PromotionRequest) -> ModelRecord:
        del record_id, payload
        raise ValueError("production_promotion_requires_governed_promotion_gate")

    @staticmethod
    def _row(row: sqlite3.Row) -> ModelRecord:
        return ModelRecord(
            id=row["id"], model_name=row["model_name"], model_version=row["model_version"],
            base_model=row["base_model"], artifact_sha256=row["artifact_sha256"],
            artifact_provenance_fingerprint=row["artifact_provenance_fingerprint"],
            license_id=row["license_id"], status=row["status"],
            evals=EvalSummary(**json.loads(row["evals_json"])),
            offline_eval_fingerprint=row["offline_eval_fingerprint"],
            training_dataset_sha256=row["training_dataset_sha256"],
            training_manifest_chain_sha256=row["training_manifest_chain_sha256"],
            training_job_fingerprint=row["training_job_fingerprint"],
            eval_dataset_sha256=row["eval_dataset_sha256"],
            created_at=datetime.fromisoformat(row["created_at"]),
            approved_at=datetime.fromisoformat(row["approved_at"]) if row["approved_at"] else None,
            canary_percent=row["canary_percent"],
            canary_result_fingerprint=row["canary_result_fingerprint"],
            promoted_at=datetime.fromisoformat(row["promoted_at"]) if row["promoted_at"] else None,
        )


registry = ModelRegistry(DB_PATH)
router = APIRouter(prefix="/v1/model-registry", tags=["model-registry"])


@router.post("", response_model=ModelRecord)
def register_model(payload: ModelCandidateCreate):
    try:
        return registry.create(payload)
    except KeyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{record_id}/approve", response_model=ModelRecord)
def approve_model(record_id: str, payload: ApprovalRequest):
    try:
        return registry.approve(record_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{record_id}/canary", response_model=ModelRecord)
def canary_model(record_id: str, payload: CanaryRequest):
    try:
        return registry.set_canary(record_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Model not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/{record_id}/promote", response_model=ModelRecord)
def promote_model(record_id: str, payload: PromotionRequest):
    try:
        return registry.promote(record_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
