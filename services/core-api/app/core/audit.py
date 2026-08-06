from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


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
        occurred_at=datetime.now(timezone.utc).isoformat(),
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
