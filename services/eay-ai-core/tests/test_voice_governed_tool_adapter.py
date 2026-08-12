import asyncio
import json

import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.platform_tool_authorizer import (
    PlatformToolAuthorizationDenied,
    TrustedToolExecutionContext,
    tool_arguments_sha256,
    tool_reason_sha256,
)
from app.tool_execution import TemplateToolExecutionRequest
from app.voice_async_runtime import CancellationToken
from app.voice_governed_tool_adapter import (
    GovernedTemplateToolAdapter,
    bind_template_tool_request,
)
from app.voice_session_ledger import VoiceSessionLedger
from app.voice_tool_bridge import VoiceToolBridge


class FakeBigQueryAdapter:
    def __init__(self):
        self.dry_run_calls = 0
        self.execute_calls = 0

    def dry_run(self, sql, parameters, *, timeout_ms):
        self.dry_run_calls += 1
        return 1024

    def execute(
        self,
        sql,
        parameters,
        *,
        timeout_ms,
        maximum_bytes_billed,
    ):
        self.execute_calls += 1
        return [{"sku": "SKU-1", "product_name": "Milk"}]


class FakePlatformAuthorizer:
    def __init__(self):
        self.calls = 0
        self.last_grant = None

    async def authorize(self, *, grant_token, plan, reason):
        self.calls += 1
        self.last_grant = grant_token
        return TrustedToolExecutionContext(
            request_id=f"voice-platform-{self.calls}",
            tenant_id="11111111-1111-4111-8111-111111111111",
            actor_subject="platform:voice-user-1",
            tool=plan.tool,
            granted_scopes=tuple(plan.required_scope),
            authorization_fingerprint="a" * 64,
            arguments_sha256=tool_arguments_sha256(plan.arguments),
            reason_sha256=tool_reason_sha256(reason),
        )


class DenyingPlatformAuthorizer:
    async def authorize(self, *, grant_token, plan, reason):
        del grant_token, plan, reason
        raise PlatformToolAuthorizationDenied("denied")


def _intent_and_request(
    tmp_path,
    *,
    arguments=None,
    reason="voice catalog lookup",
):
    args = arguments or {
        "query": "milk",
        "field": "product",
        "limit": 10,
    }
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    intent = VoiceToolBridge(ledger).seal_intent(
        session_id="session-1",
        language="en",
        tool_name="catalog_query",
        tool_call_id="tool-1",
        risk="read",
        arguments=args,
        reason=reason,
    )
    request = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments=args,
        grant_token="g" * 43,
        reason=reason,
        execute=True,
        max_rows=50,
    )
    return intent, request


def test_binding_rejects_argument_drift_after_voice_intent_is_sealed(
    tmp_path,
):
    intent, request = _intent_and_request(tmp_path)
    changed = request.model_copy(
        update={
            "arguments": {
                "query": "eggs",
                "field": "product",
                "limit": 10,
            }
        }
    )

    with pytest.raises(
        ValueError,
        match="voice_tool_bound_request_arguments_drift",
    ):
        bind_template_tool_request(
            intent=intent,
            request=changed,
        )


def test_binding_rejects_grant_drift_after_registration(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    binding = bind_template_tool_request(
        intent=intent,
        request=request,
    )
    changed = request.model_copy(
        update={"grant_token": request.grant_token.__class__("h" * 43)}
    )
    changed_binding = bind_template_tool_request(
        intent=intent,
        request=changed,
    )

    assert binding.grant_token_sha256 != changed_binding.grant_token_sha256
    assert binding.fingerprint != changed_binding.fingerprint


def test_binding_rejects_dry_run_only_request(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    dry_run = request.model_copy(update={"execute": False})

    with pytest.raises(
        ValueError,
        match="voice_tool_bound_request_execution_required",
    ):
        bind_template_tool_request(
            intent=intent,
            request=dry_run,
        )


def test_governed_adapter_authorizes_then_executes_and_builds_proof(
    tmp_path,
):
    intent, request = _intent_and_request(tmp_path)
    authorizer = FakePlatformAuthorizer()
    bq = FakeBigQueryAdapter()
    adapter = GovernedTemplateToolAdapter(
        authorizer=authorizer,  # type: ignore[arg-type]
        adapter=bq,
        audit_store=ExecutionAuditStore(
            tmp_path / "execution.db"
        ),
    )
    binding = adapter.register(intent=intent, request=request)
    assert len(binding.fingerprint) == 64
    assert "g" * 43 not in repr(binding)

    result = asyncio.run(
        adapter.execute(
            intent=intent,
            cancellation=CancellationToken(
                task_id="tool-1",
                turn_epoch=1,
            ),
        )
    )

    assert authorizer.calls == 1
    assert authorizer.last_grant == "g" * 43
    assert bq.dry_run_calls == 1
    assert bq.execute_calls == 1
    assert result.execution_proof.tool == "catalog_query"
    assert result.execution_proof.query_id == "catalog.lookup.v1"
    assert result.execution_proof.status == "executed"
    assert len(result.execution_proof.fingerprint) == 64
    payload = json.loads(result.content)
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["rows"] == [
        {"product_name": "Milk", "sku": "SKU-1"}
    ]


def test_platform_denial_prevents_voice_bigquery_execution(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    bq = FakeBigQueryAdapter()
    adapter = GovernedTemplateToolAdapter(
        authorizer=DenyingPlatformAuthorizer(),  # type: ignore[arg-type]
        adapter=bq,
        audit_store=ExecutionAuditStore(
            tmp_path / "execution.db"
        ),
    )
    adapter.register(intent=intent, request=request)

    with pytest.raises(PlatformToolAuthorizationDenied):
        asyncio.run(
            adapter.execute(
                intent=intent,
                cancellation=CancellationToken(
                    task_id="tool-1",
                    turn_epoch=1,
                ),
            )
        )

    assert bq.dry_run_calls == 0
    assert bq.execute_calls == 0


def test_registered_request_is_single_use(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    authorizer = FakePlatformAuthorizer()
    adapter = GovernedTemplateToolAdapter(
        authorizer=authorizer,  # type: ignore[arg-type]
        adapter=FakeBigQueryAdapter(),
        audit_store=ExecutionAuditStore(
            tmp_path / "execution.db"
        ),
    )
    adapter.register(intent=intent, request=request)
    cancellation = CancellationToken(
        task_id="tool-1",
        turn_epoch=1,
    )
    asyncio.run(
        adapter.execute(
            intent=intent,
            cancellation=cancellation,
        )
    )

    with pytest.raises(
        ValueError,
        match="voice_tool_bound_request_missing",
    ):
        asyncio.run(
            adapter.execute(
                intent=intent,
                cancellation=cancellation,
            )
        )

    assert authorizer.calls == 1


def test_template_voice_bridge_rejects_write_risk_even_with_same_payload(
    tmp_path,
):
    args = {
        "query": "milk",
        "field": "product",
        "limit": 10,
    }
    ledger = VoiceSessionLedger(tmp_path / "voice.db")
    intent = VoiceToolBridge(ledger).seal_intent(
        session_id="session-1",
        language="en",
        tool_name="catalog_query",
        tool_call_id="tool-1",
        risk="write",
        arguments=args,
        reason="attempt mutation through read bridge",
        approval_reference="human-approval-1",
    )
    request = TemplateToolExecutionRequest(
        tool="catalog_query",
        arguments=args,
        grant_token="g" * 43,
        reason="attempt mutation through read bridge",
        execute=True,
    )

    with pytest.raises(
        ValueError,
        match="voice_tool_template_bridge_read_only",
    ):
        bind_template_tool_request(
            intent=intent,
            request=request,
        )
