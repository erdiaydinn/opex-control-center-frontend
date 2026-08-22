"""Transactional managed-device replacement for EAY Inventory.

A replacement is not a queue migration. The old device authority is revoked,
its unfinished mission attempts are superseded, and any replacement-eligible
locations receive fresh unleased attempts. Historical events/leases remain
immutable and auditable; the new device can only continue by claiming fresh
server authority.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from typing import Any
from uuid import UUID, uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_runtime_tenant,
    _audit,
    connect,
)
from .service import InventoryRuleError


def _validate_public_key(public_key_pem: str) -> None:
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("EC key required")
        if public_key.curve.name != "secp256r1":
            raise ValueError("P-256 required")
    except (ValueError, TypeError) as error:
        raise InventoryRuleError("Cihaz P-256 public key değeri geçersiz.") from error


def _activation_hash(activation_code: str) -> tuple[str, str]:
    pepper = os.getenv("INVENTORY_MDM_ACTIVATION_PEPPER", "").strip()
    if not pepper:
        raise RuntimeError("INVENTORY_MDM_ACTIVATION_PEPPER production modunda zorunludur")
    activation_hash = hashlib.sha256(f"{pepper}:{activation_code}".encode()).hexdigest()
    return pepper, activation_hash


def replace_managed_device(
    principal: InventoryPrincipal,
    replaced_device_id: str | UUID,
    activation_code: str,
    public_key_pem: str,
) -> dict[str, Any]:
    """Replace one active managed device without transferring its authority.

    The request is made from the *new* physical device, whose UUID is carried by
    ``principal.device_id``. The body identifies only the old device being
    replaced. A fresh single-use MDM activation code is required even when the
    employee is unchanged.

    Any ACTIVE mission whose latest lease belongs to the old device is
    superseded. If the mission warehouse remains inside the caller's current
    OIDC warehouse scope, a fresh unleased attempt is created. Otherwise no new
    attempt is minted and supervisor reassignment is required. Existing count
    events, leases and audit evidence are never rewritten or rebound.
    """

    principal.validate()
    try:
        old_device_id = UUID(str(replaced_device_id))
    except ValueError as error:
        raise InventoryRuleError("Değiştirilecek managed device UUID geçersiz.") from error
    if old_device_id == principal.device_id:
        raise InventoryRuleError("Bir cihaz kendisinin replacement hedefi olamaz.")

    _validate_public_key(public_key_pem)
    _, activation_hash = _activation_hash(activation_code)
    enrollment_hash = hashlib.sha256(
        f"{principal.tenant_id}:{principal.device_id}:{activation_hash}".encode()
    ).hexdigest()
    now = datetime.now(UTC)
    reason = "managed device replacement; previous evidence preserved"

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"device-replacement:{principal.tenant_id}:{principal.employee_id}"),),
            )

            old = db.execute(
                """SELECT employee_id,status,replaced_by
                   FROM inventory_devices
                   WHERE tenant_id=%s AND device_id=%s
                   FOR UPDATE""",
                (principal.tenant_id, old_device_id),
            ).fetchone()
            new = db.execute(
                """SELECT employee_id,status,public_key_pem
                   FROM inventory_devices
                   WHERE tenant_id=%s AND device_id=%s
                   FOR UPDATE""",
                (principal.tenant_id, principal.device_id),
            ).fetchone()

            if old and old["status"] == "REPLACED" and old["replaced_by"] is not None:
                if (
                    UUID(str(old["replaced_by"])) == principal.device_id
                    and new
                    and new["status"] == "ACTIVE"
                    and str(new["employee_id"]) == principal.employee_id
                    and str(new["public_key_pem"]).strip() == public_key_pem.strip()
                ):
                    db.commit()
                    return {
                        "replaced_device_id": str(old_device_id),
                        "device_id": str(principal.device_id),
                        "status": "ACTIVE",
                        "idempotent": True,
                        "recovered_locations": [],
                        "supervisor_reassignment_required": [],
                    }
                raise InventoryRuleError("Replacement zinciri mevcut managed device kaydıyla çakışıyor.")

            if not old:
                raise InventoryRuleError("Değiştirilecek managed device kaydı bulunamadı.")
            if str(old["employee_id"]) != principal.employee_id:
                raise PermissionError("Başka Employee ID'ye bağlı cihaz replacement yapılamaz.")
            if old["status"] != "ACTIVE":
                raise InventoryRuleError("Yalnız ACTIVE managed device replacement alabilir.")
            if new:
                raise InventoryRuleError("Yeni managed device UUID zaten kayıtlı; replacement fail-closed.")

            activation = db.execute(
                """SELECT employee_id,expires_at,consumed_at
                   FROM inventory_device_activation_codes
                   WHERE tenant_id=%s AND activation_hash=%s
                   FOR UPDATE""",
                (principal.tenant_id, activation_hash),
            ).fetchone()
            if (
                not activation
                or activation["consumed_at"] is not None
                or activation["expires_at"] <= now
                or str(activation["employee_id"]) != principal.employee_id
            ):
                raise InventoryRuleError("MDM replacement activation code geçersiz, süresi dolmuş veya tüketilmiş.")

            # Lock every unfinished attempt whose most recent lease belongs to
            # the old device. This includes expired leases: a replacement must
            # never let the new physical device inherit historical lease lineage.
            attempts = db.execute(
                """SELECT a.attempt_id,a.document_id,a.location_id,a.warehouse_id
                   FROM inventory_mission_attempts a
                   JOIN inventory_document_locations dl
                     ON dl.tenant_id=a.tenant_id
                    AND dl.document_id=a.document_id
                    AND dl.location_id=a.location_id
                   JOIN LATERAL (
                     SELECT l.device_id
                     FROM inventory_mission_leases l
                     WHERE l.tenant_id=a.tenant_id AND l.attempt_id=a.attempt_id
                     ORDER BY l.valid_from DESC
                     LIMIT 1
                   ) latest_lease ON TRUE
                   WHERE a.tenant_id=%s
                     AND a.state='ACTIVE'
                     AND dl.completed_event_id IS NULL
                     AND latest_lease.device_id=%s
                   FOR UPDATE OF a""",
                (principal.tenant_id, old_device_id),
            ).fetchall()

            db.execute(
                """UPDATE inventory_devices
                   SET status='REPLACED',replaced_by=%s,revoked_at=%s
                   WHERE tenant_id=%s AND device_id=%s""",
                (principal.device_id, now, principal.tenant_id, old_device_id),
            )
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                (
                    principal.tenant_id,
                    principal.device_id,
                    principal.employee_id,
                    public_key_pem,
                    enrollment_hash,
                ),
            )
            db.execute(
                """UPDATE inventory_device_activation_codes
                   SET consumed_at=%s,consumed_by=%s
                   WHERE tenant_id=%s AND activation_hash=%s""",
                (now, principal.device_id, principal.tenant_id, activation_hash),
            )

            recovered_locations: list[dict[str, str]] = []
            supervisor_required: list[dict[str, str]] = []
            for attempt in attempts:
                old_attempt_id = UUID(str(attempt["attempt_id"]))
                document_id = UUID(str(attempt["document_id"]))
                location_id = str(attempt["location_id"])
                warehouse_id = str(attempt["warehouse_id"])

                db.execute(
                    """INSERT INTO inventory_mission_lease_closures(
                         tenant_id,lease_id,state,reason,closed_at,closed_by_subject
                       )
                       SELECT l.tenant_id,l.lease_id,'SUPERSEDED',%s,%s,%s
                       FROM inventory_mission_leases l
                       LEFT JOIN inventory_mission_lease_closures c
                         ON c.tenant_id=l.tenant_id AND c.lease_id=l.lease_id
                       WHERE l.tenant_id=%s AND l.attempt_id=%s AND c.lease_id IS NULL""",
                    (
                        reason,
                        now,
                        principal.subject,
                        principal.tenant_id,
                        old_attempt_id,
                    ),
                )
                db.execute(
                    """UPDATE inventory_mission_attempts
                       SET state='SUPERSEDED',closed_at=%s,close_reason=%s
                       WHERE tenant_id=%s AND attempt_id=%s""",
                    (now, reason, principal.tenant_id, old_attempt_id),
                )

                if warehouse_id not in principal.warehouse_scope:
                    supervisor_required.append(
                        {
                            "document_id": str(document_id),
                            "location_id": location_id,
                            "superseded_attempt_id": str(old_attempt_id),
                        }
                    )
                    continue

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
                        warehouse_id,
                        location_id,
                        principal.subject,
                        principal.employee_id,
                    ),
                )
                recovered_locations.append(
                    {
                        "document_id": str(document_id),
                        "location_id": location_id,
                        "superseded_attempt_id": str(old_attempt_id),
                        "new_attempt_id": str(new_attempt_id),
                    }
                )

            record: dict[str, Any] = {
                "replaced_device_id": str(old_device_id),
                "device_id": str(principal.device_id),
                "employee_id": principal.employee_id,
                "recovered_locations": recovered_locations,
                "supervisor_reassignment_required": supervisor_required,
                "evidence_policy": "PRESERVE_NO_REBIND",
            }
            _audit(
                db,
                principal,
                "INVENTORY_DEVICE_REPLACED",
                None,
                sorted(principal.warehouse_scope)[0],
                record,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_DEVICE_REPLACED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    principal.device_id,
                    json.dumps(record, sort_keys=True),
                ),
            )
            db.commit()
            return {
                **record,
                "status": "ACTIVE",
                "idempotent": False,
            }
        except Exception:
            db.rollback()
            raise
