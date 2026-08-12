from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, SecretStr

from .bigquery_safe_executor import DEFAULT_MAX_BYTES, DEFAULT_TIMEOUT_MS
from .jarvis_core_bridge import (
    JarvisCoreAuthorizationClient,
    JarvisCoreAuthorizationDenied,
    JarvisCoreAuthorizationProtocolError,
    JarvisCoreAuthorizationUnavailable,
    JarvisCoreBridgeConfigurationError,
    JarvisCoreBridgeSettings,
    TrustedCoreExecutionContext,
)
from .jarvis_tenant_policy import (
    JarvisTenantExecutionPolicy,
    JarvisTenantPolicyError,
)
from .tool_contracts import ToolName
from .tool_execution import (
    TemplateToolExecutionRequest,
    TemplateToolExecutionResult,
    execute_template_tool,
)

router = APIRouter(prefix="/v1/tool-execution", tags=["tool-execution"])


class AuthorizedTemplateToolExecutionRequest(BaseModel):
    grant_token: SecretStr
    tool: ToolName
    arguments: dict[str, Any]
    reason: str = Field(min_length=3, max_length=1000)
    execute: bool = False
    maximum_bytes_billed: int = Field(
        default=DEFAULT_MAX_BYTES,
        ge=1,
        le=10 * 1024 * 1024 * 1024,
    )
    timeout_ms: int = Field(default=DEFAULT_TIMEOUT_MS, ge=1000, le=120000)
    max_rows: int = Field(default=500, ge=1, le=5000)


class JarvisAuthorizedExecutionAuditStore:
    """Durable bridge audit without raw grants, arguments or reasons."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jarvis_authorized_execution_audit (
                    authorization_request_id TEXT PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    actor_subject TEXT NOT NULL,
                    tool TEXT NOT NULL,
                    authorization_fingerprint TEXT NOT NULL,
                    arguments_sha256 TEXT NOT NULL,
                    reason_sha256 TEXT NOT NULL,
                    execution_id TEXT,
                    execution_status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT
                )
                """
            )

    def begin(self, context: TrustedCoreExecutionContext) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO jarvis_authorized_execution_audit (
                    authorization_request_id,
                    tenant_id,
                    actor_subject,
                    tool,
                    authorization_fingerprint,
                    arguments_sha256,
                    reason_sha256,
                    execution_status,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'authorized', ?)
                """,
                (
                    context.request_id,
                    str(context.tenant_id),
                    context.actor_subject,
                    context.tool,
                    context.authorization_fingerprint,
                    context.arguments_sha256,
                    context.reason_sha256,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    def finalize(
        self,
        context: TrustedCoreExecutionContext,
        *,
        execution_id: str | None,
        execution_status: str,
    ) -> None:
        with sqlite3.connect(self.db_path) as conn:
            updated = conn.execute(
                """
                UPDATE jarvis_authorized_execution_audit
                SET execution_id = ?, execution_status = ?, completed_at = ?
                WHERE authorization_request_id = ?
                """,
                (
                    execution_id,
                    execution_status,
                    datetime.now(timezone.utc).isoformat(),
                    context.request_id,
                ),
            ).rowcount
        if updated != 1:
            raise RuntimeError("jarvis_execution_audit_context_missing")


@lru_cache
def get_authorization_client() -> JarvisCoreAuthorizationClient:
    settings = JarvisCoreBridgeSettings.from_environment()
    return JarvisCoreAuthorizationClient(settings)


@lru_cache
def get_tenant_policy() -> JarvisTenantExecutionPolicy:
    return JarvisTenantExecutionPolicy.from_environment()


@lru_cache
def get_authorized_execution_audit_store() -> JarvisAuthorizedExecutionAuditStore:
    db_path = Path(os.getenv("EAY_AI_DB_PATH", "./data/eay_ai.db"))
    return JarvisAuthorizedExecutionAuditStore(db_path)


def _bridge_unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Platform Core tool authorization is unavailable",
    )


@router.post(
    "/authorized",
    response_model=TemplateToolExecutionResult,
)
def execute_authorized_template_tool(
    payload: AuthorizedTemplateToolExecutionRequest,
    authorization_client: Annotated[
        JarvisCoreAuthorizationClient,
        Depends(get_authorization_client),
    ],
    tenant_policy: Annotated[
        JarvisTenantExecutionPolicy,
        Depends(get_tenant_policy),
    ],
    audit_store: Annotated[
        JarvisAuthorizedExecutionAuditStore,
        Depends(get_authorized_execution_audit_store),
    ],
) -> TemplateToolExecutionResult:
    """Execute only after Platform Core consumes the exact user grant."""

    try:
        context = authorization_client.authorize(
            grant_token=payload.grant_token,
            tool=payload.tool,
            arguments=payload.arguments,
            reason=payload.reason,
        )
        tenant_policy.authorize(context)
    except JarvisCoreAuthorizationDenied as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI tool execution is not authorized",
        ) from exc
    except JarvisTenantPolicyError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="AI tool execution tenant is not authorized",
        ) from exc
    except (
        JarvisCoreAuthorizationUnavailable,
        JarvisCoreAuthorizationProtocolError,
        JarvisCoreBridgeConfigurationError,
    ) as exc:
        raise _bridge_unavailable(exc) from exc

    try:
        audit_store.begin(context)
    except Exception as exc:
        # Core already consumed the grant. Never continue execution without a
        # durable AI-side record of the trusted tenant/actor authorization.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool execution audit is unavailable",
        ) from exc

    trusted_payload = TemplateToolExecutionRequest(
        tool=payload.tool,
        arguments=payload.arguments,
        granted_scopes=list(context.granted_scopes),
        requested_by=context.actor_subject,
        reason=payload.reason,
        execute=payload.execute,
        maximum_bytes_billed=payload.maximum_bytes_billed,
        timeout_ms=payload.timeout_ms,
        max_rows=payload.max_rows,
    )

    try:
        result = execute_template_tool(trusted_payload)
    except HTTPException as exc:
        try:
            audit_store.finalize(
                context,
                execution_id=None,
                execution_status=f"rejected_http_{exc.status_code}",
            )
        except Exception as audit_exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI tool execution audit is unavailable",
            ) from audit_exc
        raise
    except Exception as exc:
        try:
            audit_store.finalize(
                context,
                execution_id=None,
                execution_status="execution_error",
            )
        except Exception as audit_exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="AI tool execution audit is unavailable",
            ) from audit_exc
        raise

    try:
        audit_store.finalize(
            context,
            execution_id=result.execution.execution_id,
            execution_status=result.execution.status,
        )
    except Exception as exc:
        # The read may already have completed, but no rows are returned to the
        # caller when the durable completion audit cannot be persisted.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI tool execution audit is unavailable",
        ) from exc

    return result
