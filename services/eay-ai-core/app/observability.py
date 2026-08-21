from __future__ import annotations

import os
import sqlite3
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter
from pydantic import BaseModel, Field

DB_PATH = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))


class MetricsSnapshot(BaseModel):
    interactions: int = 0
    feedback: int = 0
    learning_candidates_pending: int = 0
    legal_verified: int = 0
    regulatory_changes_pending: int = 0
    company_approved: int = 0
    tool_calls: int = 0
    bigquery_executions: int = 0
    bigquery_cost_rejections: int = 0
    vision_audits_pending: int = 0
    model_candidates: int = 0
    model_canaries: int = 0
    knowledge_by_layer: dict[str, int] = Field(default_factory=dict)
    latest_interaction_at: datetime | None = None
    latest_tool_call_at: datetime | None = None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return row is not None


def _count(conn: sqlite3.Connection, table: str, where: str = "", params: tuple = ()) -> int:
    if not _table_exists(conn, table):
        return 0
    suffix = f" WHERE {where}" if where else ""
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}{suffix}", params).fetchone()[0])


def metrics_snapshot(db_path: Path = DB_PATH) -> MetricsSnapshot:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        by_layer: dict[str, int] = {}
        if _table_exists(conn, "knowledge_documents"):
            rows = conn.execute(
                "SELECT layer, COUNT(*) AS n FROM knowledge_documents GROUP BY layer"
            ).fetchall()
            by_layer = {str(row["layer"]): int(row["n"]) for row in rows}

        latest_interaction = None
        if _table_exists(conn, "interactions"):
            row = conn.execute("SELECT MAX(created_at) FROM interactions").fetchone()
            latest_interaction = datetime.fromisoformat(row[0]) if row and row[0] else None

        latest_tool = None
        if _table_exists(conn, "tool_call_audit"):
            row = conn.execute("SELECT MAX(created_at) FROM tool_call_audit").fetchone()
            latest_tool = datetime.fromisoformat(row[0]) if row and row[0] else None

        return MetricsSnapshot(
            interactions=_count(conn, "interactions"),
            feedback=_count(conn, "feedback"),
            learning_candidates_pending=_count(conn, "learning_candidates", "status='pending'"),
            legal_verified=_count(conn, "legal_instruments", "verification_status='verified'"),
            regulatory_changes_pending=_count(conn, "regulatory_changes", "status='pending'"),
            company_approved=_count(conn, "company_policy_versions", "status='approved'"),
            tool_calls=_count(conn, "tool_call_audit"),
            bigquery_executions=_count(conn, "bigquery_execution_audit", "status='executed'"),
            bigquery_cost_rejections=_count(conn, "bigquery_execution_audit", "status='rejected_cost'"),
            vision_audits_pending=_count(conn, "vision_audits", "decision='pending'"),
            model_candidates=_count(conn, "model_registry", "status='candidate'"),
            model_canaries=_count(conn, "model_registry", "status='canary'"),
            knowledge_by_layer=by_layer,
            latest_interaction_at=latest_interaction,
            latest_tool_call_at=latest_tool,
        )


router = APIRouter(prefix="/v1/metrics", tags=["observability"])


@router.get("/snapshot", response_model=MetricsSnapshot)
def snapshot():
    # Intentionally exposes counts/timestamps only: no prompts, SQL, user IDs or document text.
    return metrics_snapshot()
