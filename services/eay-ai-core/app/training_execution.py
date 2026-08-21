from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from .training_gate import canonical_dataset_sha256
from .training_job_registry import TrainingJobRegistry
from .training_job_spec import TrainingJobSpec, training_job_spec_from_mapping


_OFFLINE_ENV = {
    "HF_HUB_OFFLINE": "1",
    "TRANSFORMERS_OFFLINE": "1",
    "HF_DATASETS_OFFLINE": "1",
    "WANDB_DISABLED": "true",
    "TOKENIZERS_PARALLELISM": "false",
}


def _canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    if path.is_symlink():
        raise ValueError("training_execution_symlink_not_allowed")
    if not path.is_file():
        raise ValueError("training_execution_file_required")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_path(path: Path) -> str:
    """Hash one immutable local model/artifact path without trusting metadata.

    Directory hashes bind both relative file names and file digests. Symlinks are
    rejected so a previously reviewed tree cannot be redirected after planning.
    """

    resolved = path.resolve(strict=True)
    if path.is_symlink() or resolved.is_symlink():
        raise ValueError("training_execution_symlink_not_allowed")
    if resolved.is_file():
        return sha256_file(resolved)
    if not resolved.is_dir():
        raise ValueError("training_execution_path_must_be_file_or_directory")

    files = sorted(item for item in resolved.rglob("*") if item.is_file())
    if not files:
        raise ValueError("training_execution_empty_directory")

    digest = hashlib.sha256()
    for item in files:
        if item.is_symlink():
            raise ValueError("training_execution_symlink_not_allowed")
        relative = item.relative_to(resolved).as_posix().encode("utf-8")
        file_digest = bytes.fromhex(sha256_file(item))
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(file_digest)
    return digest.hexdigest()


def dataset_sha256_from_file(path: Path) -> str:
    resolved = path.resolve(strict=True)
    if path.is_symlink() or resolved.is_symlink() or not resolved.is_file():
        raise ValueError("training_execution_dataset_file_required")
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("training_execution_dataset_invalid_json") from exc
    if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
        raise ValueError("training_execution_dataset_must_be_example_list")
    return canonical_dataset_sha256(payload)


class TrainingExecutionRequest(BaseModel):
    training_job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    base_model_path: str = Field(min_length=1, max_length=1000)
    training_dataset_path: str = Field(min_length=1, max_length=1000)
    eval_dataset_path: str = Field(min_length=1, max_length=1000)
    output_path: str = Field(min_length=1, max_length=1000)
    requested_by: str = Field(min_length=2, max_length=180)
    execution_reference: str = Field(min_length=2, max_length=300)


class TrainingExecutionPlan(BaseModel):
    id: str
    fingerprint: str
    training_job_fingerprint: str
    method: str
    base_model_path: str
    base_model_sha256: str
    training_dataset_path: str
    training_dataset_sha256: str
    eval_dataset_path: str
    eval_dataset_sha256: str
    output_path: str
    hyperparameters: dict[str, Any]
    offline_environment: dict[str, str]
    local_only: bool
    allow_remote_code: bool
    allow_network_during_training: bool
    requested_by: str
    execution_reference: str
    created_at: datetime


class TrainingExecutionReceiptCreate(BaseModel):
    plan_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    executor: str = Field(min_length=2, max_length=180)
    execution_reference: str = Field(min_length=2, max_length=300)


class TrainingExecutionReceipt(BaseModel):
    id: str
    fingerprint: str
    plan_fingerprint: str
    training_job_fingerprint: str
    artifact_path: str
    artifact_sha256: str
    executor: str
    execution_reference: str
    created_at: datetime


