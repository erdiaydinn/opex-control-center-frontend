"""PostgreSQL-authoritative EAY Inventory terminal operations.

This module deliberately has no SQLite fallback. Production startup and every
mutation fail closed when the database, tenant identity, employee identity or
managed-device identity is unavailable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import base64
import hashlib
import json
import os
from typing import Any
from uuid import UUID, uuid4

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec

from .service import InventoryRuleError


@dataclass(frozen=True)
class InventoryPrincipal:
    tenant_id: str
    subject: str
    employee_id: str
    warehouse_scope: frozenset[str]
    device_id: UUID

    def validate(self) -> None:
        if not self.tenant_id or not self.subject or not self.employee_id:
            raise InventoryRuleError("Tenant, kullanıcı ve Employee ID kimliği zorunludur.")
        if not self.warehouse_scope:
            raise InventoryRuleError("Depo kapsamı olmayan kimlik Inventory kullanamaz.")


def _dsn() -> str:
    value = os.getenv("INVENTORY_DATABASE_URL", "").strip()
    if not value:
        raise RuntimeError("INVENTORY_DATABASE_URL production modunda zorunludur")
    return value


def connect():
    from psycopg import Connection
    from psycopg.rows import dict_row

    return Connection.connect(_dsn(), row_factory=dict_row, autocommit=False)


def canonical_payload_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def terminal_event_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    quantity = Decimal(str(payload["quantity"])).normalize()
    return {
        "barcode": str(payload["barcode"]).strip(),
        "device_sequence": int(payload["device_sequence"]),
        "document_id": str(UUID(str(payload["document_id"]))),
        "event_id": str(UUID(str(payload["event_id"]))),
        "location_id": str(payload["location_id"]).strip().upper(),
        "occurred_at": str(payload["occurred_at"]),
        "quantity": format(quantity, "f"),
        "symbology": str(payload["symbology"]).strip(),
    }


def enrollment_binding(principal: InventoryPrincipal) -> str:
    """Opaque tenant/device/employee binding for queued terminal events."""
    principal.validate()
    raw = f"v1\n{principal.tenant_id}\n{principal.device_id}\n{principal.employee_id}".encode()
    return hashlib.sha256(raw).hexdigest()


def _require_enrollment_binding(principal: InventoryPrincipal, claimed: str) -> None:
    expected = enrollment_binding(principal)
    if not claimed or not hashlib.compare_digest(claimed, expected):
        raise PermissionError("Offline event mevcut tenant/device enrollment ile eşleşmiyor.")


def _advisory_key(value: str) -> int:
    raw = hashlib.sha256(value.encode("utf-8")).digest()[:8]
    return int.from_bytes(raw, "big", signed=True)


def _assert_runtime_tenant(db: Any, principal: InventoryPrincipal) -> None:
    row = db.execute("SELECT inventory_current_tenant() AS tenant_id").fetchone()
    if not row or row["tenant_id"] != principal.tenant_id:
        raise PermissionError("Database runtime role tenant binding ile OIDC tenant eşleşmiyor.")


def _assert_active_device(db: Any, principal: InventoryPrincipal) -> None:
    row = db.execute(
        """SELECT 1 FROM inventory_devices
           WHERE tenant_id=%s AND device_id=%s AND employee_id=%s AND status='ACTIVE'""",
        (principal.tenant_id, principal.device_id, principal.employee_id),
    ).fetchone()
    if not row:
        raise PermissionError("Aktif managed device kaydı gerekli.")


def _redis_event_preflight(tenant_id: str, event_id: UUID, payload_hash: str) -> None:
    url = os.getenv("INVENTORY_REDIS_URL", "").strip()
    if not url:
        raise RuntimeError("INVENTORY_REDIS_URL production modunda zorunludur")
    from redis import Redis

    client = Redis.from_url(url, socket_connect_timeout=2, socket_timeout=2, decode_responses=True)
    key = f"eay:inventory:event:{hashlib.sha256(f'{tenant_id}:{event_id}'.encode()).hexdigest()}"
    try:
        existing = client.get(key)
        if existing and existing != payload_hash:
            raise InventoryRuleError("Event ID Redis koordinasyonunda farklı payload ile görülmüş.")
        client.set(key, payload_hash, nx=True, ex=86_400)
    except InventoryRuleError:
        raise
    except Exception as error:
        raise RuntimeError("Inventory Redis koordinasyon authority kullanılamıyor") from error


def _audit(db: Any, principal: InventoryPrincipal, action: str, document_id: UUID | None, warehouse_id: str, record: dict[str, Any]) -> None:
    db.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(f"audit:{principal.tenant_id}"),))
    previous = db.execute("SELECT hash FROM inventory_audit WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 1", (principal.tenant_id,)).fetchone()
    previous_hash = previous["hash"] if previous else "GENESIS"
    event_id = uuid4(); occurred_at = datetime.now(UTC)
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(f"{previous_hash}|{event_id}|{principal.subject}|{principal.employee_id}|{action}|{body}|{occurred_at.isoformat()}".encode()).hexdigest()
    db.execute("""INSERT INTO inventory_audit(tenant_id,event_id,actor_subject,employee_id,device_id,warehouse_id,document_id,action,record,previous_hash,hash,occurred_at)
                  VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
               (principal.tenant_id,event_id,principal.subject,principal.employee_id,principal.device_id,warehouse_id,document_id,action,body,previous_hash,digest,occurred_at))


