"""Governed recovery for quarantined Inventory terminal evidence.

Recovery metadata is recorded in the existing hash-chained Inventory audit/outbox
rather than introducing a competing mutable truth store. A terminal can request
review of one immutable event identity, but it cannot retry, delete, rebind or
promote that event. Supervisor dispositions are maker-checker and stock-neutral;
mission reassignment remains the existing server-owned authority path.

Every state-changing recovery command is bound to the same managed-device
request-proof contract as mission/count mutations: canonical request hash + fresh
timestamp + nonce + hardware-backed P-256 signature. OIDC alone is not sufficient
for a production recovery mutation.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_active_device,
    _assert_runtime_tenant,
    _audit,
    _verify_device_proof,
    connect,
)
from .service import InventoryRuleError

# This set must remain identical to RecoveryCaseCreate and the Android recovery
# client. Policy/identity/device/contract-integrity failures never enter the
# operational supervisor recovery lane.
RECOVERABLE_REASONS = frozenset(
    {
        "BUSINESS_CONFLICT",
        "DEPENDENCY_BLOCKED",
        "RETRY_EXHAUSTED",
    }
)
RECOVERY_DECISIONS = frozenset(
    {
        "RECOUNT_REQUIRED",
        "SERVER_EVIDENCE_CONFIRMED",
        "LOCAL_EVIDENCE_INVALID",
        "SECURITY_ESCALATED",
    }
)


def _uuid(value: str | UUID, label: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as error:
        raise InventoryRuleError(f"{label} UUID geçersiz.") from error


def _sha256_json(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def recovery_request_hash(payload: dict[str, Any]) -> str:
    """Canonical device-proof hash for opening a recovery case."""

    normalized = {
        "document_id": str(_uuid(payload["document_id"], "Document")),
        "event_id": str(_uuid(payload["event_id"], "Event")),
        "location_id": str(payload["location_id"]).strip().upper(),
        "payload_hash": str(payload["payload_hash"]).strip().lower(),
        "quarantine_reason": str(payload["quarantine_reason"]).strip().upper(),
        "server_code": str(payload.get("server_code") or "").strip() or None,
    }
    return _sha256_json(normalized)


def recovery_disposition_hash(
    case_id: str | UUID,
    decision: str,
    reason: str,
) -> str:
    """Canonical device-proof hash for a supervisor disposition."""

    normalized = {
        "case_id": str(_uuid(case_id, "Recovery case")),
        "decision": str(decision).strip().upper(),
        "reason": str(reason).strip(),
    }
    return _sha256_json(normalized)


def _request_record(db: Any, tenant_id: str, case_id: UUID) -> dict[str, Any] | None:
    row = db.execute(
        """SELECT employee_id,record
           FROM inventory_audit
           WHERE tenant_id=%s
             AND action='INVENTORY_RECOVERY_REQUESTED'
             AND record->>'case_id'=%s
           ORDER BY sequence DESC
           LIMIT 1""",
        (tenant_id, str(case_id)),
    ).fetchone()
    if not row:
        return None
    return {"employee_id": str(row["employee_id"]), "record": dict(row["record"])}


def request_recovery_case(
    principal: InventoryPrincipal,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    device_signature: str,
) -> dict[str, Any]:
    """Open one idempotent review case without uploading protected event payload."""

    principal.validate()
    event_id = _uuid(payload["event_id"], "Event")
    document_id = _uuid(payload["document_id"], "Document")
    location_id = str(payload["location_id"]).strip().upper()
    payload_hash = str(payload["payload_hash"]).strip().lower()
    quarantine_reason = str(payload["quarantine_reason"]).strip().upper()
    server_code = str(payload.get("server_code") or "").strip() or None
    if quarantine_reason not in RECOVERABLE_REASONS:
        raise InventoryRuleError("Bu quarantine nedeni terminal supervisor recovery akışına uygun değil.")
    if len(payload_hash) != 64 or any(ch not in "0123456789abcdef" for ch in payload_hash):
        raise InventoryRuleError("Recovery payload hash SHA-256 olmalıdır.")
    if not location_id:
        raise InventoryRuleError("Recovery lokasyonu zorunludur.")
    command_hash = recovery_request_hash(payload)

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            _assert_active_device(db, principal)
            _verify_device_proof(
                db,
                principal,
                command_hash,
                request_timestamp,
                request_nonce,
                device_signature,
            )
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"recovery:{principal.tenant_id}:{event_id}:{payload_hash}"),),
            )

            existing = db.execute(
                """SELECT record
                   FROM inventory_audit
                   WHERE tenant_id=%s
                     AND action='INVENTORY_RECOVERY_REQUESTED'
                     AND record->>'event_id'=%s
                     AND record->>'payload_hash'=%s
                   ORDER BY sequence DESC
                   LIMIT 1""",
                (principal.tenant_id, str(event_id), payload_hash),
            ).fetchone()
            if existing:
                record = dict(existing["record"])
                db.commit()
                return {**record, "idempotent": True}

            document = db.execute(
                """SELECT warehouse_id,state
                   FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document:
                raise InventoryRuleError("Recovery sayım dokümanı bulunamadı.")
            warehouse_id = str(document["warehouse_id"])
            if warehouse_id not in principal.warehouse_scope:
                raise PermissionError("Recovery sayım dokümanı depo kapsamı dışında.")
            location = db.execute(
                """SELECT 1 FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s""",
                (principal.tenant_id, document_id, location_id),
            ).fetchone()
            if not location:
                raise InventoryRuleError("Recovery lokasyonu sayım kapsamında değil.")

            committed = db.execute(
                """SELECT payload_hash,device_id,employee_id
                   FROM inventory_events
                   WHERE tenant_id=%s AND event_id=%s""",
                (principal.tenant_id, event_id),
            ).fetchone()
            authoritative_match = False
            if committed:
                if str(committed["payload_hash"]) != payload_hash:
                    raise InventoryRuleError(
                        "Aynı event ID authoritative Inventory'de farklı payload hash ile mevcut."
                    )
                if UUID(str(committed["device_id"])) != principal.device_id:
                    raise PermissionError("Başka managed device event'i için terminal recovery açılamaz.")
                if str(committed["employee_id"]) != principal.employee_id:
                    raise PermissionError("Başka Employee ID event'i için terminal recovery açılamaz.")
                authoritative_match = True

            case_id = uuid4()
            record = {
                "case_id": str(case_id),
                "event_id": str(event_id),
                "document_id": str(document_id),
                "location_id": location_id,
                "payload_hash": payload_hash,
                "quarantine_reason": quarantine_reason,
                "server_code": server_code,
                "source_device_id": str(principal.device_id),
                "source_employee_id": principal.employee_id,
                "authoritative_event_match": authoritative_match,
                "command_hash": command_hash,
                "evidence_policy": "PRESERVE_NO_CLIENT_PROMOTION",
            }
            _audit(
                db,
                principal,
                "INVENTORY_RECOVERY_REQUESTED",
                document_id,
                warehouse_id,
                record,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_RECOVERY_REQUESTED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    document_id,
                    json.dumps(record, sort_keys=True),
                ),
            )
            db.commit()
            return {**record, "idempotent": False}
        except Exception:
            db.rollback()
            raise


