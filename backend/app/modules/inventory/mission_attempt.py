"""Server-owned Inventory mission attempts and historically verifiable leases."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .service import InventoryRuleError

MIN_LEASE_SECONDS = 60
MAX_LEASE_SECONDS = 1800


def mission_claim_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_shift_id": str(payload["active_shift_id"]).strip(),
        "document_id": str(UUID(str(payload["document_id"]))),
        "lease_seconds": int(payload["lease_seconds"]),
        "location_id": str(payload["location_id"]).strip().upper(),
    }


def _require_schema_v5(db: Any) -> None:
    row = db.execute(
        "SELECT 1 FROM inventory_schema_migrations WHERE version=5",
    ).fetchone()
    if not row:
        raise RuntimeError("Inventory mission-attempt migration v5 uygulanmamış.")


def attempt_readiness() -> bool:
    from .production import connect

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


def claim_mission_attempt(
    principal: Any,
    payload: dict[str, Any],
    request_timestamp: str,
    request_nonce: str,
    request_signature: str,
) -> dict[str, Any]:
    """Claim exactly one document/location for one employee/device/shift lease."""

    from .production import (
        _advisory_key,
        _assert_active_device,
        _assert_runtime_tenant,
        _audit,
        _verify_device_proof,
        canonical_payload_hash,
        connect,
    )

    principal.validate()
    document_id = UUID(str(payload["document_id"]))
    location_id = str(payload["location_id"]).strip().upper()
    active_shift_id = str(payload["active_shift_id"]).strip()
    lease_seconds = int(payload["lease_seconds"])
    if not MIN_LEASE_SECONDS <= lease_seconds <= MAX_LEASE_SECONDS:
        raise InventoryRuleError("Mission lease süresi güvenli sınırlar dışında.")
    actual_hash = canonical_payload_hash(mission_claim_hash_input(payload))
    if str(payload["payload_hash"]) != actual_hash:
        raise InventoryRuleError("Mission claim payload hash doğrulaması başarısız.")

    now = datetime.now(UTC)
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            _require_schema_v5(db)
            _assert_active_device(db, principal)
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
                (_advisory_key(f"mission:{principal.tenant_id}:{document_id}:{location_id}"),),
            )
            document = db.execute(
                """SELECT warehouse_id,state,revision FROM inventory_documents
                   WHERE tenant_id=%s AND id=%s FOR UPDATE""",
                (principal.tenant_id, document_id),
            ).fetchone()
            if not document:
                raise InventoryRuleError("Sayım görevi bulunamadı.")
            warehouse_id = str(document["warehouse_id"])
            if warehouse_id not in principal.warehouse_scope:
                raise PermissionError("Sayım görevi depo kapsamı dışında.")
            if document["state"] != "COUNTING":
                raise InventoryRuleError("Yalnız aktif sayım görevi claim edilebilir.")
            location = db.execute(
                """SELECT completed_event_id FROM inventory_document_locations
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s FOR UPDATE""",
                (principal.tenant_id, document_id, location_id),
            ).fetchone()
            if not location:
                raise InventoryRuleError("Lokasyon sayım kapsamında değil.")
            if location.get("completed_event_id") is not None:
                raise InventoryRuleError("Tamamlanmış lokasyon yeniden claim edilemez.")

            try:
                shift = attest_shift_at_event(
                    principal.tenant_id,
                    principal.employee_id,
                    warehouse_id,
                    active_shift_id,
                    now.isoformat(),
                )
            except ActiveShiftAuthorityError as error:
                raise RuntimeError("Workforce mission vardiya authority kullanılamıyor.") from error
            if shift is None:
                raise PermissionError("Mission claim aktif vardiya dışında yapılamaz.")

            attempt = db.execute(
                """SELECT attempt_id,employee_id,device_id,active_shift_id
                   FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND document_id=%s AND location_id=%s
                     AND status='ACTIVE' FOR UPDATE""",
                (principal.tenant_id, document_id, location_id),
            ).fetchone()
            if attempt:
                lease = db.execute(
                    """SELECT lease_id,valid_from,expires_at FROM inventory_mission_leases
                       WHERE tenant_id=%s AND attempt_id=%s AND status='ACTIVE'
                       ORDER BY created_at DESC LIMIT 1 FOR UPDATE""",
                    (principal.tenant_id, attempt["attempt_id"]),
                ).fetchone()
                if lease and lease["expires_at"] > now:
                    same_holder = (
                        attempt["employee_id"] == principal.employee_id
                        and attempt["device_id"] == principal.device_id
                        and attempt["active_shift_id"] == active_shift_id
                    )
                    if not same_holder:
                        raise InventoryRuleError("Lokasyon başka bir aktif terminal tarafından claim edilmiş.")
                    response = {
                        "attempt_id": str(attempt["attempt_id"]),
                        "lease_id": str(lease["lease_id"]),
                        "document_id": str(document_id),
                        "location_id": location_id,
                        "active_shift_id": active_shift_id,
                        "valid_from": lease["valid_from"].isoformat(),
                        "expires_at": lease["expires_at"].isoformat(),
                        "idempotent_claim": True,
                    }
                    db.commit()
                    return response
                if lease:
                    db.execute(
                        """UPDATE inventory_mission_leases
                           SET status='EXPIRED'
                           WHERE tenant_id=%s AND lease_id=%s AND status='ACTIVE'""",
                        (principal.tenant_id, lease["lease_id"]),
                    )
                db.execute(
                    """UPDATE inventory_mission_attempts
                       SET status='ABANDONED',abandoned_at=%s,abandonment_reason='LEASE_EXPIRED'
                       WHERE tenant_id=%s AND attempt_id=%s AND status='ACTIVE'""",
                    (now, principal.tenant_id, attempt["attempt_id"]),
                )

            attempt_id = uuid4()
            lease_id = uuid4()
            expires_at = now + timedelta(seconds=lease_seconds)
            db.execute(
                """INSERT INTO inventory_mission_attempts(
                     tenant_id,attempt_id,document_id,location_id,warehouse_id,
                     employee_id,device_id,active_shift_id,status,created_at
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'ACTIVE',%s)""",
                (
                    principal.tenant_id,
                    attempt_id,
                    document_id,
                    location_id,
                    warehouse_id,
                    principal.employee_id,
                    principal.device_id,
                    active_shift_id,
                    now,
                ),
            )
            db.execute(
                """INSERT INTO inventory_mission_leases(
                     tenant_id,lease_id,attempt_id,employee_id,device_id,active_shift_id,
                     status,valid_from,expires_at
                   ) VALUES(%s,%s,%s,%s,%s,%s,'ACTIVE',%s,%s)""",
                (
                    principal.tenant_id,
                    lease_id,
                    attempt_id,
                    principal.employee_id,
                    principal.device_id,
                    active_shift_id,
                    now,
                    expires_at,
                ),
            )
            response = {
                "attempt_id": str(attempt_id),
                "lease_id": str(lease_id),
                "document_id": str(document_id),
                "location_id": location_id,
                "active_shift_id": active_shift_id,
                "valid_from": now.isoformat(),
                "expires_at": expires_at.isoformat(),
                "idempotent_claim": False,
            }
            _audit(db, principal, "MISSION_ATTEMPT_CLAIMED", document_id, warehouse_id, response)
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_MISSION_CLAIMED',%s::jsonb)""",
                (principal.tenant_id, uuid4(), document_id, __import__("json").dumps(response, sort_keys=True)),
            )
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise


