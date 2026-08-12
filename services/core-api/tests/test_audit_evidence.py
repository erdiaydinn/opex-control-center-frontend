from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.core.audit_evidence import (
    AUDIT_CHAIN_GENESIS_HASH,
    AuditEvidenceIntegrityError,
    AuditEvidenceRow,
    recompute_audit_event_hash,
    verify_audit_evidence_row,
    verify_tenant_audit_chain,
)

TENANT_A = UUID("11111111-1111-4111-8111-111111111111")
TENANT_B = UUID("22222222-2222-4222-8222-222222222222")
EVENT_1 = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1")
EVENT_2 = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
CREATED_AT = datetime(2026, 8, 12, 18, 30, 1, 123456, tzinfo=UTC)


def build_row(
    *,
    event_id: UUID,
    sequence: int,
    previous_hash: str,
    tenant_id: UUID = TENANT_A,
    action: str = "ai_tool_execution_authorized",
    resource_id: str | None = None,
) -> AuditEvidenceRow:
    payload = {
        "version": 1,
        "event_id": str(event_id),
        "tenant_id": str(tenant_id),
        "actor_subject": "user-1",
        "action": action,
        "resource_type": "ai_tool_execution",
        "resource_id": resource_id,
        "decision": "allowed",
        "request_id": f"request-{sequence}",
        "data": {"tool": "ops_kpi_query", "safe": True},
        "created_at_utc": "2026-08-12T18:30:01.123456Z",
    }
    event_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    event_hash = recompute_audit_event_hash(
        chain_sequence=sequence,
        previous_event_hash=previous_hash,
        event_payload=event_payload,
    )
    return AuditEvidenceRow(
        id=event_id,
        tenant_id=tenant_id,
        actor_subject="user-1",
        action=action,
        resource_type="ai_tool_execution",
        resource_id=resource_id,
        decision="allowed",
        request_id=f"request-{sequence}",
        data={"tool": "ops_kpi_query", "safe": True},
        created_at=CREATED_AT,
        chain_sequence=sequence,
        previous_event_hash=previous_hash,
        event_hash=event_hash,
        event_payload=event_payload,
    )


def valid_chain() -> list[AuditEvidenceRow]:
    first = build_row(
        event_id=EVENT_1,
        sequence=1,
        previous_hash=AUDIT_CHAIN_GENESIS_HASH,
        resource_id=None,
    )
    second = build_row(
        event_id=EVENT_2,
        sequence=2,
        previous_hash=first.event_hash,
        resource_id="execution-2",
    )
    return [first, second]


def test_valid_chain_returns_latest_hash() -> None:
    rows = valid_chain()
    assert verify_tenant_audit_chain(rows, tenant_id=TENANT_A) == rows[-1].event_hash


def test_nullable_resource_id_is_valid_evidence() -> None:
    first = valid_chain()[0]
    assert first.resource_id is None
    verify_audit_evidence_row(first)


def test_mutating_original_event_column_is_detected() -> None:
    first = valid_chain()[0]
    tampered = first.model_copy(update={"action": "tampered_action"})
    with pytest.raises(AuditEvidenceIntegrityError, match="no longer matches"):
        verify_audit_evidence_row(tampered)


def test_mutating_forensic_payload_is_detected() -> None:
    first = valid_chain()[0]
    payload = json.loads(first.event_payload)
    payload["decision"] = "denied"
    tampered_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    tampered = first.model_copy(update={"event_payload": tampered_payload})
    with pytest.raises(AuditEvidenceIntegrityError):
        verify_audit_evidence_row(tampered)


def test_rehashing_payload_without_matching_columns_is_still_detected() -> None:
    first = valid_chain()[0]
    payload = json.loads(first.event_payload)
    payload["actor_subject"] = "attacker"
    tampered_payload = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    forged_hash = recompute_audit_event_hash(
        chain_sequence=first.chain_sequence,
        previous_event_hash=first.previous_event_hash,
        event_payload=tampered_payload,
    )
    forged = first.model_copy(
        update={"event_payload": tampered_payload, "event_hash": forged_hash}
    )
    with pytest.raises(AuditEvidenceIntegrityError, match="no longer matches"):
        verify_audit_evidence_row(forged)


def test_broken_previous_hash_link_is_detected() -> None:
    rows = valid_chain()
    rows[1] = rows[1].model_copy(update={"previous_event_hash": "f" * 64})
    with pytest.raises(AuditEvidenceIntegrityError, match="previous hash link"):
        verify_tenant_audit_chain(rows)


def test_noncontiguous_sequence_is_detected() -> None:
    rows = valid_chain()
    rows[1] = rows[1].model_copy(update={"chain_sequence": 3})
    with pytest.raises(AuditEvidenceIntegrityError, match="not contiguous"):
        verify_tenant_audit_chain(rows)


def test_cross_tenant_chain_is_detected() -> None:
    rows = valid_chain()
    rows[1] = rows[1].model_copy(update={"tenant_id": TENANT_B})
    with pytest.raises(AuditEvidenceIntegrityError, match="tenant boundary"):
        verify_tenant_audit_chain(rows)


def test_empty_chain_fails_closed() -> None:
    with pytest.raises(AuditEvidenceIntegrityError, match="empty"):
        verify_tenant_audit_chain([])


def test_malformed_payload_fails_closed() -> None:
    first = valid_chain()[0]
    malformed = first.model_copy(update={"event_payload": "not-json"})
    with pytest.raises(AuditEvidenceIntegrityError, match="invalid JSON"):
        verify_audit_evidence_row(malformed)


def test_naive_created_at_is_rejected() -> None:
    first = valid_chain()[0]
    naive = first.model_copy(update={"created_at": CREATED_AT.replace(tzinfo=None)})
    with pytest.raises(AuditEvidenceIntegrityError, match="timezone-aware"):
        verify_audit_evidence_row(naive)
