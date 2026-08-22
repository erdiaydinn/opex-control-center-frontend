"""Durable Inventory location-completion events on the canonical append-only ledger."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .mission_lease import attest_event_lease, complete_attempt
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

LOCATION_COMPLETE = "LOCATION_COMPLETE"


def location_completion_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_shift_id": str(payload["active_shift_id"]).strip(),
        "attempt_id": str(UUID(str(payload["attempt_id"]))),
        "confirmed_line_count": int(payload["confirmed_line_count"]),
        "device_sequence": int(payload["device_sequence"]),
        "document_id": str(UUID(str(payload["document_id"]))),
        "event_id": str(UUID(str(payload["event_id"]))),
        "event_kind": LOCATION_COMPLETE,
        "lease_id": str(UUID(str(payload["lease_id"]))),
        "location_id": str(payload["location_id"]).strip().upper(),
        "occurred_at": str(payload["occurred_at"]),
    }


def _require_schema_v4(db: Any) -> None:
    row = db.execute(
        "SELECT 1 FROM inventory_schema_migrations WHERE version=4",
    ).fetchone()
    if not row:
        raise RuntimeError("Inventory location-completion migration v4 uygulanmamış.")


def completion_readiness() -> bool:
    try:
        from psycopg import Error as PsycopgError
    except ImportError:
        return False

    try:
        with connect() as db:
            _require_schema_v4(db)
        return True
    except (RuntimeError, PsycopgError):
        return False


def filter_completed_terminal_tasks(
    principal: InventoryPrincipal,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Hide immutable completed locations from the active terminal mission queue."""

    if not rows:
        return []
    document_ids = sorted({UUID(str(row["id"])) for row in rows}, key=str)
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _require_schema_v4(db)
        completed = db.execute(
            """SELECT document_id,location_id
               FROM inventory_events
               WHERE tenant_id=%s
                 AND event_type='LOCATION_COMPLETE'
                 AND document_id=ANY(%s)""",
            (principal.tenant_id, document_ids),
        ).fetchall()
    completed_keys = {
        (str(row["document_id"]), str(row["location_id"]).strip().upper())
        for row in completed
    }
    return [
        row
        for row in rows
        if (str(row["id"]), str(row["location_id"]).strip().upper()) not in completed_keys
    ]


def record_location_completion(
    principal: InventoryPrincipal,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    request_signature: str,
) -> dict[str, Any]:
    """Append one shift/attempt/lease-bound location completion to the canonical ledger."""

    principal.validate()
    event_id = UUID(str(payload["event_id"]))
    document_id = UUID(str(payload["document_id"]))
    attempt_id = UUID(str(payload["attempt_id"]))
    lease_id = UUID(str(payload["lease_id"]))
    active_shift_id = str(payload["active_shift_id"]).strip()
    confirmed_line_count = int(payload["confirmed_line_count"])
    claimed_hash = str(payload["payload_hash"])
    actual_hash = canonical_payload_hash(location_completion_hash_input(payload))
    if claimed_hash != actual_hash:
        raise InventoryRuleError("Location completion payload hash doğrulaması başarısız.")
    _redis_event_preflight(principal.tenant_id, event_id, actual_hash)

    occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        raise InventoryRuleError("Location completion zamanı timezone içermelidir.")
    occurred_at = occurred_at.astimezone(UTC)

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            _assert_runtime_tenant(db, principal)
            _require_schema_v4(db)
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
                    raise InventoryRuleError(
                        "Event ID farklı location completion payload ile yeniden kullanılamaz."
                    )
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
                raise InventoryRuleError("Kilitli veya gönderilmiş sayım lokasyonu tamamlanamaz.")

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
                    "Workforce location-completion vardiya authority kullanılamıyor."
                ) from error
            if shift_attestation is None:
                raise PermissionError(
                    "Location completion aktif vardiya penceresi dışında üretildi."
                )

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
                location_completion=True,
            )

            already_completed = db.execute(
                """SELECT event_id FROM inventory_events
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                     AND event_type='LOCATION_COMPLETE'
                   LIMIT 1""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if already_completed:
                raise InventoryRuleError("Lokasyon daha önce tamamlandı.")

            committed_count_row = db.execute(
                """SELECT count(*)::integer AS committed_line_count
                   FROM inventory_events
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                     AND attempt_id=%s
                     AND event_type IN ('SCAN','UNEXPECTED_SKU','RECOUNT')
                     AND occurred_at<=%s""",
                (
                    principal.tenant_id,
                    document_id,
                    location,
                    attempt_id,
                    occurred_at,
                ),
            ).fetchone()
            committed_line_count = int(committed_count_row["committed_line_count"])
            if committed_line_count != confirmed_line_count:
                raise InventoryRuleError(
                    "Lokasyon completion satır sayısı aynı attempt'in server-committed kanıtıyla eşleşmiyor."
                )

            db.execute(
                """INSERT INTO inventory_events(
                     tenant_id,event_id,device_id,device_sequence,document_id,warehouse_id,
                     employee_id,event_type,location_id,barcode,quantity,symbology,
                     payload_hash,occurred_at,attempt_id,lease_id,active_shift_id
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,'LOCATION_COMPLETE',%s,NULL,NULL,NULL,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id,
                    event_id,
                    principal.device_id,
                    int(payload["device_sequence"]),
                    document_id,
                    document["warehouse_id"],
                    principal.employee_id,
                    location,
                    actual_hash,
                    occurred_at,
                    attempt_id,
                    lease_id,
                    active_shift_id,
                ),
            )
            complete_attempt(
                db,
                principal,
                attempt_id=attempt_id,
                lease_id=lease_id,
                document_id=document_id,
                warehouse_id=document["warehouse_id"],
                occurred_at=occurred_at,
            )
            response = {
                "event_id": str(event_id),
                "accepted": True,
                "event_type": LOCATION_COMPLETE,
                "document_revision": document["revision"],
                "location_id": location,
                "active_shift_id": shift_attestation.shift_id,
                "attempt_id": str(attempt_id),
                "lease_id": str(lease_id),
                "confirmed_line_count": committed_line_count,
                "idempotent_replay": False,
            }
            db.execute(
                "INSERT INTO inventory_event_responses(tenant_id,event_id,response) VALUES(%s,%s,%s::jsonb)",
                (principal.tenant_id, event_id, json.dumps(response, sort_keys=True)),
            )
            _audit(
                db,
                principal,
                "LOCATION_COUNT_COMPLETED",
                document_id,
                document["warehouse_id"],
                response,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_LOCATION_COMPLETED',%s::jsonb)""",
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
