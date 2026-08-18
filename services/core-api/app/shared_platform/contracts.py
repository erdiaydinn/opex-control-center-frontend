from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class NotificationIntent:
    module: str
    event_key: str
    recipient_subject: str
    channel: str
    idempotency_key: str
    payload: Mapping[str, object]


@dataclass(frozen=True)
class SearchDocument:
    source_module: str
    source_type: str
    source_id: str
    title: str
    search_text: str
    permission_key: str
    provenance: Mapping[str, object]


@dataclass(frozen=True)
class IntegrationContract:
    connector_key: str
    direction: str
    version: int
    schema: Mapping[str, object]
    validation_policy: Mapping[str, object]


def validate_authority_boundary(
    *,
    tenant_from_session: str,
    tenant_from_payload: str | None = None,
) -> str:
    """Tenant authority is always server/session derived, never payload authored."""

    if tenant_from_payload not in (None, ""):
        raise ValueError("payload tenant authority is forbidden")
    if not tenant_from_session:
        raise ValueError("server tenant authority is required")
    return tenant_from_session
