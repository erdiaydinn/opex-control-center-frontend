"""Server-owned Inventory mission attempt and historical lease authority."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from os import getenv
from typing import Any
from uuid import UUID, uuid4

from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_runtime_tenant,
    _audit,
    _terminal_mission_id,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)
from .service import InventoryRuleError

LEASE_SECONDS_MIN = 120
LEASE_SECONDS_MAX = 3600
LEASE_SECONDS_DEFAULT = 900


def _lease_seconds() -> int:
    raw = getenv("EAY_INVENTORY_MISSION_LEASE_SECONDS", str(LEASE_SECONDS_DEFAULT)).strip()
    try:
        value = int(raw)
    except ValueError as error:
        raise RuntimeError("EAY_INVENTORY_MISSION_LEASE_SECONDS tam sayı olmalıdır.") from error
    if value < LEASE_SECONDS_MIN or value > LEASE_SECONDS_MAX:
        raise RuntimeError(
            f"Inventory mission lease süresi {LEASE_SECONDS_MIN}-{LEASE_SECONDS_MAX} saniye olmalıdır."
        )
    return value


def mission_claim_hash_input(document_id: str | UUID, location_id: str) -> dict[str, str]:
    return {
        "document_id": str(UUID(str(document_id))),
        "location_id": str(location_id).strip().upper(),
    }


def _require_schema_v5(db: Any) -> None:
    row = db.execute(
        "SELECT 1 FROM inventory_schema_migrations WHERE version=5",
    ).fetchone()
    if not row:
        raise RuntimeError("Inventory mission-attempt/lease migration v5 uygulanmamış.")


def lease_readiness() -> bool:
    try:
        from psycopg import Error as PsycopgError
    except ImportError:
        return False
    try:
        with connect() as db:
            _require_schema_v5(db)
        return True
    except (RuntimeError, PsycopgError):
        return False


def filter_and_annotate_terminal_tasks(
    principal: InventoryPrincipal,
    active_shift_id: str,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return only free or currently-owned terminal missions.

    Merely listing tasks never creates authority. A task with another principal's
    live lease is hidden. An expired attempt last owned by another principal is
    also hidden until a governed supervisor reassignment creates a new attempt.
    """

    principal.validate()
    if not rows:
        return []
    shift_id = str(active_shift_id).strip()
    if not shift_id:
        raise InventoryRuleError("Aktif vardiya kimliği mission listesi için zorunludur.")

    document_ids = sorted({UUID(str(row["id"])) for row in rows}, key=str)
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _require_schema_v5(db)
        attempts = db.execute(
            """SELECT a.document_id,a.location_id,a.attempt_id,
                      live.lease_id AS live_lease_id,
                      live.employee_id AS live_employee_id,
                      live.device_id AS live_device_id,
                      live.shift_id AS live_shift_id,
                      live.valid_until AS live_valid_until,
                      last_lease.employee_id AS last_employee_id,
                      last_lease.device_id AS last_device_id,
                      last_lease.shift_id AS last_shift_id
               FROM inventory_mission_attempts a
               LEFT JOIN LATERAL (
                 SELECT l.lease_id,l.employee_id,l.device_id,l.shift_id,l.valid_until
                 FROM inventory_mission_leases l
                 LEFT JOIN inventory_mission_lease_closures c
                   ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
                 WHERE l.tenant_id=a.tenant_id AND l.attempt_id=a.attempt_id
                   AND c.lease_id IS NULL AND l.valid_until>now()
                 ORDER BY l.valid_from DESC
                 LIMIT 1
               ) live ON TRUE
               LEFT JOIN LATERAL (
                 SELECT l.employee_id,l.device_id,l.shift_id
                 FROM inventory_mission_leases l
                 WHERE l.tenant_id=a.tenant_id AND l.attempt_id=a.attempt_id
                 ORDER BY l.valid_from DESC
                 LIMIT 1
               ) last_lease ON TRUE
               WHERE a.tenant_id=%s AND a.state='ACTIVE' AND a.document_id=ANY(%s)""",
            (principal.tenant_id, document_ids),
        ).fetchall()

    by_location = {
        (str(row["document_id"]), str(row["location_id"]).strip().upper()): row
        for row in attempts
    }
    visible: list[dict[str, Any]] = []
    for source in rows:
        row = dict(source)
        key = (str(row["id"]), str(row["location_id"]).strip().upper())
        attempt = by_location.get(key)
        if attempt is None:
            row.update(
                claim_status="AVAILABLE",
                attempt_id=None,
                lease_id=None,
                lease_valid_until=None,
            )
            visible.append(row)
            continue

        live_lease_id = attempt["live_lease_id"]
        if live_lease_id is not None:
            owned = (
                str(attempt["live_employee_id"]) == principal.employee_id
                and UUID(str(attempt["live_device_id"])) == principal.device_id
                and str(attempt["live_shift_id"]) == shift_id
            )
            if not owned:
                continue
            row.update(
                claim_status="OWNED",
                attempt_id=str(attempt["attempt_id"]),
                lease_id=str(live_lease_id),
                lease_valid_until=attempt["live_valid_until"].astimezone(UTC).isoformat(),
            )
            visible.append(row)
            continue

        last_employee = attempt["last_employee_id"]
        if last_employee is not None:
            same_previous_owner = (
                str(last_employee) == principal.employee_id
                and UUID(str(attempt["last_device_id"])) == principal.device_id
                and str(attempt["last_shift_id"]) == shift_id
            )
            if not same_previous_owner:
                continue

        row.update(
            claim_status="AVAILABLE",
            attempt_id=str(attempt["attempt_id"]),
            lease_id=None,
            lease_valid_until=None,
        )
        visible.append(row)
    return visible


