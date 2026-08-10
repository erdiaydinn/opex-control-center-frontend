from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .tool_router import ToolCallRequest, bounded_sql, validate_read_only_sql

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
DEFAULT_MAX_BYTES = int(os.getenv("EAY_BQ_MAX_BYTES", str(250 * 1024 * 1024)))
DEFAULT_TIMEOUT_MS = int(os.getenv("EAY_BQ_TIMEOUT_MS", "20000"))
EXECUTION_ENABLED = os.getenv("EAY_BQ_EXECUTION_ENABLED", "false").lower() == "true"


class BigQueryAdapter(Protocol):
    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int: ...
    def execute(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int, maximum_bytes_billed: int) -> list[dict[str, Any]]: ...


class ExecuteRequest(ToolCallRequest):
    maximum_bytes_billed: int = Field(default=DEFAULT_MAX_BYTES, ge=1, le=10 * 1024 * 1024 * 1024)
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=1000, le=120000)


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
                    created_at TEXT NOT NULL
                )
                """
            )

    def save(self, *, payload: ExecuteRequest, dry_run_bytes: int | None, status: str) -> str:
        execution_id = str(uuid.uuid4())
        digest = hashlib.sha256(payload.sql.encode("utf-8")).hexdigest()
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO bigquery_execution_audit(
                    id, tool, sql_sha256, dry_run_bytes, maximum_bytes_billed,
                    timeout_ms, max_rows, status, requested_by, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    execution_id, payload.tool, digest, dry_run_bytes,
                    payload.maximum_bytes_billed, payload.timeout_ms, payload.max_rows,
                    status, payload.requested_by, payload.reason,
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


class DisabledAdapter:
    def dry_run(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int) -> int:
        raise RuntimeError("BigQuery adapter is not configured")

    def execute(self, sql: str, parameters: dict[str, Any], *, timeout_ms: int, maximum_bytes_billed: int) -> list[dict[str, Any]]:
        raise RuntimeError("BigQuery adapter is not configured")


audit_store = ExecutionAuditStore(DB_PATH)
router = APIRouter(prefix="/v1/bigquery", tags=["bigquery-safe-executor"])


@router.post("/dry-run", response_model=ExecutionResult)
def dry_run(payload: ExecuteRequest):
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=409, detail="BigQuery execution adapter is disabled; use dependency-injected executor in trusted runtime")
    raise HTTPException(status_code=501, detail="Runtime adapter must be provided by deployment integration")
