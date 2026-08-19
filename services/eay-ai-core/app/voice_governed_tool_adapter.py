from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from .bigquery_safe_executor import ExecutionAuditStore
from .platform_tool_authorizer import PlatformToolAuthorizer
from .tool_execution import (
    TemplateToolExecutionRequest,
    authorize_and_execute_with_adapter,
)
from .voice_async_runtime import CancellationToken
from .voice_tool_bridge import VoiceToolIntent
from .voice_tool_execution_provenance import (
    GovernedVoiceToolResult,
    seal_tool_execution_proof,
)


def _sha256(payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _reason_sha256(reason: str) -> str:
    normalized = str(reason or "").strip()
    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


@dataclass(frozen=True)
class BoundVoiceToolRequest:
    """Transient binding between a sealed intent and governed grant request."""

    tool_call_id: str
    intent_fingerprint: str
    arguments_sha256: str
    reason_sha256: str
    grant_token_sha256: str
    fingerprint: str


def bind_template_tool_request(
    *,
    intent: VoiceToolIntent,
    request: TemplateToolExecutionRequest,
) -> BoundVoiceToolRequest:
    if str(request.tool) != intent.tool_name:
        raise ValueError("voice_tool_bound_request_tool_mismatch")
    if intent.risk != "read":
        raise ValueError("voice_tool_template_bridge_read_only")
    if request.execute is not True:
        raise ValueError(
            "voice_tool_bound_request_execution_required"
        )

    args_sha = _sha256(request.arguments)
    reason_sha = _reason_sha256(request.reason)
    if args_sha != intent.arguments_sha256:
        raise ValueError(
            "voice_tool_bound_request_arguments_drift"
        )
    if reason_sha != intent.reason_sha256:
        raise ValueError(
            "voice_tool_bound_request_reason_drift"
        )

    grant_token_sha = hashlib.sha256(
        request.grant_token.get_secret_value().encode("utf-8")
    ).hexdigest()
    payload = {
        "tool_call_id": intent.tool_call_id,
        "intent_fingerprint": intent.fingerprint,
        "arguments_sha256": args_sha,
        "reason_sha256": reason_sha,
        "grant_token_sha256": grant_token_sha,
    }
    return BoundVoiceToolRequest(
        **payload,
        fingerprint=_sha256(payload),
    )


class GovernedTemplateToolAdapter:
    """Authorize and execute exact transient voice requests at most once.

    A server-side caller registers an opaque Platform-issued grant together
    with arguments that exactly match the sealed VoiceToolIntent. Scope,
    tenant and actor identity are never supplied here: Platform Core recovers
    them from the single-use grant before the reviewed query may execute.
    """

    def __init__(
        self,
        *,
        authorizer: PlatformToolAuthorizer,
        adapter,
        audit_store: ExecutionAuditStore,
        legal_db_path: Path | None = None,
    ) -> None:
        self.authorizer = authorizer
        self.adapter = adapter
        self.audit_store = audit_store
        self.legal_db_path = legal_db_path
        self._requests: dict[
            str,
            tuple[
                TemplateToolExecutionRequest,
                BoundVoiceToolRequest,
            ],
        ] = {}

    def register(
        self,
        *,
        intent: VoiceToolIntent,
        request: TemplateToolExecutionRequest,
    ) -> BoundVoiceToolRequest:
        if intent.tool_call_id in self._requests:
            raise ValueError(
                "voice_tool_bound_request_duplicate"
            )
        binding = bind_template_tool_request(
            intent=intent,
            request=request,
        )
        self._requests[intent.tool_call_id] = (
            request,
            binding,
        )
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
            raise ValueError(
                "voice_tool_bound_request_missing"
            )
        request, binding = entry
        current = bind_template_tool_request(
            intent=intent,
            request=request,
        )
        if current != binding:
            raise ValueError(
                "voice_tool_bound_request_fingerprint_drift"
            )

        result = await authorize_and_execute_with_adapter(
            request,
            authorizer=self.authorizer,
            adapter=self.adapter,
            audit_store=self.audit_store,
            legal_db_path=self.legal_db_path,
        )
        cancellation.checkpoint()
        if result.execution.status != "executed":
            raise ValueError(
                "voice_tool_execution_not_usable:"
                f"{result.execution.status}"
            )

        proof = seal_tool_execution_proof(result)
        content = json.dumps(
            result.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        return GovernedVoiceToolResult(
            content=content,
            execution_proof=proof,
        )
