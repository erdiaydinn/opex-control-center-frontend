"""Independent verifier for PostgreSQL audit hash-chain evidence.

This module never mutates audit state. It recomputes SHA-256 in Python and
also compares the server-captured forensic payload snapshot with the current
audit columns. It is intended to feed later signed external checkpoints.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

AUDIT_CHAIN_DOMAIN = "eay-audit-chain-v1"
AUDIT_CHAIN_GENESIS_HASH = "0" * 64
SHA256_HEX = re.compile(r"^[0-9a-f]{64}$")


class AuditEvidenceError(ValueError):
    """Base fail-closed audit-evidence verification failure."""


class AuditEvidenceIntegrityError(AuditEvidenceError):
    """The audit chain or forensic snapshot is inconsistent."""


class AuditEvidenceRow(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: UUID
    tenant_id: UUID
    actor_subject: str = Field(min_length=1)
    action: str = Field(min_length=1)
    resource_type: str = Field(min_length=1)
    resource_id: str | None = None
    decision: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    data: dict[str, Any]
    created_at: datetime
    chain_sequence: int = Field(ge=1)
    previous_event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    event_payload: str = Field(min_length=2)


def recompute_audit_event_hash(
    *,
    chain_sequence: int,
    previous_event_hash: str,
    event_payload: str,
) -> str:
    if isinstance(chain_sequence, bool) or not isinstance(chain_sequence, int):
        raise AuditEvidenceIntegrityError("Audit chain sequence is invalid")
    if chain_sequence < 1:
        raise AuditEvidenceIntegrityError("Audit chain sequence is invalid")
    if not isinstance(previous_event_hash, str) or not SHA256_HEX.fullmatch(
        previous_event_hash
    ):
        raise AuditEvidenceIntegrityError("Audit previous hash is invalid")
    if not isinstance(event_payload, str) or not event_payload:
        raise AuditEvidenceIntegrityError("Audit event payload is invalid")

    material = (
        f"{AUDIT_CHAIN_DOMAIN}|{chain_sequence}|"
        f"{previous_event_hash}|{event_payload}"
    ).encode("utf-8")
    return hashlib.sha256(material).hexdigest()


def _created_at_utc(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise AuditEvidenceIntegrityError("Audit created_at must be timezone-aware")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _expected_payload(row: AuditEvidenceRow) -> dict[str, Any]:
    return {
        "version": 1,
        "event_id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "actor_subject": row.actor_subject,
        "action": row.action,
        "resource_type": row.resource_type,
        "resource_id": row.resource_id,
        "decision": row.decision,
        "request_id": row.request_id,
        "data": row.data,
        "created_at_utc": _created_at_utc(row.created_at),
    }


def verify_audit_evidence_row(row: AuditEvidenceRow) -> None:
    try:
        parsed_payload = json.loads(row.event_payload)
    except (TypeError, json.JSONDecodeError) as exc:
        raise AuditEvidenceIntegrityError("Audit forensic payload is invalid JSON") from exc

    if not isinstance(parsed_payload, dict):
        raise AuditEvidenceIntegrityError("Audit forensic payload must be an object")
    if parsed_payload != _expected_payload(row):
        raise AuditEvidenceIntegrityError(
            "Audit forensic payload no longer matches event columns"
        )

    expected_hash = recompute_audit_event_hash(
        chain_sequence=row.chain_sequence,
        previous_event_hash=row.previous_event_hash,
        event_payload=row.event_payload,
    )
    if row.event_hash != expected_hash:
        raise AuditEvidenceIntegrityError("Audit event hash mismatch")


def verify_tenant_audit_chain(
    rows: Sequence[AuditEvidenceRow | Mapping[str, Any]],
    *,
    tenant_id: UUID | None = None,
) -> str:
    if not rows:
        raise AuditEvidenceIntegrityError("Audit chain is empty")

    verified_tenant = tenant_id
    previous_hash = AUDIT_CHAIN_GENESIS_HASH

    for expected_sequence, raw_row in enumerate(rows, start=1):
        row = (
            raw_row
            if isinstance(raw_row, AuditEvidenceRow)
            else AuditEvidenceRow.model_validate(raw_row)
        )

        if verified_tenant is None:
            verified_tenant = row.tenant_id
        if row.tenant_id != verified_tenant:
            raise AuditEvidenceIntegrityError("Audit chain crosses tenant boundary")
        if row.chain_sequence != expected_sequence:
            raise AuditEvidenceIntegrityError("Audit chain sequence is not contiguous")
        if row.previous_event_hash != previous_hash:
            raise AuditEvidenceIntegrityError("Audit previous hash link is broken")

        verify_audit_evidence_row(row)
        previous_hash = row.event_hash

    return previous_hash
