from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .bigquery_safe_executor import (
    DEFAULT_MAX_BYTES,
    DEFAULT_TIMEOUT_MS,
    EXECUTION_ENABLED,
    ExecuteRequest,
    ExecutionAuditStore,
    ExecutionResult,
    GoogleBigQueryAdapter,
    SafeBigQueryExecutor,
)
from .query_templates import compile_tool_plan
from .tool_contracts import ToolName, build_tool_plan


class TemplateToolExecutionRequest(BaseModel):
    tool: ToolName
    arguments: dict[str, Any]
    granted_scopes: list[str] = Field(default_factory=list, max_length=32)
    requested_by: str | None = Field(default=None, max_length=180)
    reason: str = Field(min_length=3, max_length=1000)
    execute: bool = False
    maximum_bytes_billed: int = Field(default=DEFAULT_MAX_BYTES, ge=1, le=10 * 1024 * 1024 * 1024)
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=1000, le=120000)
    max_rows: int = Field(default=500, ge=1, le=5000)


class TemplateToolExecutionResult(BaseModel):
    tool: ToolName
    query_id: str
    required_scope: list[str]
    execution: ExecutionResult
    model_authored_sql_allowed: bool = False


def prepare_execution(payload: TemplateToolExecutionRequest) -> tuple[ExecuteRequest, str, list[str]]:
    plan = build_tool_plan(payload.tool, payload.arguments)
    missing = sorted(set(plan.required_scope) - set(payload.granted_scopes))
    if missing:
        raise PermissionError(f"missing_required_scope:{','.join(missing)}")
    sql, parameters = compile_tool_plan(plan)
    request = ExecuteRequest(
        tool=plan.tool,
        sql=sql,
        parameters=parameters,
        requested_by=payload.requested_by,
        reason=payload.reason,
        max_rows=payload.max_rows,
        maximum_bytes_billed=payload.maximum_bytes_billed,
        timeout_ms=payload.timeout_ms,
    )
    return request, plan.query_id, plan.required_scope


def execute_with_adapter(
    payload: TemplateToolExecutionRequest,
    *,
    adapter,
    audit_store: ExecutionAuditStore,
) -> TemplateToolExecutionResult:
    request, query_id, required_scope = prepare_execution(payload)
    executor = SafeBigQueryExecutor(adapter, audit_store)
    execution = executor.run(request, execute=payload.execute)
    return TemplateToolExecutionResult(
        tool=payload.tool,
        query_id=query_id,
        required_scope=required_scope,
        execution=execution,
        model_authored_sql_allowed=False,
    )


router = APIRouter(prefix="/v1/tool-execution", tags=["tool-execution"])


@router.post("", response_model=TemplateToolExecutionResult)
def execute_template_tool(payload: TemplateToolExecutionRequest):
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=409, detail="BigQuery execution is disabled by default")
    try:
        request, query_id, required_scope = prepare_execution(payload)
        adapter = GoogleBigQueryAdapter()
        audit_store = ExecutionAuditStore(
            __import__("pathlib").Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
        )
        execution = SafeBigQueryExecutor(adapter, audit_store).run(request, execute=payload.execute)
        return TemplateToolExecutionResult(
            tool=payload.tool,
            query_id=query_id,
            required_scope=required_scope,
            execution=execution,
            model_authored_sql_allowed=False,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
