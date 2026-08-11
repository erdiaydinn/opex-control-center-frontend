from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .training_job_spec import TrainingJobSpec, training_job_spec_from_mapping


class TrainingJobRegistration(BaseModel):
    spec: dict
    approved_by: str = Field(min_length=2, max_length=180)
    approval_reference: str = Field(min_length=2, max_length=300)


class TrainingJobRecord(BaseModel):
    id: str
    fingerprint: str
    manifest_id: str
    spec: dict
    approved_by: str
    approval_reference: str
    created_at: datetime


class TrainingJobRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS training_job_registry (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                manifest_id TEXT NOT NULL, spec_json TEXT NOT NULL,
                approved_by TEXT NOT NULL, approval_reference TEXT NOT NULL,
                created_at TEXT NOT NULL)"""
            )

    def _resolve_manifest(self, spec: TrainingJobSpec) -> sqlite3.Row:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM training_dataset_manifests WHERE chain_sha256=?",
                (spec.training_manifest_chain_sha256,),
            ).fetchall()
        if len(rows) != 1:
            raise ValueError("training_job_manifest_not_uniquely_registered")
        manifest = rows[0]
        if manifest["dataset_sha256"] != spec.dataset_sha256:
            raise ValueError("training_job_dataset_manifest_mismatch")
        if manifest["eval_dataset_sha256"] != spec.eval_dataset_sha256:
            raise ValueError("training_job_eval_dataset_manifest_mismatch")
        if not manifest["dataset_integrity_sha256"] or not manifest["quality_lineage_sha256"]:
            raise ValueError("training_job_manifest_quality_lineage_required")
        return manifest

    def register(self, payload: TrainingJobRegistration) -> TrainingJobRecord:
        spec = training_job_spec_from_mapping(payload.spec)
        manifest = self._resolve_manifest(spec)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        canonical = json.dumps(payload.spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO training_job_registry VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (record_id, spec.fingerprint, manifest["id"], canonical,
                     payload.approved_by, payload.approval_reference, created_at.isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("training_job_already_registered") from exc
        return TrainingJobRecord(id=record_id, fingerprint=spec.fingerprint,
            manifest_id=manifest["id"], spec=json.loads(canonical), approved_by=payload.approved_by,
            approval_reference=payload.approval_reference, created_at=created_at)

    def get_by_fingerprint(self, fingerprint: str) -> TrainingJobRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM training_job_registry WHERE fingerprint=?", (fingerprint,)).fetchone()
        if row is None:
            raise KeyError("training_job_not_found")
        return TrainingJobRecord(id=row["id"], fingerprint=row["fingerprint"],
            manifest_id=row["manifest_id"], spec=json.loads(row["spec_json"]),
            approved_by=row["approved_by"], approval_reference=row["approval_reference"],
            created_at=datetime.fromisoformat(row["created_at"]))

    def verify_model_lineage(self, *, fingerprint: str, base_model: str, license_id: str,
        training_dataset_sha256: str, training_manifest_chain_sha256: str,
        eval_dataset_sha256: str) -> TrainingJobRecord:
        record = self.get_by_fingerprint(fingerprint)
        spec = training_job_spec_from_mapping(record.spec)
        expected = (spec.base_model, spec.base_model_license_id, spec.dataset_sha256,
            spec.training_manifest_chain_sha256, spec.eval_dataset_sha256)
        actual = (base_model, license_id, training_dataset_sha256,
            training_manifest_chain_sha256, eval_dataset_sha256)
        labels = ("base_model", "license", "dataset", "manifest_chain", "eval_dataset")
        for label, left, right in zip(labels, expected, actual):
            if left != right:
                raise ValueError(f"model_training_job_lineage_mismatch:{label}")
        self._resolve_manifest(spec)
        return record
