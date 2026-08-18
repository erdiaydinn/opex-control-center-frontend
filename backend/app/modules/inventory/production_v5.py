"""Inventory v5 production mutation adapter with mission-attempt lease authority."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .mission_attempt import verify_event_lease
from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_runtime_tenant,
    _audit,
    _redis_event_preflight,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)
from .service import InventoryRuleError


def terminal_event_hash_input_v5(payload: dict[str, Any]) -> dict[str, Any]:
    quantity = Decimal(str(payload["quantity"])).normalize()
    return {
        "active_shift_id": str(payload["active_shift_id"]).strip(),
        "attempt_id": str(UUID(str(payload["attempt_id"]))),
        "barcode": str(payload["barcode"]).strip(),
        "device_sequence": int(payload["device_sequence"]),
        "document_id": str(UUID(str(payload["document_id"]))),
        "event_id": str(UUID(str(payload["event_id"]))),
        "lease_id": str(UUID(str(payload["lease_id"]))),
        "location_id": str(payload["location_id"]).strip().upper(),
        "occurred_at": str(payload["occurred_at"]),
        "quantity": format(quantity, "f"),
        "symbology": str(payload["symbology"]).strip(),
    }


def record_event_v5(
    principal: InventoryPrincipal,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    request_signature: str,
) -> dict[str, Any]:
    principal.validate()
    event_id = UUID(str(payload["event_id"]))
    document_id = UUID(str(payload["document_id"]))
    active_shift_id = str(payload["active_shift_id"]).strip()
    actual_hash = canonical_payload_hash(terminal_event_hash_input_v5(payload))
    if str(payload["payload_hash"]) != actual_hash:
        raise InventoryRuleError("Event payload hash doğrulaması başarısız.")
    _redis_event_preflight(principal.tenant_id, event_id, actual_hash)
    occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        raise InventoryRuleError("Event zamanı timezone içermelidir.")

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            _assert_runtime_tenant(db, principal)
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"event:{principal.tenant_id}:{event_id}"),),
            )
            existing = db.execute(
                """SELECT e.payload_hash,r.response FROM inventory_events e
                   JOIN inventory_event_responses r USING(tenant_id,event_id)
                   WHERE e.tenant_id=%s AND e.event_id=%s""",
                (principal.tenant_id, event_id),
            ).fetchone()
            if existing:
                if existing["payload_hash"] != actual_hash:
                    raise InventoryRuleError("Event ID farklı payload ile yeniden kullanılamaz.")
                response = dict(existing["response"])
                response["idempotent_replay"] = True
                return response

            _verify_device_proof(
                db,
                principal,
                actual_hash,
                request_timestamp,
                request_nonce,
                request_signature,
            )
            document = db.execute(
                """SELECT warehouse_id,state,revision FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s FOR UPDATE""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document:
                raise InventoryRuleError("Sayım görevi bulunamadı.")
            if document["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Sayım görevi depo kapsamı dışında.")
            if document["state"] != "COUNTING":
                raise InventoryRuleError("Kilitli veya gönderilmiş sayıma event eklenemez.")

            try:
                shift = attest_shift_at_event(
                    principal.tenant_id,
                    principal.employee_id,
                    document["warehouse_id"],
                    active_shift_id,
                    str(payload["occurred_at"]),
                )
            except ActiveShiftAuthorityError as error:
                raise RuntimeError("Workforce event vardiya authority kullanılamıyor.") from error
            if shift is None:
                raise PermissionError("Event aktif vardiya penceresi dışında üretildi.")

            location = str(payload["location_id"]).strip().upper()
            allowed = db.execute(
                """SELECT 1 FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if not allowed:
                raise InventoryRuleError("Lokasyon sayım kapsamında değil.")

            attempt_id, lease_id = verify_event_lease(
                db,
                principal,
                payload,
                document_id,
                location,
                occurred_at,
            )
            barcode = str(payload["barcode"]).strip()
            expected = db.execute(
                """SELECT sku FROM inventory_expected_stock
                   WHERE tenant_id=%s AND document_id=%s AND barcode=%s""",
                (principal.tenant_id, document_id, barcode),
            ).fetchone()
            event_type = "SCAN" if expected else "UNEXPECTED_SKU"
            db.execute(
                """INSERT INTO inventory_events(
                     tenant_id,event_id,device_id,device_sequence,document_id,warehouse_id,
                     employee_id,event_type,location_id,barcode,quantity,symbology,
                     payload_hash,occurred_at,attempt_id,lease_id,active_shift_id
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id,
                    event_id,
                    principal.device_id,
                    int(payload["device_sequence"]),
                    document_id,
                    document["warehouse_id"],
                    principal.employee_id,
                    event_type,
                    location,
                    barcode,
                    payload["quantity"],
                    payload["symbology"],
                    actual_hash,
                    occurred_at,
                    attempt_id,
                    lease_id,
                    active_shift_id,
                ),
            )
            response = {
                "event_id": str(event_id),
                "accepted": True,
                "event_type": event_type,
                "document_revision": document["revision"],
                "active_shift_id": shift.shift_id,
                "attempt_id": str(attempt_id),
                "lease_id": str(lease_id),
                "idempotent_replay": False,
            }
            db.execute(
                "INSERT INTO inventory_event_responses(tenant_id,event_id,response) VALUES(%s,%s,%s::jsonb)",
                (principal.tenant_id, event_id, json.dumps(response, sort_keys=True)),
            )
            _audit(db, principal, "TERMINAL_EVENT_ACCEPTED", document_id, document["warehouse_id"], response)
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_EVENT_ACCEPTED',%s::jsonb)""",
                (principal.tenant_id, uuid4(), document_id, json.dumps(response, sort_keys=True)),
            )
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise


def _assert_all_locations_completed_v5(db: Any, tenant_id: str, document_id: UUID) -> None:
    status = db.execute(
        """SELECT
             (SELECT count(*)::integer FROM inventory_document_locations
               WHERE tenant_id=%s AND document_id=%s) AS required_location_count,
             (SELECT count(DISTINCT location_id)::integer FROM inventory_mission_attempts
               WHERE tenant_id=%s AND document_id=%s AND status='COMPLETED') AS completed_location_count""",
        (tenant_id, document_id, tenant_id, document_id),
    ).fetchone()
    if not status:
        raise InventoryRuleError("Sayım lokasyon completion authority okunamadı.")
    required = int(status["required_location_count"])
    completed = int(status["completed_location_count"])
    if required <= 0:
        raise InventoryRuleError("Lokasyonsuz sayım gönderilemez.")
    if completed != required:
        raise InventoryRuleError("Tüm lokasyonların completed mission attempt kanıtı olmadan sayım gönderilemez.")


def transition_v5(
    principal: InventoryPrincipal,
    document_id: UUID,
    expected_revision: int,
    target_state: str,
    reason: str,
) -> dict[str, Any]:
    principal.validate()
    allowed = {
        ("COUNTING", "SUBMITTED"),
        ("SUBMITTED", "RECONCILING"),
        ("RECONCILING", "APPROVED"),
        ("APPROVED", "LOCKED"),
        ("SUBMITTED", "REJECTED"),
    }
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            row = db.execute(
                "SELECT * FROM inventory_documents WHERE tenant_id=%s AND id=%s FOR UPDATE",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not row or row["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Sayım bulunamadı veya depo kapsamı dışında.")
            if row["revision"] != expected_revision:
                raise InventoryRuleError("Sayım başka bir yönetici tarafından değiştirildi; ekranı yenileyin.")
            if (row["state"], target_state) not in allowed:
                raise InventoryRuleError("Geçersiz sayım durum geçişi.")
            if row["state"] == "COUNTING" and target_state == "SUBMITTED":
                _assert_all_locations_completed_v5(db, principal.tenant_id, document_id)
            if target_state in {"APPROVED", "LOCKED"} and row["submitted_by"] == principal.subject:
                raise InventoryRuleError("Sayımı gönderen kişi aynı sayımı onaylayamaz veya kilitleyemez.")
            next_revision = expected_revision + 1
            assignments = {
                "SUBMITTED": "submitted_by=%s",
                "APPROVED": "approved_by=%s",
                "LOCKED": "locked_by=%s",
            }
            actor_assignment = assignments.get(target_state)
            sql = "UPDATE inventory_documents SET state=%s,revision=%s,updated_at=now()"
            params: list[Any] = [target_state, next_revision]
            if actor_assignment:
                sql += f",{actor_assignment}"
                params.append(principal.subject)
            sql += " WHERE tenant_id=%s AND id=%s"
            params.extend([principal.tenant_id, document_id])
            db.execute(sql, params)
            snapshot = canonical_payload_hash({
                "document_id": str(document_id),
                "from": row["state"],
                "to": target_state,
                "revision": next_revision,
                "reason": reason,
            })
            db.execute(
                """INSERT INTO inventory_revisions(
                     tenant_id,document_id,revision,state,actor_subject,employee_id,reason,snapshot_hash
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id,
                    document_id,
                    next_revision,
                    target_state,
                    principal.subject,
                    principal.employee_id,
                    reason,
                    snapshot,
                ),
            )
            _audit(db, principal, "DOCUMENT_STATE_CHANGED", document_id, row["warehouse_id"], {
                "from": row["state"], "to": target_state, "revision": next_revision, "reason": reason,
            })
            db.commit()
            return {"document_id": str(document_id), "state": target_state, "revision": next_revision}
        except Exception:
            db.rollback()
            raise
