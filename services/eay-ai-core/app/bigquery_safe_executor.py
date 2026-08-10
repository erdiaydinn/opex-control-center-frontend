from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .tool_router import ToolCallRequest, bounded_sql, validate_read_only_sql

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
DEFAULT_MAX_BYTES = int(os.getenv("EAY_BQ_MAX_BYTES", str(250 * 1024 * 1024)))
DEFAULT_TIMEOUT_MS = int(os.getenv("EAY_BQ_TIMEOUT_MS", "20000"))
EXECUTION_ENABLED = os.getenv("EAY_BQ_EXECUTION_ENABLED", "false").lower() == "true"
BQ_PROJECT = os.getenv("EAY_BQ_PROJECT", "").strip() or None
BQ_LOCATION = os.getenv("EAY_BQ_LOCATION", "").strip() or None


class BigQueryAdapter(Protocol):
    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int: ...
    def execute(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int, maximum_bytes_billed: int) -> list[dict[str, Any]]: ...


class ExecuteRequest(ToolCallRequest):
    maximum_bytes_billed: int = Field(default=DEFAULT_MAX_BYTES, ge=1, le=10 * 1024 * 1024 * 1024)
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=1000, le=120000)
    semantic_contract_id: str | None = Field(default=None, max_length=180)
    semantic_fingerprint: str | None = Field(default=None, max_length=64)
    schema_contract_id: str | None = Field(default=None, max_length=180)
    schema_fingerprint: str | None = Field(default=None, max_length=64)
    schema_evidence_fingerprint: str | None = Field(default=None, max_length=64)
    unit_contract_fingerprint: str | None = Field(default=None, max_length=64)
    aggregation_contract_fingerprint: str | None = Field(default=None, max_length=64)
    policy_contract_fingerprint: str | None = Field(default=None, max_length=64)
    formula_contract_fingerprint: str | None = Field(default=None, max_length=64)
    result_contract_fingerprint: str | None = Field(default=None, max_length=64)
    activation_provenance_fingerprint: str | None = Field(default=None, max_length=64)


class ExecutionResult(BaseModel):
    execution_id: str
    status: str
    dry_run_bytes: int
    maximum_bytes_billed: int
    row_count: int = 0
    rows: list[dict[str, Any]] = Field(default_factory=list)
    sql_sha256: str


SENSITIVE_KEYS = {
    "tc", "tc_kimlik", "tckn", "national_id", "identity_number",
    "phone", "telefon", "email", "mail", "address", "adres",
}


def _mask_scalar(value: Any) -> Any:
    if value is None:
        return None
    text = str(value)
    if len(text) <= 4:
        return "***"
    return text[:2] + "***" + text[-2:]


def mask_sensitive_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        clean: dict[str, Any] = {}
        for key, value in row.items():
            normalized = key.lower().replace(" ", "_")
            clean[key] = _mask_scalar(value) if normalized in SENSITIVE_KEYS else value
        output.append(clean)
    return output


@dataclass(frozen=True)
class ExecutionPolicy:
    maximum_bytes_billed: int
    timeout_ms: int
    max_rows: int


class ExecutionAuditStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bigquery_execution_audit (
                    id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    sql_sha256 TEXT NOT NULL,
                    dry_run_bytes INTEGER,
                    maximum_bytes_billed INTEGER NOT NULL,
                    timeout_ms INTEGER NOT NULL,
                    max_rows INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    requested_by TEXT,
                    reason TEXT NOT NULL,
                    semantic_contract_id TEXT,
                    semantic_fingerprint TEXT,
                    schema_contract_id TEXT,
                    schema_fingerprint TEXT,
                    schema_evidence_fingerprint TEXT,
                    unit_contract_fingerprint TEXT,
                    aggregation_contract_fingerprint TEXT,
                    policy_contract_fingerprint TEXT,
                    formula_contract_fingerprint TEXT,
                    result_contract_fingerprint TEXT,
                    activation_provenance_fingerprint TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            existing = {row[1] for row in conn.execute("PRAGMA table_info(bigquery_execution_audit)")}
            for name in (
                "semantic_contract_id",
                "semantic_fingerprint",
                "schema_contract_id",
                "schema_fingerprint",
                "schema_evidence_fingerprint",
                "unit_contract_fingerprint",
                "aggregation_contract_fingerprint",
                "policy_contract_fingerprint",
                "formula_contract_fingerprint",
                "result_contract_fingerprint",
                "activation_provenance_fingerprint",
            ):
                if name not in existing:
                    conn.execute(f"ALTER TABLE bigquery_execution_audit ADD COLUMN {name} TEXT")

    def save(self, *, payload: ExecuteRequest, dry_run_bytes: int | None, status: str) -> str:
        execution_id = str(uuid.uuid4())
        digest = hashlib.sha256(payload.sql.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO bigquery_execution_audit(
                    id, tool, sql_sha256, dry_run_bytes, maximum_bytes_billed,
                    timeout_ms, max_rows, status, requested_by, reason,
                    semantic_contract_id, semantic_fingerprint,
                    schema_contract_id, schema_fingerprint, schema_evidence_fingerprint,
                    unit_contract_fingerprint, aggregation_contract_fingerprint,
                    policy_contract_fingerprint, formula_contract_fingerprint,
                    result_contract_fingerprint, activation_provenance_fingerprint, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id, payload.tool, digest, dry_run_bytes,
                    payload.maximum_bytes_billed, payload.timeout_ms, payload.max_rows,
                    status, payload.requested_by, payload.reason,
                    payload.semantic_contract_id, payload.semantic_fingerprint,
                    payload.schema_contract_id, payload.schema_fingerprint,
                    payload.schema_evidence_fingerprint,
                    payload.unit_contract_fingerprint,
                    payload.aggregation_contract_fingerprint,
                    payload.policy_contract_fingerprint,
                    payload.formula_contract_fingerprint,
                    payload.result_contract_fingerprint,
                    payload.activation_provenance_fingerprint,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )
        return execution_id


class SafeBigQueryExecutor:
    def __init__(self, adapter: BigQueryAdapter, audit_store: ExecutionAuditStore):
        self.adapter = adapter
        self.audit_store = audit_store

    def run(self, payload: ExecuteRequest, *, execute: bool) -> ExecutionResult:
        validate_read_only_sql(payload.sql)
        sql = bounded_sql(payload.sql, payload.max_rows)
        dry_run_bytes = self.adapter.dry_run(sql, payload.parameters, timeout_ms=payload.timeout_ms)
        digest = hashlib.sha256(payload.sql.encode("utf-8")).hexdigest()
        if dry_run_bytes > payload.maximum_bytes_billed:
            execution_id = self.audit_store.save(payload=payload, dry_run_bytes=dry_run_bytes, status="rejected_cost")
            return ExecutionResult(
                execution_id=execution_id,
                status="rejected_cost",
                dry_run_bytes=dry_run_bytes,
                maximum_bytes_billed=payload.maximum_bytes_billed,
                sql_sha256=digest,
            )
        if not execute:
            execution_id = self.audit_store.save(payload=payload, dry_run_bytes=dry_run_bytes, status="dry_run_ok")
            return ExecutionResult(
                execution_id=execution_id,
                status="dry_run_ok",
                dry_run_bytes=dry_run_bytes,
                maximum_bytes_billed=payload.maximum_bytes_billed,
                sql_sha256=digest,
            )
        rows = self.adapter.execute(
            sql,
            payload.parameters,
            timeout_ms=payload.timeout_ms,
            maximum_bytes_billed=payload.maximum_bytes_billed,
        )[: payload.max_rows]
        masked = mask_sensitive_rows(rows)
        execution_id = self.audit_store.save(payload=payload, dry_run_bytes=dry_run_bytes, status="executed")
        return ExecutionResult(
            execution_id=execution_id,
            status="executed",
            dry_run_bytes=dry_run_bytes,
            maximum_bytes_billed=payload.maximum_bytes_billed,
            row_count=len(masked),
            rows=masked,
            sql_sha256=digest,
        )


class GoogleBigQueryAdapter:
    """Optional adapter; import google-cloud-bigquery only in deployments that enable it."""

    def __init__(self, *, project: str | None = BQ_PROJECT, location: str | None = BQ_LOCATION):
        try:
            from google.cloud import bigquery  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "google-cloud-bigquery is required only when EAY_BQ_EXECUTION_ENABLED=true"
            ) from exc
        self.bigquery = bigquery
        self.client = bigquery.Client(project=project, location=location)

    def _parameters(self, values: dict[str, Any]):
        params = []
        for name, value in values.items():
            if isinstance(value, bool):
                type_name = "BOOL"
            elif isinstance(value, int):
                type_name = "INT64"
            elif isinstance(value, float):
                type_name = "FLOAT64"
            elif isinstance(value, datetime):
                type_name = "TIMESTAMP"
            elif isinstance(value, date):
                type_name = "DATE"
            elif isinstance(value, str) or value is None:
                type_name = "STRING"
            else:
                raise ValueError(f"unsupported_query_parameter_type:{name}")
            params.append(self.bigquery.ScalarQueryParameter(name, type_name, value))
        return params

    def _job_config(self, parameters: dict[str, Any], *, dry_run: bool, timeout_ms: int, maximum_bytes_billed: int | None = None):
        config = self.bigquery.QueryJobConfig(
            dry_run=dry_run,
            use_query_cache=False if dry_run else True,
            query_parameters=self._parameters(parameters),
            job_timeout_ms=timeout_ms,
        )
        if maximum_bytes_billed is not None:
            config.maximum_bytes_billed = maximum_bytes_billed
        return config

    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int:
        job = self.client.query(
            sql,
            job_config=self._job_config(parameters, dry_run=True, timeout_ms=timeout_ms),
        )
        return int(job.total_bytes_processed or 0)

    def execute(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int, maximum_bytes_billed: int) -> list[dict[str, Any]]:
        job = self.client.query(
            sql,
            job_config=self._job_config(
                parameters,
                dry_run=False,
                timeout_ms=timeout_ms,
                maximum_bytes_billed=maximum_bytes_billed,
            ),
        )
        rows = job.result(timeout=max(1, timeout_ms / 1000))
        return [dict(row.items()) for row in rows]


class DisabledAdapter:
    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int:
        raise RuntimeError("BigQuery adapter is not configured")

    def execute(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int, maximum_bytes_billed: int) -> list[dict[str, Any]]:
        raise RuntimeError("BigQuery adapter is not configured")


audit_store = ExecutionAuditStore(DB_PATH)
router = APIRouter(prefix="/v1/bigquery", tags=["bigquery-safe-executor"])


def _runtime_executor() -> SafeBigQueryExecutor:
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=409, detail="BigQuery execution is disabled by default")
    try:
        adapter = GoogleBigQueryAdapter()
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return SafeBigQueryExecutor(adapter, audit_store)


@router.post("/dry-run", response_model=ExecutionResult)
def dry_run(payload: ExecuteRequest):
    try:
        return _runtime_executor().run(payload, execute=False)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BigQuery dry-run failed: {exc}") from exc


@router.post("/execute", response_model=ExecutionResult)
def execute(payload: ExecuteRequest):
    try:
        return _runtime_executor().run(payload, execute=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"BigQuery execution failed: {exc}") from exc
