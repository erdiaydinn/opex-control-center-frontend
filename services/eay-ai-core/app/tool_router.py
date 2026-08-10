from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))

ToolName = Literal[
    "ops_kpi_query",
    "regulatory_impact_query",
    "catalog_query",
]


class ToolCallRequest(BaseModel):
    tool: ToolName
    sql: str = Field(min_length=6, max_length=20000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    requested_by: str | None = Field(default=None, max_length=180)
    reason: str = Field(min_length=3, max_length=1000)
    max_rows: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_sql_shape(self):
        validate_read_only_sql(self.sql)
        return self


class ToolCallAudit(BaseModel):
    id: str
    tool: ToolName
    sql_sha256: str
    status: Literal["validated", "rejected", "executed"]
    reason: str
    requested_by: str | None = None
    max_rows: int
    created_at: datetime


FORBIDDEN_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|CALL|EXECUTE|"
    r"GRANT|REVOKE|EXPORT|LOAD|BEGIN|COMMIT|ROLLBACK)\b",
    re.IGNORECASE,
)

ALLOWED_DATASET_PREFIXES = (
    "curated_data_shared.",
    "curated_data_shared_coredata_business.",
    "curated_data_shared_vendor.",
    "pandata_datamart.",
    "pandata_report.",
)

TABLE_REF = re.compile(r"`([^`]+)`")


def validate_read_only_sql(sql: str) -> None:
    normalized = re.sub(r"--.*?$|/\*.*?\*/", " ", sql, flags=re.MULTILINE | re.DOTALL).strip()
    if not normalized:
        raise ValueError("empty_sql")
    if ";" in normalized.rstrip(";"):
        raise ValueError("multiple_statements_not_allowed")
    if FORBIDDEN_SQL.search(normalized):
        raise ValueError("mutating_or_privileged_sql_not_allowed")
    if not re.match(r"^(?:WITH\b|SELECT\b)", normalized, flags=re.IGNORECASE):
        raise ValueError("only_select_or_with_queries_allowed")

    refs = TABLE_REF.findall(normalized)
    for ref in refs:
        pieces = ref.split(".")
        dataset_table = ".".join(pieces[-2:]) if len(pieces) >= 2 else ref
        if not any(dataset_table.startswith(prefix) for prefix in ALLOWED_DATASET_PREFIXES):
            raise ValueError(f"dataset_not_allowlisted:{dataset_table}")


def bounded_sql(sql: str, max_rows: int) -> str:
    normalized = sql.strip().rstrip(";")
    return f"SELECT * FROM ({normalized}) AS eay_safe_query LIMIT {int(max_rows)}"


class ToolAuditStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS tool_call_audit (
                    id TEXT PRIMARY KEY,
                    tool TEXT NOT NULL,
                    sql_text TEXT NOT NULL,
                    sql_sha256 TEXT NOT NULL,
                    parameters_json TEXT NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    requested_by TEXT,
                    max_rows INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_tool_audit_created
                ON tool_call_audit(created_at DESC);
                """
            )

    def save(self, payload: ToolCallRequest, status: str) -> ToolCallAudit:
        audit_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(payload.sql.encode("utf-8")).hexdigest()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO tool_call_audit(
                    id, tool, sql_text, sql_sha256, parameters_json,
                    status, reason, requested_by, max_rows, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    audit_id,
                    payload.tool,
                    payload.sql,
                    digest,
                    json.dumps(payload.parameters, ensure_ascii=False, sort_keys=True),
                    status,
                    payload.reason,
                    payload.requested_by,
                    payload.max_rows,
                    now.isoformat(),
                ),
            )
        return ToolCallAudit(
            id=audit_id,
            tool=payload.tool,
            sql_sha256=digest,
            status=status,
            reason=payload.reason,
            requested_by=payload.requested_by,
            max_rows=payload.max_rows,
            created_at=now,
        )


store = ToolAuditStore(DB_PATH)
router = APIRouter(prefix="/v1/tools", tags=["tools"])


@router.post("/validate")
def validate_tool_call(payload: ToolCallRequest):
    try:
        validate_read_only_sql(payload.sql)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audit = store.save(payload, "validated")
    return {
        "ok": True,
        "execution_enabled": False,
        "audit": audit.model_dump(mode="json"),
        "bounded_sql": bounded_sql(payload.sql, payload.max_rows),
        "parameters": payload.parameters,
        "safety": {
            "read_only": True,
            "single_statement": True,
            "dataset_allowlist": True,
            "hard_row_limit": payload.max_rows,
        },
    }
