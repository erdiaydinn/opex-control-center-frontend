import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class AuditEvent:
    occurred_at: str
    request_id: str
    actor: str | None
    tenant_id: str | None
    method: str
    path: str
    status_code: int
    action: str
    metadata: dict[str, Any]


def build_audit_event(
    *,
    request_id: str,
    actor: str | None,
    tenant_id: str | None,
    method: str,
    path: str,
    status_code: int,
    action: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event = AuditEvent(
        occurred_at=datetime.now(UTC).isoformat(),
        request_id=request_id,
        actor=actor,
        tenant_id=tenant_id,
        method=method,
        path=path,
        status_code=status_code,
        action=action,
        metadata=metadata or {},
    )

    return asdict(event)


async def write_transactional_audit_event(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    actor_subject: str,
    request_id: str,
    action: str,
    resource_type: str,
    resource_id: str | None,
    decision: str = "allowed",
    data: dict[str, object] | None = None,
) -> None:
    """Write one canonical platform audit event in an existing DB transaction.

    Product modules may call this shared Core helper when a sensitive domain
    mutation and its platform audit record must commit atomically. The module
    supplies only values already bound to the verified Principal/request; it
    does not own the audit sink schema or SQL.
    """
    await session.execute(
        text(
            """
            INSERT INTO audit_events (
                tenant_id, actor_subject, action, resource_type,
                resource_id, decision, request_id, data
            ) VALUES (
                :tenant_id, :actor_subject, :action, :resource_type,
                :resource_id, :decision, :request_id, CAST(:data AS jsonb)
            )
            """
        ),
        {
            "tenant_id": tenant_id,
            "actor_subject": actor_subject,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "decision": decision,
            "request_id": request_id,
            "data": json.dumps(data or {}, separators=(",", ":"), sort_keys=True),
        },
    )
