from __future__ import annotations

import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

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
from .jarvis_runtime import (
    JarvisRuntimeConfigurationError,
    build_platform_tool_authorizer,
)
from .kpi_provenance import provenance_from_activation
from .kpi_registry import get_kpi_definition
from .kpi_result_validation import (
    KpiResultValidationError,
    ResultValidatingAdapter,
    get_result_contract,
    get_result_contract_fingerprint,
)
from .kpi_runtime_contracts import verify_kpi_runtime_activation
from .kpi_semantics import verify_semantic_contract
from .platform_tool_authorizer import (
    PlatformToolAdmissionReleaseError,
    PlatformToolAuthorizationContractError,
    PlatformToolAuthorizationDenied,
    PlatformToolAuthorizationIndeterminate,
    PlatformToolAuthorizer,
    TrustedToolExecutionContext,
    validate_trusted_tool_execution_context,
)
from .query_templates import compile_tool_plan
from .regulatory_impact import resolve_verified_regulatory_impact
from .schema_contracts import verify_kpi_schema
from .tool_contracts import ToolName, ToolPlan, build_tool_plan

logger = logging.getLogger(__name__)


class TemplateToolExecutionRequest(BaseModel):
    """One exact reviewed invocation carrying only an opaque Platform grant."""

    model_config = ConfigDict(extra="forbid")

    tool: ToolName
    arguments: dict[str, Any]
    grant_token: SecretStr
    reason: str = Field(min_length=3, max_length=1000)
    execute: bool = False
    maximum_bytes_billed: int = Field(
        default=DEFAULT_MAX_BYTES,
        ge=1,
        le=10 * 1024 * 1024 * 1024,
    )
    timeout_ms: int = Field(
        default=DEFAULT_TIMEOUT_MS,
        ge=1000,
        le=120000,
    )
    max_rows: int = Field(default=500, ge=1, le=5000)

    @model_validator(mode="after")
    def validate_grant_token(self) -> TemplateToolExecutionRequest:
        token = self.grant_token.get_secret_value()
        if not 32 <= len(token) <= 256:
            raise ValueError("platform_tool_grant_invalid")
        return self


class TemplateToolExecutionResult(BaseModel):
    tool: ToolName
    query_id: str
    required_scope: list[str]
    execution: ExecutionResult
    legal_grounding: dict[str, Any] | None = None
    semantic_verification: dict[str, Any] | None = None
    schema_verification: dict[str, Any] | None = None
    runtime_activation: dict[str, Any] | None = None
    activation_provenance_fingerprint: str | None = None
    result_contract_fingerprint: str | None = None
    model_authored_sql_allowed: bool = False


def prepare_execution(
    payload: TemplateToolExecutionRequest,
    *,
    authorization_context: TrustedToolExecutionContext,
    plan: ToolPlan | None = None,
    legal_db_path: Path | None = None,
) -> tuple[ExecuteRequest, str, list[str], dict[str, Any] | None]:
    reviewed_plan = plan or build_tool_plan(
        payload.tool,
        payload.arguments,
    )
    validate_trusted_tool_execution_context(
        authorization_context,
        plan=reviewed_plan,
        reason=payload.reason,
    )

    legal_grounding: dict[str, Any] | None = None
    if reviewed_plan.tool == "regulatory_impact_query":
        db_path = legal_db_path or Path(
            os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db")
        )
        grounding = resolve_verified_regulatory_impact(
            db_path,
            instrument_id=reviewed_plan.arguments["instrument_id"],
            as_of=date.fromisoformat(
                reviewed_plan.arguments["as_of"]
            ),
        )
        # These topics are server-derived legal evidence. They are appended
        # only after the caller-authored arguments were authorized exactly.
        reviewed_plan.arguments["verified_topics"] = list(
            grounding.topics
        )
        legal_grounding = {
            "instrument_id": grounding.instrument_id,
            "source_url": grounding.source_url,
            "citation_ids": list(grounding.citation_ids),
            "topics": list(grounding.topics),
            "as_of": reviewed_plan.arguments["as_of"],
        }

    sql, parameters = compile_tool_plan(reviewed_plan)
    contract_limit = int(
        reviewed_plan.arguments.get("limit", payload.max_rows)
    )
    effective_max_rows = min(payload.max_rows, contract_limit)
    request = ExecuteRequest(
        tool=reviewed_plan.tool,
        sql=sql,
        parameters=parameters,
        requested_by=authorization_context.actor_subject,
        reason=payload.reason,
        max_rows=effective_max_rows,
        maximum_bytes_billed=payload.maximum_bytes_billed,
        timeout_ms=payload.timeout_ms,
        authorization_request_id=authorization_context.request_id,
        tenant_id=str(authorization_context.tenant_id),
        authorization_fingerprint=(
            authorization_context.authorization_fingerprint
        ),
    )
    return (
        request,
        reviewed_plan.query_id,
        reviewed_plan.required_scope,
        legal_grounding,
    )