def _claim_response(
    *,
    principal: InventoryPrincipal,
    document_id: UUID,
    location_id: str,
    shift_id: str,
    attempt_id: UUID,
    lease_id: UUID,
    valid_from: datetime,
    valid_until: datetime,
    idempotent: bool,
) -> dict[str, Any]:
    return {
        "mission_id": _terminal_mission_id(principal.tenant_id, document_id, location_id),
        "document_id": str(document_id),
        "location_id": location_id,
        "attempt_id": str(attempt_id),
        "lease_id": str(lease_id),
        "active_shift_id": shift_id,
        "lease_valid_from": valid_from.astimezone(UTC).isoformat(),
        "lease_valid_until": valid_until.astimezone(UTC).isoformat(),
        "claim_status": "OWNED",
        "idempotent": idempotent,
    }


def claim_terminal_mission(
    principal: InventoryPrincipal,
    active_shift_id: str,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    request_signature: str,
) -> dict[str, Any]:
    """Transactionally claim or renew one location mission for this principal/device."""

    principal.validate()
    document_id = UUID(str(payload["document_id"]))
    location = str(payload["location_id"]).strip().upper()
    shift_id = str(active_shift_id).strip()
    if not location or not shift_id:
        raise InventoryRuleError("Document, lokasyon ve aktif vardiya mission claim için zorunludur.")

    actual_hash = canonical_payload_hash(mission_claim_hash_input(document_id, location))
    if str(payload["payload_hash"]) != actual_hash:
        raise InventoryRuleError("Mission claim payload hash doğrulaması başarısız.")

    now = datetime.now(UTC)
    valid_until = now + timedelta(seconds=_lease_seconds())
    with connect() as db:
        try:
            # The cross-session advisory lock is the serialization primitive for
            # this exact physical mission. READ COMMITTED ensures a waiter sees
            # the winner's committed attempt/lease after the lock is acquired.
            db.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            _assert_runtime_tenant(db, principal)
            _require_schema_v5(db)
            _verify_device_proof(
                db,
                principal,
                actual_hash,
                request_timestamp,
                request_nonce,
                request_signature,
            )
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"mission:{principal.tenant_id}:{document_id}:{location}"),),
            )
            document = db.execute(
                """SELECT warehouse_id,state,revision
                   FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s FOR UPDATE""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document:
                raise InventoryRuleError("Sayım görevi bulunamadı.")
            if document["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Sayım görevi depo kapsamı dışında.")
            if document["state"] != "COUNTING":
                raise InventoryRuleError("Yalnız COUNTING durumundaki sayım görevi claim edilebilir.")
            location_row = db.execute(
                """SELECT completed_event_id
                   FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                   FOR UPDATE""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if not location_row:
                raise InventoryRuleError("Lokasyon sayım kapsamında değil.")
            if location_row["completed_event_id"] is not None:
                raise InventoryRuleError("Tamamlanmış lokasyon yeniden claim edilemez.")

            attempt = db.execute(
                """SELECT attempt_id
                   FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s AND state='ACTIVE'
                   FOR UPDATE""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if attempt:
                attempt_id = UUID(str(attempt["attempt_id"]))
            else:
                attempt_id = uuid4()
                db.execute(
                    """INSERT INTO inventory_mission_attempts(
                         tenant_id,attempt_id,document_id,warehouse_id,location_id,
                         created_by_subject,created_by_employee_id
                       ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        principal.tenant_id,
                        attempt_id,
                        document_id,
                        document["warehouse_id"],
                        location,
                        principal.subject,
                        principal.employee_id,
                    ),
                )

            live = db.execute(
                """SELECT l.lease_id,l.employee_id,l.device_id,l.shift_id,l.valid_from,l.valid_until
                   FROM inventory_mission_leases l
                   LEFT JOIN inventory_mission_lease_closures c
                     ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
                   WHERE l.tenant_id=%s AND l.attempt_id=%s
                     AND c.lease_id IS NULL AND l.valid_until>%s
                   ORDER BY l.valid_from DESC
                   LIMIT 1
                   FOR UPDATE OF l""",
                (principal.tenant_id, attempt_id, now),
            ).fetchone()
            if live:
                if (
                    str(live["employee_id"]) != principal.employee_id
                    or UUID(str(live["device_id"])) != principal.device_id
                    or str(live["shift_id"]) != shift_id
                ):
                    raise InventoryRuleError("Lokasyon başka bir terminal tarafından aktif olarak claim edilmiş.")
                response = _claim_response(
                    principal=principal,
                    document_id=document_id,
                    location_id=location,
                    shift_id=shift_id,
                    attempt_id=attempt_id,
                    lease_id=UUID(str(live["lease_id"])),
                    valid_from=live["valid_from"],
                    valid_until=live["valid_until"],
                    idempotent=True,
                )
                db.commit()
                return response

            previous = db.execute(
                """SELECT employee_id,device_id,shift_id
                   FROM inventory_mission_leases
                   WHERE tenant_id=%s AND attempt_id=%s
                   ORDER BY valid_from DESC
                   LIMIT 1""",
                (principal.tenant_id, attempt_id),
            ).fetchone()
            if previous and (
                str(previous["employee_id"]) != principal.employee_id
                or UUID(str(previous["device_id"])) != principal.device_id
                or str(previous["shift_id"]) != shift_id
            ):
                raise InventoryRuleError(
                    "Önceki mission sahibi değişti; supervisor reassignment olmadan claim devralınamaz."
                )

            lease_id = uuid4()
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,shift_id,
                     warehouse_id,valid_from,valid_until
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id,
                    lease_id,
                    attempt_id,
                    principal.employee_id,
                    principal.device_id,
                    shift_id,
                    document["warehouse_id"],
                    now,
                    valid_until,
                ),
            )
            response = _claim_response(
                principal=principal,
                document_id=document_id,
                location_id=location,
                shift_id=shift_id,
                attempt_id=attempt_id,
                lease_id=lease_id,
                valid_from=now,
                valid_until=valid_until,
                idempotent=False,
            )
            _audit(
                db,
                principal,
                "INVENTORY_MISSION_LEASE_ISSUED",
                document_id,
                document["warehouse_id"],
                response,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_MISSION_LEASE_ISSUED',%s::jsonb)""",
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


def attest_event_lease(
    db: Any,
    principal: InventoryPrincipal,
    *,
    document_id: UUID,
    warehouse_id: str,
    location_id: str,
    active_shift_id: str,
    attempt_id: UUID,
    lease_id: UUID,
    occurred_at: datetime,
    location_completion: bool = False,
) -> dict[str, Any]:
    """Historically attest one already-issued immutable lease interval."""

    location = str(location_id).strip().upper()
    row = db.execute(
        """SELECT a.state AS attempt_state,a.closed_at AS attempt_closed_at,
                  a.document_id,a.warehouse_id,a.location_id,
                  l.employee_id,l.device_id,l.shift_id,l.valid_from,l.valid_until,
                  c.closed_at AS lease_closed_at
           FROM inventory_mission_attempts a
           JOIN inventory_mission_leases l
             ON l.tenant_id=a.tenant_id AND l.attempt_id=a.attempt_id
           LEFT JOIN inventory_mission_lease_closures c
             ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
           WHERE a.tenant_id=%s AND a.attempt_id=%s AND l.lease_id=%s""",
        (principal.tenant_id, attempt_id, lease_id),
    ).fetchone()
    if not row:
        raise PermissionError("Mission attempt/lease authority bulunamadı.")
    if (
        UUID(str(row["document_id"])) != document_id
        or str(row["warehouse_id"]) != str(warehouse_id)
        or str(row["location_id"]).strip().upper() != location
        or str(row["employee_id"]) != principal.employee_id
        or UUID(str(row["device_id"])) != principal.device_id
        or str(row["shift_id"]) != str(active_shift_id).strip()
    ):
        raise PermissionError("Event mission lease binding ile eşleşmiyor.")
    event_time = occurred_at.astimezone(UTC)
    if event_time < row["valid_from"] or event_time > row["valid_until"]:
        raise PermissionError("Event issued lease interval dışında üretildi.")
    if row["lease_closed_at"] is not None and event_time > row["lease_closed_at"]:
        raise PermissionError("Event lease kapandıktan sonra üretildi.")
    if row["attempt_closed_at"] is not None and event_time > row["attempt_closed_at"]:
        raise PermissionError("Event mission attempt kapandıktan sonra üretildi.")
    if location_completion and row["attempt_state"] != "ACTIVE":
        raise InventoryRuleError("Yalnız ACTIVE mission attempt lokasyonu tamamlayabilir.")
    return dict(row)


def complete_attempt(
    db: Any,
    principal: InventoryPrincipal,
    *,
    attempt_id: UUID,
    lease_id: UUID,
    document_id: UUID,
    warehouse_id: str,
    occurred_at: datetime,
) -> None:
    """Close the accepted attempt without rewriting any lease interval or event."""

    attempt = db.execute(
        """SELECT state,created_at FROM inventory_mission_attempts
           WHERE tenant_id=%s AND attempt_id=%s FOR UPDATE""",
        (principal.tenant_id, attempt_id),
    ).fetchone()
    if not attempt or attempt["state"] != "ACTIVE":
        raise InventoryRuleError("Mission attempt completion sırasında ACTIVE değil.")
    later_lease = db.execute(
        """SELECT 1 FROM inventory_mission_leases
           WHERE tenant_id=%s AND attempt_id=%s AND valid_from>%s LIMIT 1""",
        (principal.tenant_id, attempt_id, occurred_at),
    ).fetchone()
    if later_lease:
        raise InventoryRuleError("Stale location completion daha yeni lease interval'ını kapatamaz.")
    existing_closure = db.execute(
        """SELECT 1 FROM inventory_mission_lease_closures
           WHERE tenant_id=%s AND lease_id=%s""",
        (principal.tenant_id, lease_id),
    ).fetchone()
    if existing_closure:
        raise InventoryRuleError("Mission lease daha önce kapatılmış.")
    db.execute(
        """INSERT INTO inventory_mission_lease_closures(
             tenant_id,lease_id,state,reason,closed_at,closed_by_subject
           ) VALUES(%s,%s,'COMPLETED','location completion accepted',%s,%s)""",
        (principal.tenant_id, lease_id, occurred_at, principal.subject),
    )
    db.execute(
        """UPDATE inventory_mission_attempts
           SET state='COMPLETED',closed_at=%s,close_reason='location completion accepted'
           WHERE tenant_id=%s AND attempt_id=%s""",
        (occurred_at, principal.tenant_id, attempt_id),
    )
    _audit(
        db,
        principal,
        "INVENTORY_MISSION_ATTEMPT_COMPLETED",
        document_id,
        warehouse_id,
        {"attempt_id": str(attempt_id), "lease_id": str(lease_id)},
    )


def supersede_attempt(
    principal: InventoryPrincipal,
    document_id: UUID,
    location_id: str,
    reason: str,
) -> dict[str, Any]:
    """Governed supervisor reassignment: close old attempt and create a fresh unleased attempt."""

    principal.validate()
    location = str(location_id).strip().upper()
    reason = str(reason).strip()
    if len(reason) < 3:
        raise InventoryRuleError("Reassignment nedeni zorunludur.")
    now = datetime.now(UTC)
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            _assert_runtime_tenant(db, principal)
            _require_schema_v5(db)
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"mission:{principal.tenant_id}:{document_id}:{location}"),),
            )
            document = db.execute(
                """SELECT warehouse_id,state FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s FOR UPDATE""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document or document["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Sayım bulunamadı veya depo kapsamı dışında.")
            if document["state"] != "COUNTING":
                raise InventoryRuleError("Yalnız COUNTING sayım mission'ı reassignment alabilir.")
            location_row = db.execute(
                """SELECT completed_event_id FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s FOR UPDATE""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            if not location_row:
                raise InventoryRuleError("Lokasyon sayım kapsamında değil.")
            if location_row["completed_event_id"] is not None:
                raise InventoryRuleError("Tamamlanmış lokasyon reassignment alamaz.")

            old = db.execute(
                """SELECT attempt_id FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s AND state='ACTIVE'
                   FOR UPDATE""",
                (principal.tenant_id, document_id, location),
            ).fetchone()
            old_attempt_id = UUID(str(old["attempt_id"])) if old else None
            if old_attempt_id is not None:
                leases = db.execute(
                    """SELECT l.lease_id
                       FROM inventory_mission_leases l
                       LEFT JOIN inventory_mission_lease_closures c
                         ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
                       WHERE l.tenant_id=%s AND l.attempt_id=%s AND c.lease_id IS NULL""",
                    (principal.tenant_id, old_attempt_id),
                ).fetchall()
                for lease in leases:
                    db.execute(
                        """INSERT INTO inventory_mission_lease_closures(
                             tenant_id,lease_id,state,reason,closed_at,closed_by_subject
                           ) VALUES(%s,%s,'SUPERSEDED',%s,%s,%s)""",
                        (
                            principal.tenant_id,
                            lease["lease_id"],
                            reason,
                            now,
                            principal.subject,
                        ),
                    )
                db.execute(
                    """UPDATE inventory_mission_attempts
                       SET state='SUPERSEDED',closed_at=%s,close_reason=%s
                       WHERE tenant_id=%s AND attempt_id=%s""",
                    (now, reason, principal.tenant_id, old_attempt_id),
                )

            new_attempt_id = uuid4()
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,warehouse_id,location_id,
                     created_by_subject,created_by_employee_id
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id,
                    new_attempt_id,
                    document_id,
                    document["warehouse_id"],
                    location,
                    principal.subject,
                    principal.employee_id,
                ),
            )
            record = {
                "document_id": str(document_id),
                "location_id": location,
                "superseded_attempt_id": str(old_attempt_id) if old_attempt_id else None,
                "new_attempt_id": str(new_attempt_id),
                "reason": reason,
            }
            _audit(
                db,
                principal,
                "INVENTORY_MISSION_REASSIGNED",
                document_id,
                document["warehouse_id"],
                record,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_MISSION_REASSIGNED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    document_id,
                    json.dumps(record, sort_keys=True),
                ),
            )
            db.commit()
            return record
        except Exception:
            db.rollback()
            raise
