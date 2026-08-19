from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from app.bigquery_safe_executor import ExecutionAuditStore
from app.platform_tool_authorizer import (
    PlatformToolAuthorizationDenied,
    PlatformToolAuthorizationIndeterminate,
    TrustedToolExecutionContext,
    tool_arguments_sha256,
    tool_reason_sha256,
)
from app.tool_execution import (
    TemplateToolExecutionRequest,
    authorize_and_execute_with_adapter,
)


class RecordingAdapter:
    def __init__(self, *, fail_after_authorization: bool = False):
        self.dry_run_calls = 0
        self.execute_calls = 0
        self.fail_after_authorization = fail_after_authorization

    def dry_run(self, sql, parameters, *, timeout_ms):
        del sql, parameters, timeout_ms
        self.dry_run_calls += 1
        if self.fail_after_authorization:
            raise RuntimeError("downstream execution failure")
        return 100

    def execute(
        self,
        sql,
        parameters,
        *,
        timeout_ms,
        maximum_bytes_billed,
    ):
        del sql, parameters, timeout_ms, maximum_bytes_billed
        self.execute_calls += 1
        return [{"product_name": "Milk"}]


def trusted_context(*, plan, reason: str, arguments_sha256: str | None = None):
    return TrustedToolExecutionContext(
        request_id="platform-request-1",
        tenant_id="11111111-1111-4111-8111-111111111111",
        actor_subject="platform:user-1",
        tool=plan.tool,
        granted_scopes=tuple(plan.required_scope),
        data_scope={"store_names": []},
        data_scope_fingerprint="d" * 64,
        tenant_entity_ids=("YS_TR",),
        tenant_query_context_fingerprint="q" * 64,
        query_contract_id="ops.catalog.v1",
        query_contract_revision=1,
        query_contract_fingerprint="c" * 64,
        execution_scope_fingerprint="e" * 64,
        authorization_fingerprint="a" * 64,
        arguments_sha256=(
            arguments_sha256 or tool_arguments_sha256(plan.arguments)
        ),
        reason_sha256=tool_reason_sha256(reason),
        admission_lease_token=SecretStr("l" * 43),
        admission_lease_ttl_seconds=135,
    )


class SuccessfulAuthorizer:
    def __init__(self):
        self.calls = 0
        self.release_calls = 0
        self.grants: list[str] = []

    async def authorize(self, *, grant_token, plan, reason):
        self.calls += 1
        self.grants.append(grant_token)
        context = trusted_context(plan=plan, reason=reason)
        return context.model_copy(
            update={"request_id": f"platform-{self.calls}"}
        )

    async def release_admission(self, context):
        assert context.admission_lease_token.get_secret_value() == "l" * 43
        self.release_calls += 1


class DenyingAuthorizer:
    async def authorize(self, *, grant_token, plan, reason):
        del grant_token, plan, reason
        raise PlatformToolAuthorizationDenied("denied")


class IndeterminateAuthorizer:
    async def authorize(self, *, grant_token, plan, reason):
        del grant_token, plan, reason
        raise PlatformToolAuthorizationIndeterminate("unknown")


class ForgingAuthorizer:
    def __init__(self):
        self.release_calls = 0

    async def authorize(self, *, grant_token, plan, reason):
        del grant_token
        return trusted_context(
            plan=plan,
            reason=reason,
            arguments_sha256="b" * 64,
        )

    async def release_admission(self, context):
        del context
        self.release_calls += 1


def request(*, execute: bool = True) -> TemplateToolExecutionRequest:
    return TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments={
            "query": "milk",
            "field": "product",
            "limit": 10,
        },
        grant_token=SecretStr("g" * 43),
        reason="governed catalog lookup",
        execute=execute,
        max_rows=10,
    )


def run_governed(
    payload: TemplateToolExecutionRequest,
    *,
    authorizer,
    adapter,
    audit_path: Path,
):
    return asyncio.run(
        authorize_and_execute_with_adapter(
            payload,
            authorizer=authorizer,
            adapter=adapter,
            audit_store=ExecutionAuditStore(audit_path),
        )
    )


def test_public_request_has_no_caller_authority_surface() -> None:
    fields = set(TemplateToolExecutionRequest.model_fields)

    assert "grant_token" in fields
    assert "granted_scopes" not in fields
    assert "requested_by" not in fields
    assert "tenant_id" not in fields
    assert "actor_subject" not in fields
    assert "permissions" not in fields

    with pytest.raises(ValidationError, match="extra_forbidden"):
        TemplateToolExecutionRequest(
            tool="catalog_query",
            arguments={
                "query": "milk",
                "field": "product",
                "limit": 10,
            },
            grant_token=SecretStr("g" * 43),
            reason="governed catalog lookup",
            granted_scopes=["catalog:read"],
        )


def test_grant_token_is_secret_in_request_representation() -> None:
    payload = request()

    assert "g" * 43 not in repr(payload)
    assert payload.grant_token.get_secret_value() == "g" * 43


def test_platform_success_authorizes_once_then_executes_once(tmp_path) -> None:
    authorizer = SuccessfulAuthorizer()
    adapter = RecordingAdapter()

    result = run_governed(
        request(),
        authorizer=authorizer,
        adapter=adapter,
        audit_path=tmp_path / "execution.db",
    )

    assert authorizer.calls == 1
    assert authorizer.release_calls == 1
    assert authorizer.grants == ["g" * 43]
    assert adapter.dry_run_calls == 1
    assert adapter.execute_calls == 1
    assert result.execution.status == "executed"


@pytest.mark.parametrize(
    "authorizer",
    [DenyingAuthorizer(), IndeterminateAuthorizer()],
)
def test_platform_failure_prevents_any_bigquery_call(
    tmp_path,
    authorizer,
) -> None:
    adapter = RecordingAdapter()

    with pytest.raises(
        (
            PlatformToolAuthorizationDenied,
            PlatformToolAuthorizationIndeterminate,
        )
    ):
        run_governed(
            request(),
            authorizer=authorizer,
            adapter=adapter,
            audit_path=tmp_path / "execution.db",
        )

    assert adapter.dry_run_calls == 0
    assert adapter.execute_calls == 0


def test_forged_platform_context_is_revalidated_before_bigquery(tmp_path) -> None:
    adapter = RecordingAdapter()
    authorizer = ForgingAuthorizer()

    with pytest.raises(RuntimeError, match="different arguments"):
        run_governed(
            request(),
            authorizer=authorizer,
            adapter=adapter,
            audit_path=tmp_path / "execution.db",
        )

    assert authorizer.release_calls == 1
    assert adapter.dry_run_calls == 0
    assert adapter.execute_calls == 0


def test_executor_failure_after_authorization_never_reauthorizes_grant(
    tmp_path,
) -> None:
    authorizer = SuccessfulAuthorizer()
    adapter = RecordingAdapter(fail_after_authorization=True)

    with pytest.raises(RuntimeError, match="downstream execution failure"):
        run_governed(
            request(),
            authorizer=authorizer,
            adapter=adapter,
            audit_path=tmp_path / "execution.db",
        )

    assert authorizer.calls == 1
    assert authorizer.release_calls == 1
    assert adapter.dry_run_calls == 1
    assert adapter.execute_calls == 0