class TrainingExecutionRegistry:
    """Immutable bridge from reviewed training job to observed local artifact.

    This registry never runs a model training process itself. It prepares a
    fail-closed local/offline execution plan and, after the external GPU/CPU
    worker finishes, hashes the actual output on disk before accepting a receipt.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.training_jobs = TrainingJobRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS training_execution_plans (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    training_job_fingerprint TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    requested_by TEXT NOT NULL,
                    execution_reference TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS training_execution_receipts (
                    id TEXT PRIMARY KEY,
                    fingerprint TEXT NOT NULL UNIQUE,
                    plan_fingerprint TEXT NOT NULL UNIQUE,
                    training_job_fingerprint TEXT NOT NULL,
                    artifact_path TEXT NOT NULL,
                    artifact_sha256 TEXT NOT NULL UNIQUE,
                    executor TEXT NOT NULL,
                    execution_reference TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    @staticmethod
    def _resolved_input(path: str, label: str) -> Path:
        candidate = Path(path).expanduser()
        try:
            resolved = candidate.resolve(strict=True)
        except FileNotFoundError as exc:
            raise ValueError(f"training_execution_{label}_not_found") from exc
        if candidate.is_symlink() or resolved.is_symlink():
            raise ValueError("training_execution_symlink_not_allowed")
        return resolved

    @staticmethod
    def _resolved_output(path: str) -> Path:
        candidate = Path(path).expanduser()
        resolved = candidate.resolve(strict=False)
        if candidate.is_symlink():
            raise ValueError("training_execution_symlink_not_allowed")
        if resolved.exists():
            if resolved.is_file() or any(resolved.iterdir()):
                raise ValueError("training_execution_output_must_be_absent_or_empty")
        return resolved

    @staticmethod
    def _hyperparameters(spec: TrainingJobSpec) -> dict[str, Any]:
        return {
            "job_version": spec.job_version,
            "seed": spec.seed,
            "epochs": spec.epochs,
            "learning_rate": spec.learning_rate,
            "batch_size": spec.batch_size,
            "gradient_accumulation_steps": spec.gradient_accumulation_steps,
            "max_seq_length": spec.max_seq_length,
            "lora_rank": spec.lora_rank,
            "lora_alpha": spec.lora_alpha,
            "lora_dropout": spec.lora_dropout,
            "precision": spec.precision,
        }

    def create_plan(self, payload: TrainingExecutionRequest) -> TrainingExecutionPlan:
        job = self.training_jobs.get_by_fingerprint(payload.training_job_fingerprint)
        spec = training_job_spec_from_mapping(job.spec)
        if not spec.local_only or spec.allow_remote_code or spec.allow_network_during_training:
            raise ValueError("training_execution_offline_local_policy_required")

        base_model = self._resolved_input(payload.base_model_path, "base_model")
        train_dataset = self._resolved_input(payload.training_dataset_path, "training_dataset")
        eval_dataset = self._resolved_input(payload.eval_dataset_path, "eval_dataset")
        output = self._resolved_output(payload.output_path)

        base_sha = sha256_path(base_model)
        if base_sha != spec.base_model_sha256:
            raise ValueError("training_execution_base_model_hash_mismatch")
        train_sha = dataset_sha256_from_file(train_dataset)
        if train_sha != spec.dataset_sha256:
            raise ValueError("training_execution_training_dataset_hash_mismatch")
        eval_sha = dataset_sha256_from_file(eval_dataset)
        if eval_sha != spec.eval_dataset_sha256:
            raise ValueError("training_execution_eval_dataset_hash_mismatch")
        if train_sha == eval_sha:
            raise ValueError("training_execution_train_eval_collision")

        inputs = {base_model, train_dataset, eval_dataset}
        if output in inputs:
            raise ValueError("training_execution_output_overlaps_input")

        canonical = {
            "training_job_fingerprint": payload.training_job_fingerprint,
            "method": spec.method,
            "base_model_path": str(base_model),
            "base_model_sha256": base_sha,
            "training_dataset_path": str(train_dataset),
            "training_dataset_sha256": train_sha,
            "eval_dataset_path": str(eval_dataset),
            "eval_dataset_sha256": eval_sha,
            "output_path": str(output),
            "hyperparameters": self._hyperparameters(spec),
            "offline_environment": _OFFLINE_ENV,
            "local_only": spec.local_only,
            "allow_remote_code": spec.allow_remote_code,
            "allow_network_during_training": spec.allow_network_during_training,
            "requested_by": payload.requested_by.strip(),
            "execution_reference": payload.execution_reference.strip(),
        }
        fingerprint = _canonical_sha256(canonical)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        plan = TrainingExecutionPlan(
            id=record_id,
            fingerprint=fingerprint,
            created_at=created_at,
            **canonical,
        )
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO training_execution_plans(
                        id, fingerprint, training_job_fingerprint, plan_json,
                        requested_by, execution_reference, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        fingerprint,
                        payload.training_job_fingerprint,
                        json.dumps(
                            plan.model_dump(mode="json"),
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        ),
                        payload.requested_by.strip(),
                        payload.execution_reference.strip(),
                        created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("training_execution_plan_already_registered") from exc
        return plan

    def get_plan(self, fingerprint: str) -> TrainingExecutionPlan:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                "SELECT plan_json FROM training_execution_plans WHERE fingerprint=?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            raise KeyError("training_execution_plan_not_found")
        return TrainingExecutionPlan.model_validate_json(row[0])

    def register_receipt(
        self,
        payload: TrainingExecutionReceiptCreate,
    ) -> TrainingExecutionReceipt:
        plan = self.get_plan(payload.plan_fingerprint)
        artifact_path = Path(plan.output_path)
        if not artifact_path.exists():
            raise ValueError("training_execution_artifact_not_found")
        artifact_sha = sha256_path(artifact_path)
        canonical = {
            "plan_fingerprint": plan.fingerprint,
            "training_job_fingerprint": plan.training_job_fingerprint,
            "artifact_path": str(artifact_path.resolve(strict=True)),
            "artifact_sha256": artifact_sha,
            "executor": payload.executor.strip(),
            "execution_reference": payload.execution_reference.strip(),
        }
        fingerprint = _canonical_sha256(canonical)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        receipt = TrainingExecutionReceipt(
            id=record_id,
            fingerprint=fingerprint,
            created_at=created_at,
            **canonical,
        )
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT 1 FROM training_execution_receipts WHERE plan_fingerprint=?",
                    (plan.fingerprint,),
                ).fetchone()
                if existing is not None:
                    raise ValueError("training_execution_receipt_already_registered")
                conn.execute(
                    """
                    INSERT INTO training_execution_receipts(
                        id, fingerprint, plan_fingerprint, training_job_fingerprint,
                        artifact_path, artifact_sha256, executor,
                        execution_reference, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record_id,
                        fingerprint,
                        plan.fingerprint,
                        plan.training_job_fingerprint,
                        canonical["artifact_path"],
                        artifact_sha,
                        payload.executor.strip(),
                        payload.execution_reference.strip(),
                        created_at.isoformat(),
                    ),
                )
            except Exception:
                conn.rollback()
                raise
        return receipt

    def require_verified_artifact(
        self,
        *,
        training_job_fingerprint: str,
        artifact_sha256: str,
    ) -> TrainingExecutionReceipt:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT * FROM training_execution_receipts
                WHERE training_job_fingerprint=? AND artifact_sha256=?
                """,
                (training_job_fingerprint, artifact_sha256),
            ).fetchone()
        if row is None:
            raise KeyError("training_execution_verified_artifact_not_found")
        plan = self.get_plan(row["plan_fingerprint"])
        if plan.training_job_fingerprint != row["training_job_fingerprint"]:
            raise ValueError("training_execution_receipt_plan_job_drift")
        path = Path(row["artifact_path"])
        if not path.exists() or sha256_path(path) != row["artifact_sha256"]:
            raise ValueError("training_execution_artifact_drift")
        if Path(plan.output_path).resolve(strict=True) != path.resolve(strict=True):
            raise ValueError("training_execution_receipt_output_path_drift")
        canonical = {
            "plan_fingerprint": row["plan_fingerprint"],
            "training_job_fingerprint": row["training_job_fingerprint"],
            "artifact_path": str(path.resolve(strict=True)),
            "artifact_sha256": row["artifact_sha256"],
            "executor": row["executor"],
            "execution_reference": row["execution_reference"],
        }
        if _canonical_sha256(canonical) != row["fingerprint"]:
            raise ValueError("training_execution_receipt_fingerprint_drift")
        return TrainingExecutionReceipt(
            id=row["id"],
            fingerprint=row["fingerprint"],
            plan_fingerprint=row["plan_fingerprint"],
            training_job_fingerprint=row["training_job_fingerprint"],
            artifact_path=row["artifact_path"],
            artifact_sha256=row["artifact_sha256"],
            executor=row["executor"],
            execution_reference=row["execution_reference"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )


def apply_offline_training_environment() -> None:
    """Set the reviewed process-level offline flags before loading training libraries."""

    for key, value in _OFFLINE_ENV.items():
        os.environ[key] = value
