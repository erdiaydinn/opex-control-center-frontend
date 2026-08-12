"""Fail-closed binding between tenant query authority and Jarvis execution scope."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.core.ai_tenant_query_context import AiTenantQueryContextRecord

SHA256_LENGTH = 64


class AiQueryContextBindingError(PermissionError):
    """Tenant query context cannot be safely bound to execution."""


@dataclass(frozen=True)
class AiQueryContextBinding:
    version: int
    tenant_id: str
    context_record_fingerprint: str
    entity_ids: tuple[str, ...]
    execution_context_fingerprint: str


def _require_sha256(value: str, *, field: str) -> None:
    if len(value) != SHA256_LENGTH:
        raise AiQueryContextBindingError(f"{field} is not SHA-256")
    try:
        bytes.fromhex(value)
    except ValueError as exc:
        raise AiQueryContextBindingError(f"{field} is not SHA-256") from exc


def bind_query_context_to_execution(
    *,
    tenant_id: str,
    query_context: AiTenantQueryContextRecord | None,
    execution_scope_fingerprint: str,
) -> AiQueryContextBinding:
    """Bind authoritative tenant discriminator context to a reviewed execution scope.

    Missing context is intentionally a denial: no implicit/default entity identity exists.
    Raw source provenance is excluded from the execution fingerprint; its canonical record
    fingerprint already commits to the validated context including source_reference.
    """
    if query_context is None:
        raise AiQueryContextBindingError("Tenant query context is not configured")
    if query_context.tenant_id != tenant_id:
        raise AiQueryContextBindingError("Tenant query context does not match principal")
    _require_sha256(execution_scope_fingerprint, field="execution_scope_fingerprint")
    _require_sha256(query_context.record_fingerprint, field="context_record_fingerprint")

    payload = {
        "version": 1,
        "tenant_id": tenant_id,
        "context_record_fingerprint": query_context.record_fingerprint,
        "execution_scope_fingerprint": execution_scope_fingerprint,
    }
    fingerprint = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return AiQueryContextBinding(
        version=1,
        tenant_id=tenant_id,
        context_record_fingerprint=query_context.record_fingerprint,
        entity_ids=query_context.context.entity_ids,
        execution_context_fingerprint=fingerprint,
    )
