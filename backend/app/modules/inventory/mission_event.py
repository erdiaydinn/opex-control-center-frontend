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
from .sku_identity import frozen_sku_identity


def terminal_event_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    quantity = Decimal(str(payload["quantity"])).normalize()
    hashed = {
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
    if payload.get("recount_of_event_id") is not None:
        hashed["recount_of_event_id"] = str(UUID(str(payload["recount_of_event_id"])))
        hashed["recount_reason_code"] = str(payload.get("recount_reason_code", "")).strip().upper()
    return hashed


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
            # Idempotency is not an authentication shortcut. Every delivery,
            # including an exact replay, must prove that the device is still
            # ACTIVE and present a fresh signed nonce before any stored
            # response can be disclosed.
            _verify_device_proof(
                db,
                principal,
                actual_hash,
                request_timestamp,
                request_nonce,
                request_signature,
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
            # Serialize the logical count line, not merely the delivery event. This
            # prevents two offline queues from both creating a "first" count.
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(
                    f"count-line:{principal.tenant_id}:{attempt_id}:{location}:{barcode}"
                ),),
            )
            prior = db.execute(
                """SELECT event_id,event_type,count_version
                   FROM inventory_events
                   WHERE tenant_id=%s AND document_id=%s AND attempt_id=%s
                     AND location_id=%s AND barcode=%s
                     AND event_type IN ('SCAN','UNEXPECTED_SKU','RECOUNT')
                   ORDER BY count_version DESC
                   LIMIT 1""",
                (principal.tenant_id, document_id, attempt_id, location, barcode),
            ).fetchone()
            recount_of = payload.get("recount_of_event_id")
            if prior and recount_of is None:
                raise InventoryRuleError(
                    "SKU bu lokasyonda zaten sayıldı; sessiz tekrar yerine açık yeniden sayım başlatılmalıdır."
                )
            if not prior and recount_of is not None:
                raise InventoryRuleError("Yeniden sayım için önceki sayım kanıtı bulunamadı.")
            if prior:
                try:
                    superseded_event_id = UUID(str(recount_of))
                except (TypeError, ValueError):
                    raise InventoryRuleError("Yeniden sayım önceki event kimliğine bağlanmalıdır.")
                if superseded_event_id != prior["event_id"]:
                    raise InventoryRuleError(
                        "Yeniden sayım güncel sayım sürümüne bağlı değil; ekran yenilenmelidir."
                    )
                reason_code = str(payload.get("recount_reason_code", "")).strip().upper()
                if reason_code not in {
                    "OPERATOR_CORRECTION",
                    "SUPERVISOR_REQUEST",
                    "DEVICE_RECOVERY",
                    "VARIANCE_REVIEW",
                }:
                    raise InventoryRuleError("Geçerli bir yeniden sayım neden kodu zorunludur.")
            else:
                superseded_event_id = None
                reason_code = None
            expected = db.execute(
                """SELECT sku FROM inventory_expected_stock
                   WHERE tenant_id=%s AND document_id=%s AND barcode=%s""",
                (principal.tenant_id, document_id, barcode),
            ).fetchone()
            event_type = "RECOUNT" if prior else ("SCAN" if expected else "UNEXPECTED_SKU")
            sku_identity = frozen_sku_identity(document_id, barcode, expected)
            db.execute(
                """INSERT INTO inventory_events(
                     tenant_id,event_id,device_id,device_sequence,document_id,warehouse_id,
                     employee_id,event_type,location_id,barcode,quantity,symbology,
                     payload_hash,occurred_at,attempt_id,lease_id,active_shift_id,
                     count_version,supersedes_event_id,recount_reason_code
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
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
                    int(prior["count_version"]) + 1 if prior else 1,
                    superseded_event_id,
                    reason_code,
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
                "count_version": int(prior["count_version"]) + 1 if prior else 1,
                "supersedes_event_id": str(superseded_event_id) if superseded_event_id else None,
                "recount_reason_code": reason_code,
                # Only the barcode actually presented is projected. Expected
                # quantity, cost, variance and the document SKU universe stay
                # behind the reconciliation authority boundary.
                "sku_identity": sku_identity,
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
