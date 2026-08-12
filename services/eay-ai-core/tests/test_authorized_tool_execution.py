from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from uuid import UUID

import pytest
from fastapi import HTTPException
from pydantic import SecretStr

import app.authorized_tool_execution as authorized_module
from app.authorized_tool_execution import (
    AuthorizedTemplateToolExecutionRequest,
    JarvisAuthorizedExecutionAuditStore,
    execute_authorized_template_tool,
)
from app.bigquery_safe_executor import ExecutionResult
from app.jarvis_core_bridge import (
    JarvisCoreAuthorizationDenied,
    TrustedCoreExecutionContext,
    canonical_arguments_sha256,
    canonical_reason_sha256,
)
from app.jarvis_tenant_policy import (
    JarvisTenantExecutionPolicy,
    JarvisTenantPolicyError,
    legacy_caller_scope_execution_allowed,
)
from app.tool_execution import TemplateToolExecutionResult

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")


def arguments() -> dict[str, object]:
    return {
        "query": "milk",
        "field": "product",
        "limit": 10,
    }


def context(*, tenant_id: UUID = TENANT_A) -> TrustedCoreExecutionContext:
    args = arguments()
    reason = "catalog lookup"
    return TrustedCoreExecutionContext(
        request_id="core-request-1",
        tenant_id=tenant_id,
        actor_subject="user-1",
        tool="catalog_query",
        granted_scopes=("catalog:read",),
        authorization_fingerprint="a" * 64,
        arguments_sha256=canonical_arguments_sha256(args),
        reason_sha256=canonical_reason_sha256(reason),
    )


def payload() -> AuthorizedTemplateToolExecutionRequest:
    return AuthorizedTemplateToolExecutionRequest(
        grant_token=SecretStr("g" * 43),
        tool="catalog_query",
        arguments=arguments(),
        reason="catalog lookup",
        execute=False,
    )


class FakeAuthorizationClient:
    def __init__(self, result: TrustedCoreExecutionContext | Exception) -> None:
        self.result = result
        self.calls = 0

    def authorize(self, **_: object) -> TrustedCoreExecutionContext:
        self.calls += 1
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class FakeAuditStore:
    def __init__(self, *, fail_begin: bool = False, fail_finalize: bool = False) -> None:
        self.fail_begin = fail_begin
        self.fail_finalize = fail_finalize
        self.begun = 0
        self.finalized = 0

    def begin(self, _: TrustedCoreExecutionContext) -> None:
        self.begun += 1
        if self.fail_begin:
            raise RuntimeError("audit down")

    def finalize(self, *_: object, **__: object) -> None:
        self.finalized += 1
        if self.fail_finalize:
            raise RuntimeError("audit down")


def execution_result() -> TemplateToolExecutionResult:
    return TemplateToolExecutionResult(
        tool="catalog_query",
        query_id="catalog.lookup.v1",
        required_scope=["catalog:read"],
        execution=ExecutionResult(
            execution_id="execution-1",
            status="dry_run_ok",
            dry_run_bytes=1,
            maximum_bytes_billed=1024,
            row_count=0,
            rows=[],
            sql_sha256="b" * 64,
        ),
        model_authored_sql_allowed=False,
    )


def test_authorized_request_has_no_caller_scope_or_identity_fields() -> None:
    fields = set(AuthorizedTemplateToolExecutionRequest.model_fields)
    assert "granted_scopes" not in fields
    assert "requested_by" not in fields
    assert "tenant_id" not in fields
    assert "actor_subject" not in fields


def test_trusted_core_context_is_injected_into_legacy_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    def fake_execute(trusted_payload):
        captured["payload"] = trusted_payload
        return execution_result()

    monkeypatch.setattr(authorized_module, "execute_template_tool", fake_execute)
    audit = FakeAuditStore()
    result = execute_authorized_template_tool(
        payload(),
        FakeAuthorizationClient(context()),  # type: ignore[arg-type]
        JarvisTenantExecutionPolicy(environment="test", tenant_id=None),
        audit,  # type: ignore[arg-type]
    )

    trusted = captured["payload"]
    assert trusted.granted_scopes == ["catalog:read"]
    assert trusted.requested_by == "user-1"
    assert result.execution.execution_id == "execution-1"
    assert audit.begun == 1
    assert audit.finalized == 1


