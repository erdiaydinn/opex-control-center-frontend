from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .canary_evals import CanaryMetrics, evaluate_canary


class CanaryResultRegistration(BaseModel):
    model_record_id: str = Field(min_length=1, max_length=180)
    artifact_provenance_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    current_percent: int = Field(ge=1, le=25)
    metrics: CanaryMetrics
    evaluated_by: str = Field(min_length=2, max_length=180)
    evidence_reference: str = Field(min_length=2, max_length=500)


class CanaryResultRecord(BaseModel):
    id: str
    model_record_id: str
    artifact_provenance_fingerprint: str
    current_percent: int
    metrics: CanaryMetrics
    passed: bool
    violations: tuple[str, ...]
    recommended_percent: int
    evaluated_by: str
    evidence_reference: str
    result_fingerprint: str
    created_at: datetime


def canary_result_fingerprint(payload: CanaryResultRegistration) -> str:
    metrics = payload.metrics
    canonical = json.dumps(
        {
            "model_record_id": payload.model_record_id,
            "artifact_provenance_fingerprint": payload.artifact_provenance_fingerprint,
            "current_percent": payload.current_percent,
            "metrics": {
                "sample_size": metrics.sample_size,
                "error_rate": metrics.error_rate,
                "grounded_answer_rate": metrics.grounded_answer_rate,
                "citation_validity_rate": metrics.citation_validity_rate,
                "unsafe_action_rate": metrics.unsafe_action_rate,
                "kvkk_leak_rate": metrics.kvkk_leak_rate,
                "p95_latency_ms": metrics.p95_latency_ms,
            },
            "evaluated_by": payload.evaluated_by.strip(),
            "evidence_reference": payload.evidence_reference.strip(),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class CanaryResultRegistry:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS canary_result_registry (
                id TEXT PRIMARY KEY,
                model_record_id TEXT NOT NULL,
                artifact_provenance_fingerprint TEXT NOT NULL,
                current_percent INTEGER NOT NULL,
                metrics_json TEXT NOT NULL,
                passed INTEGER NOT NULL,
                violations_json TEXT NOT NULL,
                recommended_percent INTEGER NOT NULL,
                evaluated_by TEXT NOT NULL,
                evidence_reference TEXT NOT NULL,
                result_fingerprint TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL)"""
            )

    def _verify_model_binding(self, payload: CanaryResultRegistration) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, artifact_provenance_fingerprint, canary_percent FROM model_registry WHERE id=?",
                (payload.model_record_id,),
            ).fetchone()
        if row is None:
            raise KeyError("canary_model_not_found")
        if row["status"] != "canary":
            raise ValueError("canary_result_requires_canary_model")
        if row["artifact_provenance_fingerprint"] != payload.artifact_provenance_fingerprint:
            raise ValueError("canary_result_artifact_provenance_mismatch")
        if int(row["canary_percent"]) != payload.current_percent:
            raise ValueError("canary_result_percent_mismatch")

    def register(self, payload: CanaryResultRegistration) -> CanaryResultRecord:
        self._verify_model_binding(payload)
        decision = evaluate_canary(payload.metrics, payload.current_percent)
        fingerprint = canary_result_fingerprint(payload)
        record_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc)
        with sqlite3.connect(self.db_path) as conn:
            try:
                conn.execute(
                    """INSERT INTO canary_result_registry(
                    id,model_record_id,artifact_provenance_fingerprint,current_percent,
                    metrics_json,passed,violations_json,recommended_percent,evaluated_by,
                    evidence_reference,result_fingerprint,created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (
                        record_id,
                        payload.model_record_id,
                        payload.artifact_provenance_fingerprint,
                        payload.current_percent,
                        json.dumps(payload.metrics.__dict__, sort_keys=True, separators=(",", ":")),
                        1 if decision.promote else 0,
                        json.dumps(list(decision.violations), separators=(",", ":")),
                        decision.recommended_percent,
                        payload.evaluated_by,
                        payload.evidence_reference,
                        fingerprint,
                        created_at.isoformat(),
                    ),
                )
            except sqlite3.IntegrityError as exc:
                raise ValueError("canary_result_already_registered") from exc
        return CanaryResultRecord(
            id=record_id,
            model_record_id=payload.model_record_id,
            artifact_provenance_fingerprint=payload.artifact_provenance_fingerprint,
            current_percent=payload.current_percent,
            metrics=payload.metrics,
            passed=decision.promote,
            violations=decision.violations,
            recommended_percent=decision.recommended_percent,
            evaluated_by=payload.evaluated_by,
            evidence_reference=payload.evidence_reference,
            result_fingerprint=fingerprint,
            created_at=created_at,
        )

    def get_by_fingerprint(self, fingerprint: str) -> CanaryResultRecord:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM canary_result_registry WHERE result_fingerprint=?",
                (fingerprint,),
            ).fetchone()
        if row is None:
            raise KeyError("canary_result_not_found")
        metrics = CanaryMetrics(**json.loads(row["metrics_json"]))
        return CanaryResultRecord(
            id=row["id"],
            model_record_id=row["model_record_id"],
            artifact_provenance_fingerprint=row["artifact_provenance_fingerprint"],
            current_percent=row["current_percent"],
            metrics=metrics,
            passed=bool(row["passed"]),
            violations=tuple(json.loads(row["violations_json"])),
            recommended_percent=row["recommended_percent"],
            evaluated_by=row["evaluated_by"],
            evidence_reference=row["evidence_reference"],
            result_fingerprint=row["result_fingerprint"],
            created_at=datetime.fromisoformat(row["created_at"]),
        )