def list_open_recovery_cases(principal: InventoryPrincipal) -> list[dict[str, Any]]:
    """List unresolved cases in the caller's current warehouse scope."""

    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _assert_active_device(db, principal)
        rows = db.execute(
            """SELECT req.record,req.occurred_at
               FROM inventory_audit req
               WHERE req.tenant_id=%s
                 AND req.action='INVENTORY_RECOVERY_REQUESTED'
                 AND req.warehouse_id=ANY(%s)
                 AND NOT EXISTS (
                   SELECT 1 FROM inventory_audit decision
                   WHERE decision.tenant_id=req.tenant_id
                     AND decision.action='INVENTORY_RECOVERY_DISPOSITIONED'
                     AND decision.record->>'case_id'=req.record->>'case_id'
                 )
               ORDER BY req.occurred_at ASC""",
            (principal.tenant_id, sorted(principal.warehouse_scope)),
        ).fetchall()
    return [
        {**dict(row["record"]), "requested_at": row["occurred_at"].isoformat()}
        for row in rows
    ]


def disposition_recovery_case(
    principal: InventoryPrincipal,
    case_id: str | UUID,
    decision: str,
    reason: str,
    request_timestamp: str,
    request_nonce: str,
    device_signature: str,
) -> dict[str, Any]:
    """Append a signed maker-checker disposition; never mutate quarantined evidence."""

    principal.validate()
    parsed_case_id = _uuid(case_id, "Recovery case")
    decision = str(decision).strip().upper()
    reason = str(reason).strip()
    if decision not in RECOVERY_DECISIONS:
        raise InventoryRuleError("Recovery disposition kararı geçersiz.")
    if len(reason) < 3:
        raise InventoryRuleError("Recovery disposition nedeni zorunludur.")
    command_hash = recovery_disposition_hash(parsed_case_id, decision, reason)

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            _assert_active_device(db, principal)
            _verify_device_proof(
                db,
                principal,
                command_hash,
                request_timestamp,
                request_nonce,
                device_signature,
            )
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"recovery-case:{principal.tenant_id}:{parsed_case_id}"),),
            )
            request = _request_record(db, principal.tenant_id, parsed_case_id)
            if not request:
                raise InventoryRuleError("Recovery case bulunamadı.")
            source = request["record"]
            if request["employee_id"] == principal.employee_id:
                raise PermissionError("Recovery talebini açan Employee ID kendi kanıtına karar veremez.")

            document_id = _uuid(source["document_id"], "Document")
            document = db.execute(
                """SELECT warehouse_id FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document or str(document["warehouse_id"]) not in principal.warehouse_scope:
                raise PermissionError("Recovery case depo kapsamı dışında.")
            warehouse_id = str(document["warehouse_id"])

            existing = db.execute(
                """SELECT record FROM inventory_audit
                   WHERE tenant_id=%s
                     AND action='INVENTORY_RECOVERY_DISPOSITIONED'
                     AND record->>'case_id'=%s
                   ORDER BY sequence DESC LIMIT 1""",
                (principal.tenant_id, str(parsed_case_id)),
            ).fetchone()
            if existing:
                previous = dict(existing["record"])
                if previous.get("decision") == decision and previous.get("reason") == reason:
                    db.commit()
                    return {**previous, "idempotent": True}
                raise InventoryRuleError("Recovery case daha önce farklı bir kararla kapatılmış.")

            authoritative_match = False
            if decision == "SERVER_EVIDENCE_CONFIRMED":
                row = db.execute(
                    """SELECT 1 FROM inventory_events
                       WHERE tenant_id=%s AND event_id=%s AND payload_hash=%s
                         AND document_id=%s AND location_id=%s""",
                    (
                        principal.tenant_id,
                        _uuid(source["event_id"], "Event"),
                        source["payload_hash"],
                        document_id,
                        str(source["location_id"]).strip().upper(),
                    ),
                ).fetchone()
                if not row:
                    raise InventoryRuleError(
                        "Authoritative event + payload hash doğrulanmadan kanıt onaylanamaz."
                    )
                authoritative_match = True

            next_action = {
                "RECOUNT_REQUIRED": "SUPERVISOR_MISSION_REASSIGN",
                "SERVER_EVIDENCE_CONFIRMED": "TERMINAL_RECONCILE_ACK_ONLY",
                "LOCAL_EVIDENCE_INVALID": "SUPERVISOR_MISSION_REASSIGN",
                "SECURITY_ESCALATED": "SECURITY_REVIEW_NO_REASSIGN",
            }[decision]
            record = {
                "case_id": str(parsed_case_id),
                "event_id": source["event_id"],
                "document_id": source["document_id"],
                "location_id": source["location_id"],
                "payload_hash": source["payload_hash"],
                "decision": decision,
                "reason": reason,
                "authoritative_event_match": authoritative_match,
                "reviewer_employee_id": principal.employee_id,
                "command_hash": command_hash,
                "next_action": next_action,
                "evidence_policy": "PRESERVE_NO_CLIENT_PROMOTION",
            }
            _audit(
                db,
                principal,
                "INVENTORY_RECOVERY_DISPOSITIONED",
                document_id,
                warehouse_id,
                record,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_RECOVERY_DISPOSITIONED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    document_id,
                    json.dumps(record, sort_keys=True),
                ),
            )
            db.commit()
            return {**record, "idempotent": False}
        except Exception:
            db.rollback()
            raise
