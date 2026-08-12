"""Fail-closed orchestration boundary for Jarvis tool execution.

This module composes existing trust boundaries without widening any of them:
1. verify and consume the dedicated EAY AI Core machine assertion;
2. derive tenant/user authority from the resolved Platform principal only;
3. consume the invocation-bound single-use tool grant;
4. invoke only an explicitly registered executor;
5. emit sanitized audit metadata that contains no bearer tokens, raw arguments,
   human reason text, or tool result payloads.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from app.core.ai_tool_authorization import (
    AiToolName,
    PrincipalLike,
    derive_ai_tool_capability,
)
from app.core.ai_tool_grants import (
    RedisAiToolGrantStore,
    canonical_arguments_sha256,
    canonical_reason_sha256,
)
from app.core.jarvis_service_identity import (
    JarvisServiceVerifierSettings,
    VerifiedJarvisService,
)
from app.core.jarvis_service_replay import (
    RedisJarvisServiceReplayGuard,
    verify_and_consume_jarvis_service_assertion,
)

JarvisExecutor = Callable[[Mapping[str, Any]], Awaitable[Any]]


class JarvisExecutionError(RuntimeError):
    """Base failure for the internal Jarvis execution boundary."""


class JarvisExecutorUnavailable(JarvisExecutionError):
    """The requested reviewed tool has no registered runtime executor."""


class JarvisAuditSink(Protocol):
    async def __call__(self, event: Mapping[str, object]) -> None: ...


@dataclass(frozen=True)
class JarvisExecutionResult:
    tool: AiToolName
    result: Any
    service_assertion_id_sha256: str
    authorization_fingerprint: str


def _assertion_id_sha256(verified: VerifiedJarvisService) -> str:
    return hashlib.sha256(
        verified.assertion_id.encode("utf-8")
    ).hexdigest()


async def _emit_sanitized_audit(
    audit_sink: JarvisAuditSink | None,
    *,
    decision: str,
    tool: AiToolName,
    tenant_id: str,
    actor_subject: str,
    assertion_id_sha256: str,
    authorization_fingerprint: str,
    arguments_sha256: str,
    reason_sha256: str,
    error_type: str | None = None,
) -> None:
    if audit_sink is None:
        return

    event: dict[str, object] = {
        "event": "jarvis_tool_execution",
        "decision": decision,
        "tool": tool,
        "tenant_id": tenant_id,
        "actor_subject": actor_subject,
        "service_assertion_id_sha256": assertion_id_sha256,
        "authorization_fingerprint": authorization_fingerprint,
        "arguments_sha256": arguments_sha256,
        "reason_sha256": reason_sha256,
    }
    if error_type is not None:
        event["error_type"] = error_type

    await audit_sink(event)


async def execute_jarvis_tool(
    *,
    service_assertion: str,
    service_settings: JarvisServiceVerifierSettings,
    replay_guard: RedisJarvisServiceReplayGuard,
    grant_store: RedisAiToolGrantStore,
    grant_token: str,
    principal: PrincipalLike,
    tool: AiToolName,
    arguments: Mapping[str, Any],
    reason: str,
    executors: Mapping[AiToolName, JarvisExecutor],
    audit_sink: JarvisAuditSink | None = None,
    now: float | None = None,
) -> JarvisExecutionResult:
    """Execute one reviewed Jarvis invocation through all security boundaries.

    The service assertion is consumed before tenant/user authorization and the
    invocation grant is consumed before the executor is called. A failed or
    mismatched attempt therefore cannot leave either bearer credential reusable.
    """

    verified = await verify_and_consume_jarvis_service_assertion(
        service_assertion,
        service_settings,
        replay_guard,
        now=now,
    )
    assertion_hash = _assertion_id_sha256(verified)

    capability = derive_ai_tool_capability(
        principal,
        tool=tool,
    )

    arguments_hash = canonical_arguments_sha256(arguments)
    reason_hash = canonical_reason_sha256(reason)

    await grant_store.consume(
        token=grant_token,
        capability=capability,
        arguments=arguments,
        reason=reason,
    )

    executor = executors.get(tool)
    if executor is None:
        await _emit_sanitized_audit(
            audit_sink,
            decision="denied",
            tool=tool,
            tenant_id=str(capability.tenant_id),
            actor_subject=capability.actor_subject,
            assertion_id_sha256=assertion_hash,
            authorization_fingerprint=capability.authorization_fingerprint,
            arguments_sha256=arguments_hash,
            reason_sha256=reason_hash,
            error_type="JarvisExecutorUnavailable",
        )
        raise JarvisExecutorUnavailable("reviewed Jarvis executor is unavailable")

    try:
        result = await executor(arguments)
    except Exception as exc:
        await _emit_sanitized_audit(
            audit_sink,
            decision="error",
            tool=tool,
            tenant_id=str(capability.tenant_id),
            actor_subject=capability.actor_subject,
            assertion_id_sha256=assertion_hash,
            authorization_fingerprint=capability.authorization_fingerprint,
            arguments_sha256=arguments_hash,
            reason_sha256=reason_hash,
            error_type=type(exc).__name__,
        )
        raise

    await _emit_sanitized_audit(
        audit_sink,
        decision="allowed",
        tool=tool,
        tenant_id=str(capability.tenant_id),
        actor_subject=capability.actor_subject,
        assertion_id_sha256=assertion_hash,
        authorization_fingerprint=capability.authorization_fingerprint,
        arguments_sha256=arguments_hash,
        reason_sha256=reason_hash,
    )

    return JarvisExecutionResult(
        tool=tool,
        result=result,
        service_assertion_id_sha256=assertion_hash,
        authorization_fingerprint=capability.authorization_fingerprint,
    )
