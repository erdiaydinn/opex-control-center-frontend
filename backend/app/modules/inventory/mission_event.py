"""Lease-bound production Inventory terminal count events."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .mission_lease import attest_event_lease
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


def terminal_event_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
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


def record_event(
    principal: InventoryPrincipal,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    request_signature: str,
) -> dict[str, Any]:
    principal.validate()
    event_id = UUID(str(payload["event_id"]))
    document_id = UUID(str(payload["document_id"]))
    attempt_id = UUID(str(payload["attempt_id"]))
    lease_id = UUID(str(payload["lease_id"]))
    active_shift_id = str(payload["active_shift_id"]).strip()
    claimed_hash = str(payload["payload_hash"])
    actual_hash = canonical_payload_hash(terminal_event_hash_input(payload))
    if claimed_hash != actual_hash:
        raise InventoryRuleError("Event payload hash doğrulaması başarısız.")
    _redis_event_preflight(principal.tenant_id, event_id, actual_hash)
    occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        raise InventoryRuleError("Event zamanı timezone içermelidir.")
    occurred_at = occurred_at.astimezone(UTC)

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
                shift_attestation = attest_shift_at_event(
                    principal.tenant_id,
                    principal.employee_id,
                    document["warehouse_id"],
                    active_shift_id,
                    str(payload["occurred_at"]),
                )
            except ActiveShiftAuthorityError as error:
                raise RuntimeError(
                    "Workforce event vardiya authority kullanılamıyor."
                ) from error
            if shift_attestation is None:
                raise PermissionError("Event aktif vardiya penceresi dışında üretildi.")

            location = str(payload["location_id"]).strip().upper()
            allowed = db.execute(
                """SELECT 1 FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if not allowed:
                raise InventoryRuleError("Lokasyon sayım kapsamında değil.")

            attest_event_lease(
                db,
                principal,
                document_id=document_id,
                warehouse_id=document["warehouse_id"],
                location_id=location,
                active_shift_id=active_shift_id,
                attempt_id=attempt_id,
                lease_id=lease_id,
                occurred_at=occurred_at,
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
                "active_shift_id": shift_attestation.shift_id,
                "attempt_id": str(attempt_id),
                "lease_id": str(lease_id),
                "idempotent_replay": False,
            }
            db.execute(
                "INSERT INTO inventory_event_responses(tenant_id,event_id,response) VALUES(%s,%s,%s::jsonb)",
                (principal.tenant_id, event_id, json.dumps(response, sort_keys=True)),
            )
            _audit(
                db,
                principal,
                "TERMINAL_EVENT_ACCEPTED",
                document_id,
                document["warehouse_id"],
                response,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_EVENT_ACCEPTED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    document_id,
                    json.dumps(response, sort_keys=True),
                ),
            )
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
