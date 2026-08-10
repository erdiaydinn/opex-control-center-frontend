from __future__ import annotations

import os
from datetime import date, datetime
from pathlib import Path
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
from .regulatory_impact import resolve_verified_regulatory_impact
from .schema_contracts import verify_kpi_schema
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
    legal_grounding: dict[str, Any] | None = None
    schema_verification: dict[str, Any] | None = None
    model_authored_sql_allowed: bool = False


def prepare_execution(
    payload: TemplateToolExecutionRequest,
    *,
    legal_db_path: Path | None = None,
) -> tuple[ExecuteRequest, str, list[str], dict[str, Any] | None]:
    plan = build_tool_plan(payload.tool, payload.arguments)
    missing = sorted(set(plan.required_scope) - set(payload.granted_scopes))
    if missing:
        raise PermissionError(f"missing_required_scope:{','.join(missing)}")

    legal_grounding: dict[str, Any] | None = None
    if plan.tool == "regulatory_impact_query":
        db_path = legal_db_path or Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
        grounding = resolve_verified_regulatory_impact(
            db_path,
            instrument_id=plan.arguments["instrument_id"],
            as_of=date.fromisoformat(plan.arguments["as_of"]),
        )
        plan.arguments["verified_topics"] = list(grounding.topics)
        legal_grounding = {
            "instrument_id": grounding.instrument_id,
            "source_url": grounding.source_url,
            "citation_ids": list(grounding.citation_ids),
            "topics": list(grounding.topics),
            "as_of": plan.arguments["as_of"],
        }

    sql, parameters = compile_tool_plan(plan)
    contract_limit = int(plan.arguments.get("limit", payload.max_rows))
    effective_max_rows = min(payload.max_rows, contract_limit)
    request = ExecuteRequest(
        tool=plan.tool,
        sql=sql,
        parameters=parameters,
        requested_by=payload.requested_by,
        reason=payload.reason,
        max_rows=effective_max_rows,
        maximum_bytes_billed=payload.maximum_bytes_billed,
        timeout_ms=payload.timeout_ms,
    )
    return request, plan.query_id, plan.required_scope, legal_grounding


def _schema_verification(payload: TemplateToolExecutionRequest, adapter) -> dict[str, Any] | None:
    if payload.tool != "ops_kpi_query":
        return None
    metric = str(payload.arguments.get("metric") or "")
    return verify_kpi_schema(adapter, metric)


def execute_with_adapter(
    payload: TemplateToolExecutionRequest,
    *,
    adapter,
    audit_store: ExecutionAuditStore,
    legal_db_path: Path | None = None,
) -> TemplateToolExecutionResult:
    request, query_id, required_scope, legal_grounding = prepare_execution(
        payload, legal_db_path=legal_db_path
    )
    schema_verification = _schema_verification(payload, adapter)
    executor = SafeBigQueryExecutor(adapter, audit_store)
    execution = executor.run(request, execute=payload.execute)
    return TemplateToolExecutionResult(
        tool=payload.tool,
        query_id=query_id,
        required_scope=required_scope,
        execution=execution,
        legal_grounding=legal_grounding,
        schema_verification=schema_verification,
        model_authored_sql_allowed=False,
    )


class TemplateBigQueryAdapter(GoogleBigQueryAdapter):
    """BigQuery adapter for vetted templates, including named ARRAY parameters."""

    @staticmethod
    def _scalar_type(value: Any) -> str:
        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT64"
        if isinstance(value, float):
            return "FLOAT64"
        if isinstance(value, datetime):
            return "TIMESTAMP"
        if isinstance(value, date):
            return "DATE"
        if isinstance(value, str):
            return "STRING"
        raise ValueError("unsupported_query_parameter_type")

    def _parameters(self, values: dict[str, Any]):
        params = []
        for name, value in values.items():
            if isinstance(value, list):
                if not value:
                    array_type = "STRING"
                else:
                    array_type = self._scalar_type(value[0])
                    if any(self._scalar_type(item) != array_type for item in value):
                        raise ValueError(f"mixed_array_parameter_types:{name}")
                params.append(self.bigquery.ArrayQueryParameter(name, array_type, value))
                continue
            if value is None:
                raise ValueError(f"null_query_parameter_not_allowed:{name}")
            params.append(
                self.bigquery.ScalarQueryParameter(name, self._scalar_type(value), value)
            )
        return params

    def table_schema(self, table_id: str) -> dict[str, str]:
        table = self.client.get_table(table_id)
        return {field.name: field.field_type for field in table.schema}


router = APIRouter(prefix="/v1/tool-execution", tags=["tool-execution"])


@router.post("", response_model=TemplateToolExecutionResult)
def execute_template_tool(payload: TemplateToolExecutionRequest):
    if not EXECUTION_ENABLED:
        raise HTTPException(status_code=409, detail="BigQuery execution is disabled by default")
    try:
        db_path = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
        request, query_id, required_scope, legal_grounding = prepare_execution(
            payload, legal_db_path=db_path
        )
        adapter = TemplateBigQueryAdapter()
        schema_verification = _schema_verification(payload, adapter)
        audit_store = ExecutionAuditStore(db_path)
        execution = SafeBigQueryExecutor(adapter, audit_store).run(request, execute=payload.execute)
        return TemplateToolExecutionResult(
            tool=payload.tool,
            query_id=query_id,
            required_scope=required_scope,
            execution=execution,
            legal_grounding=legal_grounding,
            schema_verification=schema_verification,
            model_authored_sql_allowed=False,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