def verify_event_lease(
    db: Any,
    principal: Any,
    payload: dict[str, Any],
    document_id: UUID,
    location_id: str,
    occurred_at: datetime,
) -> tuple[UUID, UUID]:
    """Verify exact signed lease authority at event time, not upload time."""

    _require_schema_v5(db)
    attempt_id = UUID(str(payload["attempt_id"]))
    lease_id = UUID(str(payload["lease_id"]))
    active_shift_id = str(payload["active_shift_id"]).strip()
    row = db.execute(
        """SELECT a.status AS attempt_status,l.status AS lease_status,
                  l.valid_from,l.expires_at,l.revoked_at
           FROM inventory_mission_attempts a
           JOIN inventory_mission_leases l
             ON l.tenant_id=a.tenant_id AND l.attempt_id=a.attempt_id
           WHERE a.tenant_id=%s AND a.attempt_id=%s AND l.lease_id=%s
             AND a.document_id=%s AND a.location_id=%s
             AND a.employee_id=%s AND a.device_id=%s AND a.active_shift_id=%s
             AND l.employee_id=%s AND l.device_id=%s AND l.active_shift_id=%s""",
        (
            principal.tenant_id,
            attempt_id,
            lease_id,
            document_id,
            location_id,
            principal.employee_id,
            principal.device_id,
            active_shift_id,
            principal.employee_id,
            principal.device_id,
            active_shift_id,
        ),
    ).fetchone()
    if not row:
        raise PermissionError("Event mission attempt/lease authority ile eşleşmiyor.")
    if row["attempt_status"] == "COMPLETED" or row["lease_status"] == "COMPLETED":
        raise InventoryRuleError("Tamamlanmış mission attempt yeni event kabul etmez.")
    if occurred_at < row["valid_from"] or occurred_at > row["expires_at"]:
        raise PermissionError("Event mission lease zaman penceresi dışında üretildi.")
    if row["revoked_at"] is not None and occurred_at > row["revoked_at"]:
        raise PermissionError("Event revoke edilmiş mission lease sonrasında üretildi.")
    return attempt_id, lease_id


