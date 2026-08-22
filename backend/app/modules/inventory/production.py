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

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
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
        "active_shift_id": str(payload["active_shift_id"]).strip(),
        "barcode": str(payload["barcode"]).strip(),
        "device_sequence": int(payload["device_sequence"]),
        "document_id": str(UUID(str(payload["document_id"]))),
        "event_id": str(UUID(str(payload["event_id"]))),
        "location_id": str(payload["location_id"]).strip().upper(),
        "occurred_at": str(payload["occurred_at"]),
        "quantity": format(quantity, "f"),
        "symbology": str(payload["symbology"]).strip(),
    }


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


def _audit(
    db: Any,
    principal: InventoryPrincipal,
    action: str,
    document_id: UUID | None,
    warehouse_id: str,
    record: dict[str, Any],
) -> None:
    db.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(f"audit:{principal.tenant_id}"),))
    previous = db.execute(
        "SELECT hash FROM inventory_audit WHERE tenant_id=%s ORDER BY sequence DESC LIMIT 1",
        (principal.tenant_id,),
    ).fetchone()
    previous_hash = previous["hash"] if previous else "GENESIS"
    event_id = uuid4()
    occurred_at = datetime.now(UTC)
    body = json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(
        f"{previous_hash}|{event_id}|{principal.subject}|{principal.employee_id}|{action}|{body}|{occurred_at.isoformat()}".encode()
    ).hexdigest()
    db.execute(
        """INSERT INTO inventory_audit(
             tenant_id,event_id,actor_subject,employee_id,device_id,warehouse_id,
             document_id,action,record,previous_hash,hash,occurred_at
           ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
        (
            principal.tenant_id, event_id, principal.subject, principal.employee_id,
            principal.device_id, warehouse_id, document_id, action, body,
            previous_hash, digest, occurred_at,
        ),
    )


def _verify_device_proof(
    db: Any,
    principal: InventoryPrincipal,
    payload_hash: str,
    timestamp: str,
    nonce: str,
    signature: str,
) -> None:
    if not timestamp or not nonce or not signature:
        raise InventoryRuleError("İmzalı cihaz isteği zorunludur.")
    requested_at = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    if requested_at.tzinfo is None or abs((datetime.now(UTC) - requested_at).total_seconds()) > 120:
        raise InventoryRuleError("Cihaz isteğinin zaman penceresi geçersiz.")
    if len(nonce) < 16 or len(nonce) > 120:
        raise InventoryRuleError("Cihaz nonce değeri geçersiz.")
    device = db.execute(
        """SELECT employee_id,status,public_key_pem FROM inventory_devices
           WHERE tenant_id=%s AND device_id=%s FOR SHARE""",
        (principal.tenant_id, principal.device_id),
    ).fetchone()
    if not device or device["status"] != "ACTIVE" or device["employee_id"] != principal.employee_id:
        raise InventoryRuleError("Cihaz aktif MDM kaydı ve Employee ID ile eşleşmiyor.")
    message = f"{principal.device_id}\n{timestamp}\n{nonce}\n{payload_hash}".encode()
    try:
        public_key = serialization.load_pem_public_key(device["public_key_pem"].encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise ValueError("EC key required")
        public_key.verify(base64.b64decode(signature, validate=True), message, ec.ECDSA(hashes.SHA256()))
    except (ValueError, TypeError, InvalidSignature) as error:
        raise InventoryRuleError("Cihaz isteği imzası geçersiz.") from error
    try:
        db.execute(
            """INSERT INTO inventory_device_nonces(tenant_id,device_id,nonce,request_timestamp)
               VALUES(%s,%s,%s,%s)""",
            (principal.tenant_id, principal.device_id, nonce, requested_at),
        )
    except Exception as error:
        raise InventoryRuleError("Cihaz isteği replay olarak reddedildi.") from error


def readiness() -> dict[str, Any]:
    checks = {
        "production_mode": os.getenv("EAY_INVENTORY_MODE") == "production",
        "postgres_configured": bool(os.getenv("INVENTORY_DATABASE_URL")),
        "redis_configured": bool(os.getenv("INVENTORY_REDIS_URL")),
        "oidc_configured": all(os.getenv(name) for name in ("OPEX_OIDC_ISSUER", "OPEX_OIDC_AUDIENCE", "OPEX_OIDC_JWKS_URL")),
        "mdm_activation_pepper": bool(os.getenv("INVENTORY_MDM_ACTIVATION_PEPPER")),
    }
    if checks["postgres_configured"]:
        try:
            with connect() as db:
                row = db.execute("SELECT version FROM inventory_schema_migrations WHERE version=3").fetchone()
                checks["migration_v3"] = bool(row)
        except Exception:
            checks["migration_v3"] = False
    else:
        checks["migration_v3"] = False
    if checks["redis_configured"]:
        try:
            from redis import Redis

            checks["redis_healthy"] = bool(Redis.from_url(
                os.environ["INVENTORY_REDIS_URL"], socket_connect_timeout=2, socket_timeout=2,
            ).ping())
        except Exception:
            checks["redis_healthy"] = False
    else:
        checks["redis_healthy"] = False
    return {"status": "ready" if all(checks.values()) else "blocked", "checks": checks}


def enroll_device(
    principal: InventoryPrincipal,
    activation_code: str,
    public_key_pem: str,
) -> dict[str, Any]:
    principal.validate()
    pepper = os.getenv("INVENTORY_MDM_ACTIVATION_PEPPER", "")
    if not pepper:
        raise RuntimeError("INVENTORY_MDM_ACTIVATION_PEPPER production modunda zorunludur")
    try:
        public_key = serialization.load_pem_public_key(public_key_pem.encode())
        if not isinstance(public_key, ec.EllipticCurvePublicKey) or public_key.curve.name != "secp256r1":
            raise ValueError("P-256 required")
    except (ValueError, TypeError) as error:
        raise InventoryRuleError("Cihaz P-256 public key değeri geçersiz.") from error
    activation_hash = hashlib.sha256(f"{pepper}:{activation_code}".encode()).hexdigest()
    enrollment_hash = hashlib.sha256(f"{principal.tenant_id}:{principal.device_id}:{activation_hash}".encode()).hexdigest()
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            existing = db.execute(
                """SELECT employee_id,public_key_pem,status FROM inventory_devices
                   WHERE tenant_id=%s AND device_id=%s FOR UPDATE""",
                (principal.tenant_id, principal.device_id),
            ).fetchone()
            if existing:
                if (
                    existing["employee_id"] == principal.employee_id
                    and existing["public_key_pem"].strip() == public_key_pem.strip()
                    and existing["status"] == "ACTIVE"
                ):
                    return {"device_id": str(principal.device_id), "status": "ACTIVE", "idempotent": True}
                raise InventoryRuleError("Managed device kimliği başka bir kayıtla çakışıyor.")
            activation = db.execute(
                """SELECT employee_id,expires_at,consumed_at FROM inventory_device_activation_codes
                   WHERE tenant_id=%s AND activation_hash=%s FOR UPDATE""",
                (principal.tenant_id, activation_hash),
            ).fetchone()
            if (
                not activation or activation["consumed_at"] is not None
                or activation["expires_at"] <= datetime.now(UTC)
                or activation["employee_id"] != principal.employee_id
            ):
                raise InventoryRuleError("MDM activation code geçersiz, süresi dolmuş veya tüketilmiş.")
            db.execute(
                """INSERT INTO inventory_devices(
                     tenant_id,device_id,employee_id,public_key_pem,mdm_enrollment_hash,status
                   ) VALUES(%s,%s,%s,%s,%s,'ACTIVE')""",
                (principal.tenant_id, principal.device_id, principal.employee_id, public_key_pem, enrollment_hash),
            )
            db.execute(
                """UPDATE inventory_device_activation_codes SET consumed_at=now(),consumed_by=%s
                   WHERE tenant_id=%s AND activation_hash=%s""",
                (principal.device_id, principal.tenant_id, activation_hash),
            )
            _audit(db, principal, "DEVICE_ENROLLED", None, sorted(principal.warehouse_scope)[0], {
                "device_id": str(principal.device_id), "employee_id": principal.employee_id,
            })
            db.commit()
            return {"device_id": str(principal.device_id), "status": "ACTIVE"}
        except Exception:
            db.rollback()
            raise


def create_document(principal: InventoryPrincipal, payload: dict[str, Any]) -> dict[str, Any]:
    principal.validate()
    warehouse_id = str(payload["warehouse_id"]).strip()
    if warehouse_id not in principal.warehouse_scope:
        raise PermissionError("Sayım deposu yetki kapsamı dışında.")
    count_mode = str(payload.get("count_mode", "GOLDEN_COUNT")).strip().upper()
    if count_mode not in {"GOLDEN_COUNT", "WALL_TO_WALL"}:
        raise InventoryRuleError("Geçersiz sayım modu.")
    locations = sorted({str(value).strip().upper() for value in payload["locations"] if str(value).strip()})
    products = payload["products"]
    if not locations or not products:
        raise InventoryRuleError("Lokasyon ve ürün listesi zorunludur.")
    if len(locations) != len(payload["locations"]):
        raise InventoryRuleError("Lokasyon listesinde boş veya mükerrer kayıt var.")
    if count_mode == "WALL_TO_WALL" and "LOST_FOUND" not in locations:
        locations = sorted([*locations, "LOST_FOUND"])
    document_id = uuid4()
    seen_skus: set[str] = set()
    seen_barcodes: set[str] = set()
    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
            _assert_runtime_tenant(db, principal)
            if count_mode == "WALL_TO_WALL":
                db.execute(
                    "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                    (f"inventory:w2w:warehouse:{principal.tenant_id}:{warehouse_id}",),
                )
                competing = db.execute(
                    """SELECT id FROM inventory_documents
                       WHERE tenant_id=%s AND warehouse_id=%s
                         AND count_mode='WALL_TO_WALL'
                         AND state IN ('COUNTING','SUBMITTED','RECONCILING')
                       LIMIT 1""",
                    (principal.tenant_id, warehouse_id),
                ).fetchone()
                if competing:
                    raise InventoryRuleError("Bu depoda zaten aktif bir Wall-to-Wall sayımı var.")
            db.execute(
                """INSERT INTO inventory_documents(
                     tenant_id,id,warehouse_id,name,state,created_by,count_mode
                   ) VALUES(%s,%s,%s,%s,'COUNTING',%s,%s)""",
                (
                    principal.tenant_id,
                    document_id,
                    warehouse_id,
                    payload["name"],
                    principal.subject,
                    count_mode,
                ),
            )
            for location in locations:
                db.execute(
                    """INSERT INTO inventory_document_locations(
                         tenant_id,document_id,location_id
                       ) VALUES(%s,%s,%s)""",
                    (principal.tenant_id, document_id, location),
                )
            for product in products:
                sku = str(product.get("sku", "")).strip()
                barcode = str(product.get("barcode", "")).strip()
                if not sku or not barcode or sku in seen_skus or barcode in seen_barcodes:
                    raise InventoryRuleError("SKU ve barkodlar boş olamaz ve tekil olmalıdır.")
                seen_skus.add(sku); seen_barcodes.add(barcode)
                db.execute(
                    """INSERT INTO inventory_expected_stock(
                         tenant_id,document_id,sku,barcode,expected_quantity,unit_cost
                       ) VALUES(%s,%s,%s,%s,%s,%s)""",
                    (principal.tenant_id, document_id, sku, barcode, product.get("expected", 0), product.get("cost", 0)),
                )
            readiness_snapshot: dict[str, Any] | None = None
            if count_mode == "WALL_TO_WALL":
                readiness_row = db.execute(
                    "SELECT inventory_wall_to_wall_readiness_v14(%s,%s) AS readiness",
                    (principal.tenant_id, document_id),
                ).fetchone()
                if not readiness_row or not readiness_row.get("readiness"):
                    raise RuntimeError("Wall-to-Wall readiness authority yanıt vermedi.")
                readiness_snapshot = dict(readiness_row["readiness"])
                if readiness_snapshot.get("status") not in {"READY", "BLOCKED"}:
                    raise InventoryRuleError("Wall-to-Wall kapsamı doğrulanamadı; sayım oluşturulmadı.")
            snapshot = canonical_payload_hash({
                "document_id": str(document_id), "warehouse_id": warehouse_id,
                "locations": locations, "sku_count": len(products), "count_mode": count_mode, "revision": 1,
            })
            db.execute(
                """INSERT INTO inventory_revisions(
                     tenant_id,document_id,revision,state,actor_subject,employee_id,reason,snapshot_hash
                   ) VALUES(%s,%s,1,'COUNTING',%s,%s,'document created',%s)""",
                (principal.tenant_id, document_id, principal.subject, principal.employee_id, snapshot),
            )
            _audit(db, principal, "DOCUMENT_CREATED", document_id, warehouse_id, {
                "location_count": len(locations),
                "sku_count": len(products),
                "count_mode": count_mode,
                "readiness_status": readiness_snapshot.get("status") if readiness_snapshot else "READY",
                "revision": 1,
            })
            db.commit()
            response: dict[str, Any] = {
                "id": str(document_id),
                "warehouse_id": warehouse_id,
                "state": "COUNTING",
                "revision": 1,
                "count_mode": count_mode,
            }
            if readiness_snapshot is not None:
                response["readiness"] = readiness_snapshot
            return response
        except Exception:
            db.rollback()
            raise


def _terminal_mission_id(tenant_id: str, document_id: UUID, location_id: str) -> str:
    location = str(location_id).strip().upper()
    digest = hashlib.sha256(f"{tenant_id}:{document_id}:{location}".encode("utf-8")).hexdigest()[:32]
    return f"inventory.count:{digest}"


def list_terminal_tasks(principal: InventoryPrincipal) -> list[dict[str, Any]]:
    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _assert_active_device(db, principal)
        rows = db.execute(
            """SELECT d.id,d.warehouse_id,d.name,d.state,d.revision,d.updated_at,d.count_mode,
                      l.location_id,
                      (SELECT count(*)::integer
                         FROM inventory_document_locations scope_l
                        WHERE scope_l.tenant_id=d.tenant_id
                          AND scope_l.document_id=d.id) AS location_count
               FROM inventory_documents d
               JOIN inventory_document_locations l
                 ON l.tenant_id=d.tenant_id AND l.document_id=d.id
               WHERE d.tenant_id=%s
                 AND d.state='COUNTING'
                 AND d.warehouse_id=ANY(%s)
                 AND (
                   d.count_mode<>'WALL_TO_WALL'
                   OR inventory_wall_to_wall_readiness_v14(d.tenant_id,d.id)->>'status'='READY'
                 )
                 AND NOT (
                   d.count_mode='WALL_TO_WALL'
                   AND l.location_id='LOST_FOUND'
                   AND EXISTS (
                     SELECT 1
                       FROM inventory_document_locations standard_l
                      WHERE standard_l.tenant_id=d.tenant_id
                        AND standard_l.document_id=d.id
                        AND standard_l.location_kind='STANDARD'
                        AND standard_l.completed_event_id IS NULL
                   )
                 )
               ORDER BY d.updated_at DESC,l.location_id""",
            (principal.tenant_id, list(principal.warehouse_scope)),
        ).fetchall()
    tasks: list[dict[str, Any]] = []
    for row in rows:
        task = dict(row)
        location_id = str(task["location_id"]).strip().upper()
        task["location_id"] = location_id
        task["mission_id"] = _terminal_mission_id(principal.tenant_id, task["id"], location_id)
        task["operation"] = "inventory.count"
        task["runtime_profile"] = "EAY_TERMINAL"
        tasks.append(task)
    # Expected quantities, costs, SKU universe, readiness blockers and variance
    # never cross this terminal boundary. W2W BLOCKED/UNKNOWN documents are hidden.
    return tasks


def reconciliation(principal: InventoryPrincipal, document_id: UUID) -> dict[str, Any]:
    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        document = db.execute(
            "SELECT warehouse_id,state,revision FROM inventory_documents WHERE tenant_id=%s AND id=%s",
            (principal.tenant_id, document_id),
        ).fetchone()
        if not document or document["warehouse_id"] not in principal.warehouse_scope:
            raise PermissionError("Sayım bulunamadı veya depo kapsamı dışında.")
        rows = db.execute(
            """WITH versioned AS (
                 SELECT *,row_number() OVER (
                   PARTITION BY attempt_id,location_id,barcode
                   ORDER BY count_version DESC
                 ) AS count_version_rank
                 FROM inventory_events
                 WHERE tenant_id=%s AND document_id=%s
                   AND event_type IN ('SCAN','UNEXPECTED_SKU','RECOUNT')
                   AND barcode IS NOT NULL
               ), counted AS (
                 SELECT barcode,sum(quantity) AS counted_quantity
                 FROM versioned WHERE count_version_rank=1
                 GROUP BY barcode
               )
               SELECT COALESCE(s.sku,'UNEXPECTED') AS sku,COALESCE(s.barcode,c.barcode) AS barcode,
                      COALESCE(s.expected_quantity,0) AS expected_quantity,
                      COALESCE(c.counted_quantity,0) AS counted_quantity,
                      COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0) AS variance,
                      (COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0))*COALESCE(s.unit_cost,0) AS variance_value
               FROM inventory_expected_stock s
               FULL OUTER JOIN counted c ON c.barcode=s.barcode
               WHERE (s.tenant_id=%s AND s.document_id=%s) OR s.document_id IS NULL
               ORDER BY abs(COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0)) DESC""",
            (principal.tenant_id, document_id, principal.tenant_id, document_id),
        ).fetchall()
        revisions = db.execute(
            """SELECT revision,state,actor_subject,employee_id,reason,snapshot_hash,created_at
               FROM inventory_revisions WHERE tenant_id=%s AND document_id=%s ORDER BY revision""",
            (principal.tenant_id, document_id),
        ).fetchall()
    return {"document": dict(document), "rows": [dict(row) for row in rows], "revisions": [dict(row) for row in revisions]}


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
    active_shift_id = str(payload["active_shift_id"]).strip()
    claimed_hash = str(payload["payload_hash"])
    hash_input = terminal_event_hash_input(payload)
    actual_hash = canonical_payload_hash(hash_input)
    if claimed_hash != actual_hash:
        raise InventoryRuleError("Event payload hash doğrulaması başarısız.")
    _redis_event_preflight(principal.tenant_id, event_id, actual_hash)
    occurred_at = datetime.fromisoformat(str(payload["occurred_at"]).replace("Z", "+00:00"))
    if occurred_at.tzinfo is None:
        raise InventoryRuleError("Event zamanı timezone içermelidir.")

    with connect() as db:
        try:
            db.execute("SET TRANSACTION ISOLATION LEVEL READ COMMITTED")
            _assert_runtime_tenant(db, principal)
            db.execute("SELECT pg_advisory_xact_lock(%s)", (_advisory_key(f"event:{principal.tenant_id}:{event_id}"),))
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
                db, principal, actual_hash, request_timestamp, request_nonce, request_signature,
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
                     payload_hash,occurred_at
                   ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    principal.tenant_id, event_id, principal.device_id, int(payload["device_sequence"]),
                    document_id, document["warehouse_id"], principal.employee_id, event_type,
                    location, barcode, payload["quantity"], payload["symbology"], actual_hash, occurred_at,
                ),
            )
            response = {
                "event_id": str(event_id),
                "accepted": True,
                "event_type": event_type,
                "document_revision": document["revision"],
                "active_shift_id": shift_attestation.shift_id,
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


def _assert_all_locations_completed(db: Any, tenant_id: str, document_id: UUID) -> None:
    status = db.execute(
        """SELECT
             (SELECT count(*)::integer
                FROM inventory_document_locations
               WHERE tenant_id=%s AND document_id=%s) AS required_location_count,
             (SELECT count(DISTINCT location_id)::integer
                FROM inventory_events
               WHERE tenant_id=%s AND document_id=%s
                 AND event_type='LOCATION_COMPLETE') AS completed_location_count""",
        (tenant_id, document_id, tenant_id, document_id),
    ).fetchone()
    if not status:
        raise InventoryRuleError("Sayım lokasyon tamamlama kanıtı okunamadı.")
    required_location_count = int(status["required_location_count"])
    completed_location_count = int(status["completed_location_count"])
    if required_location_count <= 0:
        raise InventoryRuleError("Lokasyonsuz sayım gönderilemez.")
    if completed_location_count != required_location_count:
        raise InventoryRuleError(
            "Tüm sayım lokasyonları server tarafından tamamlanmadan sayım gönderilemez."
        )


def transition(
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
                _assert_all_locations_completed(db, principal.tenant_id, document_id)
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
                "document_id": str(document_id), "from": row["state"], "to": target_state,
                "revision": next_revision, "reason": reason,
            })
            db.execute(
                """INSERT INTO inventory_revisions(
                     tenant_id,document_id,revision,state,actor_subject,employee_id,reason,snapshot_hash
                   ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)""",
                (principal.tenant_id, document_id, next_revision, target_state, principal.subject, principal.employee_id, reason, snapshot),
            )
            _audit(db, principal, "DOCUMENT_STATE_CHANGED", document_id, row["warehouse_id"], {
                "from": row["state"], "to": target_state, "revision": next_revision, "reason": reason,
            })
            db.commit()
            return {"document_id": str(document_id), "state": target_state, "revision": next_revision}
        except Exception:
            db.rollback()
            raise