def _semantic_verification(
    payload: TemplateToolExecutionRequest,
) -> dict[str, Any] | None:
    if payload.tool != "ops_kpi_query":
        return None
    metric = str(payload.arguments.get("metric") or "")
    definition = get_kpi_definition(metric)
    if not definition.semantic_contract_id:
        raise ValueError(
            f"kpi_semantic_contract_required:{metric}"
        )
    return verify_semantic_contract(
        metric=metric,
        contract_id=definition.semantic_contract_id,
    )


def _schema_verification(
    payload: TemplateToolExecutionRequest,
    adapter,
) -> dict[str, Any] | None:
    if payload.tool != "ops_kpi_query":
        return None
    metric = str(payload.arguments.get("metric") or "")
    return verify_kpi_schema(adapter, metric)


def _runtime_activation(
    payload: TemplateToolExecutionRequest,
    semantic_verification: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if payload.tool != "ops_kpi_query":
        return None
    if semantic_verification is None or schema_verification is None:
        raise ValueError(
            "kpi_runtime_activation_prerequisites_required"
        )
    metric = str(payload.arguments.get("metric") or "")
    start_raw = payload.arguments.get("start_date")
    end_raw = payload.arguments.get("end_date")
    start_date = (
        date.fromisoformat(str(start_raw))
        if start_raw
        else None
    )
    end_date = (
        date.fromisoformat(str(end_raw))
        if end_raw
        else None
    )
    return verify_kpi_runtime_activation(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        start_date=start_date,
        end_date=end_date,
    )


def _activation_provenance(
    payload: TemplateToolExecutionRequest,
    semantic_verification: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None,
    runtime_activation: dict[str, Any] | None,
) -> str | None:
    if payload.tool != "ops_kpi_query":
        return None
    if semantic_verification is None or schema_verification is None:
        raise ValueError(
            "kpi_activation_provenance_prerequisites_required"
        )
    metric = str(payload.arguments.get("metric") or "")
    return provenance_from_activation(
        metric=metric,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        runtime_activation=runtime_activation,
    )


def _result_contract_fingerprint(
    payload: TemplateToolExecutionRequest,
) -> str | None:
    if payload.tool != "ops_kpi_query":
        return None
    return get_result_contract_fingerprint(
        str(payload.arguments.get("metric") or "")
    )


def _attach_contract_audit(
    request: ExecuteRequest,
    semantic_verification: dict[str, Any] | None,
    schema_verification: dict[str, Any] | None,
    runtime_activation: dict[str, Any] | None = None,
    activation_provenance_fingerprint: str | None = None,
    result_contract_fingerprint: str | None = None,
) -> ExecuteRequest:
    if (
        semantic_verification is None
        and schema_verification is None
        and runtime_activation is None
        and activation_provenance_fingerprint is None
        and result_contract_fingerprint is None
    ):
        return request
    return request.model_copy(
        update={
            "semantic_contract_id": (
                str(semantic_verification["contract_id"])
                if semantic_verification
                else None
            ),
            "semantic_fingerprint": (
                str(semantic_verification["fingerprint"])
                if semantic_verification
                else None
            ),
            "schema_contract_id": (
                str(schema_verification["contract_id"])
                if schema_verification
                else None
            ),
            "schema_fingerprint": (
                str(schema_verification["observed_fingerprint"])
                if schema_verification
                else None
            ),
            "schema_evidence_fingerprint": (
                str(schema_verification["evidence_fingerprint"])
                if schema_verification
                and schema_verification.get("evidence_fingerprint")
                else None
            ),
            "unit_contract_fingerprint": (
                str(runtime_activation["unit_contract_fingerprint"])
                if runtime_activation
                and runtime_activation.get("unit_contract_fingerprint")
                else None
            ),
            "aggregation_contract_fingerprint": (
                str(
                    runtime_activation[
                        "aggregation_contract_fingerprint"
                    ]
                )
                if runtime_activation
                and runtime_activation.get(
                    "aggregation_contract_fingerprint"
                )
                else None
            ),
            "policy_contract_fingerprint": (
                str(runtime_activation["sla_contract_fingerprint"])
                if runtime_activation
                and runtime_activation.get("sla_contract_fingerprint")
                else None
            ),
            "formula_contract_fingerprint": (
                str(
                    runtime_activation[
                        "quantity_contract_fingerprint"
                    ]
                )
                if runtime_activation
                and runtime_activation.get(
                    "quantity_contract_fingerprint"
                )
                else None
            ),
            "result_contract_fingerprint": (
                result_contract_fingerprint
            ),
            "activation_provenance_fingerprint": (
                activation_provenance_fingerprint
            ),
        }
    )


def _execution_adapter(
    payload: TemplateToolExecutionRequest,
    adapter,
):
    if payload.tool != "ops_kpi_query":
        return adapter
    metric = str(payload.arguments.get("metric") or "")
    if get_result_contract(metric) is None:
        return adapter
    return ResultValidatingAdapter(adapter, metric=metric)


def _run_executor(
    *,
    payload: TemplateToolExecutionRequest,
    request: ExecuteRequest,
    adapter,
    audit_store: ExecutionAuditStore,
) -> ExecutionResult:
    try:
        return SafeBigQueryExecutor(
            _execution_adapter(payload, adapter),
            audit_store,
        ).run(
            request,
            execute=payload.execute,
        )
    except KpiResultValidationError:
        audit_store.save(
            payload=request,
            dry_run_bytes=None,
            status="rejected_result_contract",
        )
        raise


def execute_with_adapter(
    payload: TemplateToolExecutionRequest,
    *,
    authorization_context: TrustedToolExecutionContext,
    adapter,
    audit_store: ExecutionAuditStore,
    plan: ToolPlan | None = None,
    legal_db_path: Path | None = None,
) -> TemplateToolExecutionResult:
    request, query_id, required_scope, legal_grounding = (
        prepare_execution(
            payload,
            authorization_context=authorization_context,
            plan=plan,
            legal_db_path=legal_db_path,
        )
    )
    semantic_verification = _semantic_verification(payload)
    schema_verification = _schema_verification(payload, adapter)
    runtime_activation = _runtime_activation(
        payload,
        semantic_verification,
        schema_verification,
    )
    activation_provenance_fingerprint = _activation_provenance(
        payload,
        semantic_verification,
        schema_verification,
        runtime_activation,
    )
    result_contract_fingerprint = _result_contract_fingerprint(payload)
    request = _attach_contract_audit(
        request,
        semantic_verification,
        schema_verification,
        runtime_activation,
        activation_provenance_fingerprint,
        result_contract_fingerprint,
    )
    execution = _run_executor(
        payload=payload,
        request=request,
        adapter=adapter,
        audit_store=audit_store,
    )
    return TemplateToolExecutionResult(
        tool=payload.tool,
        query_id=query_id,
        required_scope=required_scope,
        execution=execution,
        legal_grounding=legal_grounding,
        semantic_verification=semantic_verification,
        schema_verification=schema_verification,
        runtime_activation=runtime_activation,
        activation_provenance_fingerprint=(
            activation_provenance_fingerprint
        ),
        result_contract_fingerprint=result_contract_fingerprint,
        model_authored_sql_allowed=False,
    )


async def authorize_and_execute_with_adapter(
    payload: TemplateToolExecutionRequest,
    *,
    authorizer: PlatformToolAuthorizer,
    adapter,
    audit_store: ExecutionAuditStore,
    legal_db_path: Path | None = None,
) -> TemplateToolExecutionResult:
    """Consume one Platform grant, execute once, then release admission."""

    plan = build_tool_plan(payload.tool, payload.arguments)
    authorization_context = await authorizer.authorize(
        grant_token=payload.grant_token.get_secret_value(),
        plan=plan,
        reason=payload.reason,
    )
    try:
        return execute_with_adapter(
            payload,
            authorization_context=authorization_context,
            adapter=adapter,
            audit_store=audit_store,
            plan=plan,
            legal_db_path=legal_db_path,
        )
    finally:
        try:
            await authorizer.release_admission(authorization_context)
        except PlatformToolAdmissionReleaseError:
            # Do not mask a known execution result/outcome. The Platform lease
            # expires by Redis server time even if early release is unavailable.
            logger.warning(
                "Jarvis admission lease was not released early",
                exc_info=True,
            )


class TemplateBigQueryAdapter(GoogleBigQueryAdapter):
    """BigQuery adapter for vetted templates, including ARRAY parameters."""

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
                    if any(
                        self._scalar_type(item) != array_type
                        for item in value
                    ):
                        raise ValueError(
                            f"mixed_array_parameter_types:{name}"
                        )
                params.append(
                    self.bigquery.ArrayQueryParameter(
                        name,
                        array_type,
                        value,
                    )
                )
                continue
            if value is None:
                raise ValueError(
                    f"null_query_parameter_not_allowed:{name}"
                )
            params.append(
                self.bigquery.ScalarQueryParameter(
                    name,
                    self._scalar_type(value),
                    value,
                )
            )
        return params

    def table_schema(self, table_id: str) -> dict[str, str]:
        table = self.client.get_table(table_id)
        return {
            field.name: field.field_type
            for field in table.schema
        }


router = APIRouter(
    prefix="/v1/tool-execution",
    tags=["tool-execution"],
)


@router.post("", response_model=TemplateToolExecutionResult)
async def execute_template_tool(
    payload: TemplateToolExecutionRequest,
):
    if not EXECUTION_ENABLED:
        raise HTTPException(
            status_code=409,
            detail="BigQuery execution is disabled by default",
        )

    try:
        # Local runtime preflight happens before consuming the single-use grant.
        adapter = TemplateBigQueryAdapter()
        authorizer = build_platform_tool_authorizer()
        db_path = Path(
            os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db")
        )
        return await authorize_and_execute_with_adapter(
            payload,
            authorizer=authorizer,
            adapter=adapter,
            audit_store=ExecutionAuditStore(db_path),
            legal_db_path=db_path,
        )
    except PlatformToolAuthorizationDenied as exc:
        raise HTTPException(
            status_code=403,
            detail="Tool execution authorization denied",
        ) from exc
    except PlatformToolAuthorizationIndeterminate as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Tool authorization outcome is unknown; "
                "do not retry this grant"
            ),
        ) from exc
    except PlatformToolAuthorizationContractError as exc:
        raise HTTPException(
            status_code=503,
            detail="Tool authorization contract failed closed",
        ) from exc
    except JarvisRuntimeConfigurationError as exc:
        raise HTTPException(
            status_code=503,
            detail="Jarvis authorization runtime is unavailable",
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