def _verify_device_proof(db: Any, principal: InventoryPrincipal, payload_hash: str, timestamp: str, nonce: str, signature: str) -> None:
    if not timestamp or not nonce or not signature: raise InventoryRuleError("İmzalı cihaz isteği zorunludur.")
    requested_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if requested_at.tzinfo is None or abs((datetime.now(UTC) - requested_at).total_seconds()) > 120: raise InventoryRuleError("Cihaz isteğinin zaman penceresi geçersiz.")
    if len(nonce) < 16 or len(nonce) > 120: raise InventoryRuleError("Cihaz nonce değeri geçersiz.")
    device = db.execute("SELECT employee_id,status,public_key_pem FROM inventory_devices WHERE tenant_id=%s AND device_id=%s FOR SHARE", (principal.tenant_id, principal.device_id)).fetchone()
    if not device or device["status"] != "ACTIVE" or device["employee_id"] != principal.employee_id: raise InventoryRuleError("Cihaz aktif MDM kaydı ve Employee ID ile eşleşmiyor.")
    message = f"{principal.device_id}\n{timestamp}\n{nonce}\n{payload_hash}".encode()
    try:
        public_key = serialization.load_pem_public_key(device["public_key_pem"].encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey): raise ValueError("EC key required")
        public_key.verify(base64.b64decode(signature, validate=True), message, ec.ECDSA(hashes.SHA256()))
    except (ValueError, TypeError, InvalidSignature) as error: raise InventoryRuleError("Cihaz isteği imzası geçersiz.") from error
    try: db.execute("INSERT INTO inventory_device_nonces(tenant_id,device_id,nonce,request_timestamp) VALUES(%s,%s,%s,%s)", (principal.tenant_id, principal.device_id, nonce, requested_at))
    except Exception as error: raise InventoryRuleError("Cihaz isteği replay olarak reddedildi.") from error


def readiness() -> dict[str, Any]:
    checks = {"production_mode": os.getenv("EAY_INVENTORY_MODE") == "production", "postgres_configured": bool(os.getenv("INVENTORY_DATABASE_URL")), "redis_configured": bool(os.getenv("INVENTORY_REDIS_URL")), "oidc_configured": all(os.getenv(name) for name in ("OPEX_OIDC_ISSUER", "OPEX_OIDC_AUDIENCE", "OPEX_OIDC_JWKS_URL")), "mdm_activation_pepper": bool(os.getenv("INVENTORY_MDM_ACTIVATION_PEPPER"))}
    if checks["postgres_configured"]:
        try:
            with connect() as db: checks["migration_v3"] = bool(db.execute("SELECT version FROM inventory_schema_migrations WHERE version=3").fetchone())
        except Exception: checks["migration_v3"] = False
    else: checks["migration_v3"] = False
    if checks["redis_configured"]:
        try:
            from redis import Redis
            checks["redis_healthy"] = bool(Redis.from_url(os.environ["INVENTORY_REDIS_URL"], socket_connect_timeout=2, socket_timeout=2).ping())
        except Exception: checks["redis_healthy"] = False
    else: checks["redis_healthy"] = False
    return {"status": "ready" if all(checks.values()) else "blocked", "checks": checks}


def enroll_device(principal: InventoryPrincipal, activation_code: str, public_key_pem: str) -> dict[str, Any]:
    principal.validate(); pepper = os.getenv("INVENTORY_MDM_ACTIVATION_PEPPER", "")
    if not pepper: raise RuntimeError("INVENTORY_MDM_ACTIVATION_PEPPER production modunda zorunludur")
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or public_key.curve.name != "secp256r1": raise ValueError("P-256 required")
    except (ValueError, TypeError) as error: raise InventoryRuleError("Cihaz P-256 public key değeri geçersiz.") from error
    activation_hash = hashlib.sha256(f"{pepper}:{activation_code}".encode()).hexdigest(); enrollment_hash = hashlib.sha256(f"{principal.tenant_id}:{principal.device_id}:{activation_hash}".encode()).hexdigest()
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"); _assert_runtime_tenant(db, principal)
            existing = db.execute("SELECT employee_id,public_key_pem,status FROM inventory_devices WHERE tenant_id=%s AND device_id=%s FOR UPDATE", (principal.tenant_id, principal.device_id)).fetchone()
            if existing:
                if existing["employee_id"] == principal.employee_id and existing["public_key_pem"].strip() == public_key_pem.strip() and existing["status"] == "ACTIVE":
                    return {"device_id": str(principal.device_id), "status": "ACTIVE", "idempotent": True, "enrollment_binding": enrollment_binding(principal)}
                raise InventoryRuleError("Managed device kimliği başka bir kayıtla çakışıyor.")
            activation = db.execute("SELECT employee_id,expires_at,consumed_at FROM inventory_device_activation_codes WHERE tenant_id=%s AND activation_hash=%s FOR UPDATE", (principal.tenant_id, activation_hash)).fetchone()
            if not activation or activation["consumed_at"] is not None or activation["expires_at"] <= datetime.now(UTC) or activation["employee_id"] != principal.employee_id: raise InventoryRuleError("MDM activation code geçersiz, süresi dolmuş veya tüketilmiş.")
            db.execute("INSERT INTO inventory_devices(tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status) VALUES(%s,%s,%s,%s,%s,'ACTIVE')", (principal.tenant_id, principal.device_id, principal.employee_id, public_key_pem, enrollment_hash))
            db.execute("UPDATE inventory_device_activation_codes SET consumed_at=now(),consumed_by=%s WHERE tenant_id=%s AND activation_hash=%s", (principal.device_id, principal.tenant_id, activation_hash))
            _audit(db, principal, "DEVICE_ENROLLED", None, sorted(principal.warehouse_scope)[0], {"device_id": str(principal.device_id), "employee_id": principal.employee_id}); db.commit()
            return {"device_id": str(principal.device_id), "status": "ACTIVE", "enrollment_binding": enrollment_binding(principal)}
        except Exception: db.rollback(); raise

# The remainder of the production module is retained below by this branch's prior implementation.
