from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .bigquery_safe_executor import ExecutionAuditStore
from .tool_execution import TemplateToolExecutionRequest, execute_with_adapter
from .voice_async_runtime import CancellationToken
from .voice_tool_bridge import VoiceToolIntent
from .voice_tool_execution_provenance import GovernedVoiceToolResult, seal_tool_execution_proof


def _sha256(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reason_sha256(reason: str) -> str:
    normalized = str(reason or "").strip()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class BoundVoiceToolRequest:
    """Transient binding between a sealed voice intent and a governed tool request.

    The actual request stays in process memory only. The binding fingerprint is safe to
    persist because it contains hashes/identifiers rather than the raw arguments.
    """

    tool_call_id: str
    intent_fingerprint: str
    arguments_sha256: str
    reason_sha256: str
    granted_scopes_sha256: str
    requested_by_sha256: str | None
    fingerprint: str


def bind_template_tool_request(
    *,
    intent: VoiceToolIntent,
    request: TemplateToolExecutionRequest,
) -> BoundVoiceToolRequest:
    if str(request.tool) != intent.tool_name:
        raise ValueError("voice_tool_bound_request_tool_mismatch")
    if intent.risk != "read":
        # The current reviewed template execution surface is read-only. Future write
        # adapters must use a distinct contract instead of smuggling mutations through
        # this bridge.
        raise ValueError("voice_tool_template_bridge_read_only")
    if request.execute is not True:
        raise ValueError("voice_tool_bound_request_execution_required")

    args_sha = _sha256(request.arguments)
    reason_sha = _reason_sha256(request.reason)
    if args_sha != intent.arguments_sha256:
        raise ValueError("voice_tool_bound_request_arguments_drift")
    if reason_sha != intent.reason_sha256:
        raise ValueError("voice_tool_bound_request_reason_drift")

    scopes_sha = _sha256(sorted(set(request.granted_scopes)))
    actor_sha = (
        hashlib.sha256(request.requested_by.strip().encode("utf-8")).hexdigest()
        if request.requested_by and request.requested_by.strip()
        else None
    )
    payload = {
        "tool_call_id": intent.tool_call_id,
        "intent_fingerprint": intent.fingerprint,
        "arguments_sha256": args_sha,
        "reason_sha256": reason_sha,
        "granted_scopes_sha256": scopes_sha,
        "requested_by_sha256": actor_sha,
    }
    return BoundVoiceToolRequest(**payload, fingerprint=_sha256(payload))


class GovernedTemplateToolAdapter:
    """Execute exact, transient voice requests through the existing governed tool path.

    This is deliberately not a generic model-authored tool adapter. A server-side caller
    must first register a request whose raw arguments exactly match the sealed
    VoiceToolIntent. Execution then goes through ``execute_with_adapter`` so scope,
    reviewed SQL template, KPI schema/semantic contracts, legal grounding, cost limits,
    KVKK masking and BigQuery audit remain authoritative.
    """

    def __init__(
        self,
        *,
        adapter,
        audit_store: ExecutionAuditStore,
        legal_db_path: Path | None = None,
    ) -> None:
        self.adapter = adapter
        self.audit_store = audit_store
        self.legal_db_path = legal_db_path
        self._requests: dict[str, tuple[TemplateToolExecutionRequest, BoundVoiceToolRequest]] = {}

    def register(
        self,
        *,
        intent: VoiceToolIntent,
        request: TemplateToolExecutionRequest,
    ) -> BoundVoiceToolRequest:
        if intent.tool_call_id in self._requests:
            raise ValueError("voice_tool_bound_request_duplicate")
        binding = bind_template_tool_request(intent=intent, request=request)
        self._requests[intent.tool_call_id] = (request, binding)
        return binding

    async def execute(
        self,
        *,
        intent: VoiceToolIntent,
        cancellation: CancellationToken,
    ) -> GovernedVoiceToolResult:
        cancellation.checkpoint()
        entry = self._requests.pop(intent.tool_call_id, None)
        if entry is None:
            raise ValueError("voice_tool_bound_request_missing")
        request, binding = entry
        current = bind_template_tool_request(intent=intent, request=request)
        if current != binding:
            raise ValueError("voice_tool_bound_request_fingerprint_drift")

        result = await asyncio.to_thread(
            execute_with_adapter,
            request,
            adapter=self.adapter,
            audit_store=self.audit_store,
            legal_db_path=self.legal_db_path,
        )
        cancellation.checkpoint()
        if result.execution.status != "executed":
            raise ValueError(f"voice_tool_execution_not_usable:{result.execution.status}")

        proof = seal_tool_execution_proof(result)
        # This content is transient live-runtime material. The async coordinator hashes
        # it before durable audit; neither this adapter nor the voice ledger persists it.
        content = json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return GovernedVoiceToolResult(content=content, execution_proof=proof)