def test_core_denial_prevents_executor_and_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authorized_module,
        "execute_template_tool",
        lambda _: pytest.fail("executor must not run"),
    )
    audit = FakeAuditStore()

    with pytest.raises(HTTPException) as exc_info:
        execute_authorized_template_tool(
            payload(),
            FakeAuthorizationClient(JarvisCoreAuthorizationDenied("denied")),  # type: ignore[arg-type]
            JarvisTenantExecutionPolicy(environment="test", tenant_id=None),
            audit,  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403
    assert audit.begun == 0


def test_tenant_mismatch_prevents_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authorized_module,
        "execute_template_tool",
        lambda _: pytest.fail("executor must not run"),
    )

    with pytest.raises(HTTPException) as exc_info:
        execute_authorized_template_tool(
            payload(),
            FakeAuthorizationClient(context(tenant_id=TENANT_B)),  # type: ignore[arg-type]
            JarvisTenantExecutionPolicy(environment="production", tenant_id=TENANT_A),
            FakeAuditStore(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 403


def test_audit_begin_failure_prevents_executor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authorized_module,
        "execute_template_tool",
        lambda _: pytest.fail("executor must not run"),
    )

    with pytest.raises(HTTPException) as exc_info:
        execute_authorized_template_tool(
            payload(),
            FakeAuthorizationClient(context()),  # type: ignore[arg-type]
            JarvisTenantExecutionPolicy(environment="test", tenant_id=None),
            FakeAuditStore(fail_begin=True),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 503


def test_completion_audit_failure_returns_no_execution_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        authorized_module,
        "execute_template_tool",
        lambda _: execution_result(),
    )

    with pytest.raises(HTTPException) as exc_info:
        execute_authorized_template_tool(
            payload(),
            FakeAuthorizationClient(context()),  # type: ignore[arg-type]
            JarvisTenantExecutionPolicy(environment="test", tenant_id=None),
            FakeAuditStore(fail_finalize=True),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 503


def test_bridge_audit_stores_hashes_not_raw_invocation(tmp_path: Path) -> None:
    db_path = tmp_path / "audit.sqlite"
    store = JarvisAuthorizedExecutionAuditStore(db_path)
    ctx = context()
    store.begin(ctx)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM jarvis_authorized_execution_audit"
        ).fetchone()
        columns = [
            item[1]
            for item in conn.execute(
                "PRAGMA table_info(jarvis_authorized_execution_audit)"
            )
        ]

    assert row is not None
    serialized = "|".join("" if item is None else str(item) for item in row)
    assert "milk" not in serialized
    assert "catalog lookup" not in serialized
    assert "g" * 43 not in serialized
    assert "grant_token" not in columns
    assert "arguments" not in columns
    assert "reason" not in columns


def test_production_tenant_pin_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EAY_AI_ENVIRONMENT", "production")
    monkeypatch.delenv("EAY_JARVIS_TENANT_ID", raising=False)

    with pytest.raises(Exception, match="EAY_JARVIS_TENANT_ID"):
        JarvisTenantExecutionPolicy.from_environment()


def test_legacy_caller_scope_route_is_dev_test_only() -> None:
    assert legacy_caller_scope_execution_allowed("development") is True
    assert legacy_caller_scope_execution_allowed("test") is True
    assert legacy_caller_scope_execution_allowed("staging") is False
    assert legacy_caller_scope_execution_allowed("production") is False


def test_production_entrypoint_quarantines_legacy_scope_route(tmp_path: Path) -> None:
    env = dict(os.environ)
    env.update(
        {
            "EAY_AI_ENVIRONMENT": "production",
            "EAY_JARVIS_CORE_BRIDGE_ENABLED": "false",
            "EAY_JARVIS_TENANT_ID": str(TENANT_A),
            "EAY_AI_DB_PATH": str(tmp_path / "entrypoint.sqlite"),
        }
    )
    code = """
from app.entrypoint import app
paths = set(app.openapi().get('paths', {}))
assert '/v1/tool-execution' not in paths, sorted(paths)
assert '/v1/tool-execution/authorized' in paths, sorted(paths)
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=Path(__file__).resolve().parents[1],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