def complete_mission_attempt(
    db: Any,
    principal: Any,
    attempt_id: UUID,
    lease_id: UUID,
    completion_event_id: UUID,
    occurred_at: datetime,
) -> None:
    updated = db.execute(
        """UPDATE inventory_mission_attempts
           SET status='COMPLETED',completed_at=%s,completed_event_id=%s
           WHERE tenant_id=%s AND attempt_id=%s AND status='ACTIVE'""",
        (occurred_at, completion_event_id, principal.tenant_id, attempt_id),
    )
    if updated.rowcount != 1:
        raise InventoryRuleError("Mission attempt artık completion kabul etmiyor.")
    lease = db.execute(
        """UPDATE inventory_mission_leases
           SET status='COMPLETED'
           WHERE tenant_id=%s AND lease_id=%s AND attempt_id=%s AND status='ACTIVE'""",
        (principal.tenant_id, lease_id, attempt_id),
    )
    if lease.rowcount != 1:
        raise InventoryRuleError("Mission lease artık completion kabul etmiyor.")


def abandon_mission_attempt(principal: Any, attempt_id: UUID, reason: str) -> dict[str, Any]:
    """Supervisor-governed release for device loss/reassignment; evidence is retained."""

    from .production import _assert_runtime_tenant, _audit, connect

    normalized_reason = reason.strip()
    if len(normalized_reason) < 3:
        raise InventoryRuleError("Mission abandon nedeni zorunludur.")
    now = datetime.now(UTC)
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            _require_schema_v5(db)
            attempt = db.execute(
                """SELECT document_id,warehouse_id,status FROM inventory_mission_attempts
                   WHERE tenant_id=%s AND attempt_id=%s FOR UPDATE""",
                (principal.tenant_id, attempt_id),
            ).fetchone()
            if not attempt:
                raise InventoryRuleError("Mission attempt bulunamadı.")
            if attempt["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Mission attempt depo kapsamı dışında.")
            if attempt["status"] != "ACTIVE":
                raise InventoryRuleError("Yalnız aktif mission attempt abandon edilebilir.")
            db.execute(
                """UPDATE inventory_mission_leases SET status='REVOKED',revoked_at=%s
                   WHERE tenant_id=%s AND attempt_id=%s AND status='ACTIVE'""",
                (now, principal.tenant_id, attempt_id),
            )
            db.execute(
                """UPDATE inventory_mission_attempts
                   SET status='ABANDONED',abandoned_at=%s,abandonment_reason=%s
                   WHERE tenant_id=%s AND attempt_id=%s AND status='ACTIVE'""",
                (now, normalized_reason, principal.tenant_id, attempt_id),
            )
            response = {
                "attempt_id": str(attempt_id),
                "status": "ABANDONED",
                "reason": normalized_reason,
            }
            _audit(
                db,
                principal,
                "MISSION_ATTEMPT_ABANDONED",
                attempt["document_id"],
                attempt["warehouse_id"],
                response,
            )
            db.commit()
            return response
        except Exception:
            db.rollback()
            raise
