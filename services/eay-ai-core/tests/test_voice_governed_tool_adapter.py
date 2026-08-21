import asyncio
import json

import pytest

from app.bigquery_safe_executor import ExecutionAuditStore
from app.tool_execution import TemplateToolExecutionRequest
from app.voice_async_runtime import CancellationToken
from app.voice_governed_tool_adapter import GovernedTemplateToolAdapter, bind_template_tool_request
from app.voice_session_ledger import VoiceSessionLedger
from app.voice_tool_bridge import VoiceToolBridge


class FakeBigQueryAdapter:
    def dry_run(self, sql, parameters, *, timeout_ms):
        return 1024

    def execute(self, sql, parameters, *, timeout_ms, maximum_bytes_billed):
        return [{"sku": "SKU-1", "product_name": "Milk"}]


def _intent_and_request(tmp_path, *, arguments=None, reason="voice catalog lookup"):
    args = arguments or {"query": "milk", "field": "product", "limit": 10}
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
        granted_scopes=["catalog:read"],
        requested_by="voice:user-1",
        reason=reason,
        execute=True,
        max_rows=50,
    )
    return intent, request


def test_binding_rejects_argument_drift_after_voice_intent_is_sealed(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    changed = request.model_copy(update={"arguments": {"query": "eggs", "field": "product", "limit": 10}})

    with pytest.raises(ValueError, match="voice_tool_bound_request_arguments_drift"):
        bind_template_tool_request(intent=intent, request=changed)


def test_binding_rejects_dry_run_only_request(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    dry_run = request.model_copy(update={"execute": False})

    with pytest.raises(ValueError, match="voice_tool_bound_request_execution_required"):
        bind_template_tool_request(intent=intent, request=dry_run)


def test_governed_adapter_executes_existing_tool_path_and_builds_proof(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    adapter = GovernedTemplateToolAdapter(
        adapter=FakeBigQueryAdapter(),
        audit_store=ExecutionAuditStore(tmp_path / "execution.db"),
    )
    binding = adapter.register(intent=intent, request=request)
    assert len(binding.fingerprint) == 64

    result = asyncio.run(
        adapter.execute(
            intent=intent,
            cancellation=CancellationToken(task_id="tool-1", turn_epoch=1),
        )
    )

    assert result.execution_proof.tool == "catalog_query"
    assert result.execution_proof.query_id == "catalog.lookup.v1"
    assert result.execution_proof.status == "executed"
    assert len(result.execution_proof.fingerprint) == 64
    payload = json.loads(result.content)
    assert payload["execution"]["status"] == "executed"
    assert payload["execution"]["rows"] == [{"product_name": "Milk", "sku": "SKU-1"}]


def test_registered_request_is_single_use(tmp_path):
    intent, request = _intent_and_request(tmp_path)
    adapter = GovernedTemplateToolAdapter(
        adapter=FakeBigQueryAdapter(),
        audit_store=ExecutionAuditStore(tmp_path / "execution.db"),
    )
    adapter.register(intent=intent, request=request)
    cancellation = CancellationToken(task_id="tool-1", turn_epoch=1)
    asyncio.run(adapter.execute(intent=intent, cancellation=cancellation))

    with pytest.raises(ValueError, match="voice_tool_bound_request_missing"):
        asyncio.run(adapter.execute(intent=intent, cancellation=cancellation))


def test_template_voice_bridge_rejects_write_risk_even_with_same_payload(tmp_path):
    args = {"query": "milk", "field": "product", "limit": 10}
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
        granted_scopes=["catalog:read"],
        reason="attempt mutation through read bridge",
        execute=True,
    )

    with pytest.raises(ValueError, match="voice_tool_template_bridge_read_only"):
        bind_template_tool_request(intent=intent, request=request)
