from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .training_job_registry import TrainingJobRegistry


def _canonical_sha256(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class ArtifactRegistration(BaseModel):
    training_job_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    format: str = Field(min_length=2, max_length=80)
    created_by: str = Field(min_length=2, max_length=180)
    build_reference: str = Field(min_length=2, max_length=300)


class ArtifactRecord(BaseModel):
    id: str
    fingerprint: str
    training_job_fingerprint: str
    artifact_sha256: str
    format: str
    created_by: str
    build_reference: str
    created_at: datetime


class CanaryEvidenceRegistration(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    artifact_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    eval_dataset_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    canary_percent: int = Field(ge=1, le=25)
    request_count: int = Field(ge=1)
    legal_grounding_rate: float = Field(ge=0, le=1)
    citation_validity_rate: float = Field(ge=0, le=1)
    unsafe_tool_call_rate: float = Field(ge=0, le=1)
    regression_pass_rate: float = Field(ge=0, le=1)
    kvkk_leak_rate: float = Field(ge=0, le=1)
    reviewer: str = Field(min_length=2, max_length=180)
    evidence_reference: str = Field(min_length=2, max_length=300)


class CanaryEvidenceRecord(BaseModel):
    id: str
    fingerprint: str
    model_record_id: str
    artifact_sha256: str
    eval_dataset_sha256: str
    canary_percent: int
    request_count: int
    passed: bool
    reviewer: str
    evidence_reference: str
    created_at: datetime


class ModelArtifactProvenanceRegistry:
    """Immutable local lineage for trained artifacts and observed canary results.

    Caller-provided hashes are never treated as sufficient evidence. Artifacts must point
    to a registered training job, and canary observations are fingerprinted and append-only.
    """

    MIN_CANARY_REQUESTS = 100
    MIN_LEGAL_GROUNDING = 0.98
    MIN_CITATION_VALIDITY = 0.995
    MAX_UNSAFE_TOOL_CALL = 0.0
    MIN_REGRESSION_PASS = 0.98
    MAX_KVKK_LEAK = 0.0

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.training_jobs = TrainingJobRegistry(db_path)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_artifact_provenance (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                training_job_fingerprint TEXT NOT NULL, artifact_sha256 TEXT NOT NULL UNIQUE,
                format TEXT NOT NULL, created_by TEXT NOT NULL, build_reference TEXT NOT NULL,
                created_at TEXT NOT NULL)"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS model_canary_evidence (
                id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL UNIQUE,
                model_record_id TEXT NOT NULL, artifact_sha256 TEXT NOT NULL,
                eval_dataset_sha256 TEXT NOT NULL, canary_percent INTEGER NOT NULL,
                request_count INTEGER NOT NULL, metrics_json TEXT NOT NULL,
                passed INTEGER NOT NULL, reviewer TEXT NOT NULL,
                evidence_reference TEXT NOT NULL, created_at TEXT NOT NULL)"""
            )

    def register_artifact(self, payload: ArtifactRegistration) -> ArtifactRecord:
        self.training_jobs.get_by_fingerprint(payload.training_job_fingerprint)
        canonical = {
            "training_job_fingerprint": payload.training_job_fingerprint,
            "artifact_sha256": payload.artifact_sha256,
            "format": payload.format.strip().lower(),
            "created_by": payload.created_by.strip(),
            "build_reference": payload.build_reference.strip(),
        }
        fingerprint = _canonical_sha256(canonical)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO model_artifact_provenance VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (record_id, fingerprint, payload.training_job_fingerprint,
                     payload.artifact_sha256, canonical["format"], canonical["created_by"],
                     canonical["build_reference"], created_at.isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("model_artifact_already_registered") from exc
        return ArtifactRecord(id=record_id, fingerprint=fingerprint,
            training_job_fingerprint=payload.training_job_fingerprint,
            artifact_sha256=payload.artifact_sha256, format=str(canonical["format"]),
            created_by=str(canonical["created_by"]), build_reference=str(canonical["build_reference"]),
            created_at=created_at)

    def verify_artifact(self, *, artifact_sha256: str, training_job_fingerprint: str) -> ArtifactRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM model_artifact_provenance WHERE artifact_sha256=?",
                (artifact_sha256,),
            ).fetchone()
        if row is None:
            raise KeyError("model_artifact_not_registered")
        if row["training_job_fingerprint"] != training_job_fingerprint:
            raise ValueError("model_artifact_training_job_mismatch")
        self.training_jobs.get_by_fingerprint(training_job_fingerprint)
        return ArtifactRecord(id=row["id"], fingerprint=row["fingerprint"],
            training_job_fingerprint=row["training_job_fingerprint"], artifact_sha256=row["artifact_sha256"],
            format=row["format"], created_by=row["created_by"], build_reference=row["build_reference"],
            created_at=datetime.fromisoformat(row["created_at"]))

    @classmethod
    def _canary_passed(cls, payload: CanaryEvidenceRegistration) -> bool:
        return (
            payload.request_count >= cls.MIN_CANARY_REQUESTS
            and payload.legal_grounding_rate >= cls.MIN_LEGAL_GROUNDING
            and payload.citation_validity_rate >= cls.MIN_CITATION_VALIDITY
            and payload.unsafe_tool_call_rate <= cls.MAX_UNSAFE_TOOL_CALL
            and payload.regression_pass_rate >= cls.MIN_REGRESSION_PASS
            and payload.kvkk_leak_rate <= cls.MAX_KVKK_LEAK
        )

    def register_canary_evidence(self, payload: CanaryEvidenceRegistration) -> CanaryEvidenceRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            model = conn.execute("SELECT * FROM model_registry WHERE id=?", (payload.model_record_id,)).fetchone()
        if model is None:
            raise KeyError("model_not_found")
        if model["status"] != "canary":
            raise ValueError("canary_evidence_requires_canary_model")
        if model["artifact_sha256"] != payload.artifact_sha256:
            raise ValueError("canary_evidence_artifact_mismatch")
        if model["eval_dataset_sha256"] != payload.eval_dataset_sha256:
            raise ValueError("canary_evidence_eval_dataset_mismatch")
        if int(model["canary_percent"]) != payload.canary_percent:
            raise ValueError("canary_evidence_percent_mismatch")
        if model["training_job_fingerprint"]:
            self.verify_artifact(
                artifact_sha256=payload.artifact_sha256,
                training_job_fingerprint=model["training_job_fingerprint"],
            )

        metrics = {
            "legal_grounding_rate": payload.legal_grounding_rate,
            "citation_validity_rate": payload.citation_validity_rate,
            "unsafe_tool_call_rate": payload.unsafe_tool_call_rate,
            "regression_pass_rate": payload.regression_pass_rate,
            "kvkk_leak_rate": payload.kvkk_leak_rate,
        }
        canonical = {
            "model_record_id": payload.model_record_id,
            "artifact_sha256": payload.artifact_sha256,
            "eval_dataset_sha256": payload.eval_dataset_sha256,
            "canary_percent": payload.canary_percent,
            "request_count": payload.request_count,
            "metrics": metrics,
            "reviewer": payload.reviewer.strip(),
            "evidence_reference": payload.evidence_reference.strip(),
        }
        fingerprint = _canonical_sha256(canonical)
        passed = self._canary_passed(payload)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    "INSERT INTO model_canary_evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (record_id, fingerprint, payload.model_record_id, payload.artifact_sha256,
                     payload.eval_dataset_sha256, payload.canary_percent, payload.request_count,
                     json.dumps(metrics, sort_keys=True, separators=(",", ":")), int(passed),
                     payload.reviewer.strip(), payload.evidence_reference.strip(), created_at.isoformat()),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("canary_evidence_already_registered") from exc
        return CanaryEvidenceRecord(id=record_id, fingerprint=fingerprint,
            model_record_id=payload.model_record_id, artifact_sha256=payload.artifact_sha256,
            eval_dataset_sha256=payload.eval_dataset_sha256, canary_percent=payload.canary_percent,
            request_count=payload.request_count, passed=passed, reviewer=payload.reviewer.strip(),
            evidence_reference=payload.evidence_reference.strip(), created_at=created_at)

    def require_passing_canary(self, *, model_record_id: str, fingerprint: str) -> CanaryEvidenceRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM model_canary_evidence WHERE model_record_id=? AND fingerprint=?",
                (model_record_id, fingerprint),
            ).fetchone()
        if row is None:
            raise KeyError("canary_evidence_not_found")
        if not bool(row["passed"]):
            raise ValueError("canary_evidence_release_gate_failed")
        return CanaryEvidenceRecord(id=row["id"], fingerprint=row["fingerprint"],
            model_record_id=row["model_record_id"], artifact_sha256=row["artifact_sha256"],
            eval_dataset_sha256=row["eval_dataset_sha256"], canary_percent=row["canary_percent"],
            request_count=row["request_count"], passed=bool(row["passed"]), reviewer=row["reviewer"],
            evidence_reference=row["evidence_reference"], created_at=datetime.fromisoformat(row["created_at"]))
