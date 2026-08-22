"""PostgreSQL authority for physical inventory workflows; never an in-memory reducer."""
from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
import json
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_active_device,
    _assert_runtime_tenant,
    _audit,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)
from .service import InventoryRuleError

DEFINITIONS = {
    "PICKING": ("inventory.pick.capture", ["SOURCE_LOCATION", "ITEM", "QUANTITY", "CONTAINER", "COMPLETE"]),
    "PUTAWAY": ("inventory.putaway.capture", ["ITEM", "QUANTITY", "DESTINATION_LOCATION", "COMPLETE"]),
    "RECEIVING": ("inventory.receiving.capture", ["CONTAINER", "ITEM", "QUANTITY", "CONDITION", "COMPLETE"]),
    "TRANSFER": ("inventory.transfer.capture", ["SOURCE_LOCATION", "ITEM", "QUANTITY", "DESTINATION_LOCATION", "COMPLETE"]),
}

CODE_STEPS = {"SOURCE_LOCATION", "DESTINATION_LOCATION", "CONDITION", "CONTAINER", "COMPLETE"}
MAX_OPERATIONAL_QUANTITY = Decimal("1000000")
MISSION_PRIORITIES = {"LOW", "NORMAL", "HIGH", "URGENT"}
MAX_ESTIMATED_SECONDS = 86_400


def _decimal_text(value: Any) -> str:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise InventoryRuleError("Operasyon miktarı geçersiz.") from error
    if not number.is_finite() or number < 0 or number > MAX_OPERATIONAL_QUANTITY:
        raise InventoryRuleError("Operasyon miktarı geçersiz.")
    if number == 0:
        return "0"
    return format(number.normalize(), "f")


def normalize_operational_value(step_kind: str, value: Any) -> str:
    kind = str(step_kind).strip().upper()
    if kind not in {step for _, steps in DEFINITIONS.values() for step in steps}:
        raise InventoryRuleError("Desteklenmeyen operasyon adımı.")
    raw = str(value).strip()
    if not raw:
        raise InventoryRuleError("Operasyon adım değeri boş olamaz.")
    if kind == "QUANTITY":
        return _decimal_text(raw)
    if kind in CODE_STEPS:
        normalized = raw.upper()
        if kind == "COMPLETE" and normalized != "COMPLETE":
            raise InventoryRuleError("Mission yalnız COMPLETE kanıtı ile tamamlanabilir.")
        return normalized
    # ITEM remains the scanner-presented identity. It is hash-bound and never
    # persisted or returned in raw form.
    return raw


def _length_prefixed(value: str) -> str:
    return f"{len(value.encode('utf-8'))}:{value}"


def operational_value_hash(step_kind: str, value: Any) -> str:
    kind = str(step_kind).strip().upper()
    normalized = normalize_operational_value(kind, value)
    material = _length_prefixed(kind) + _length_prefixed(normalized)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def event_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        k: payload[k]
        for k in (
            "event_id",
            "mission_id",
            "claim_id",
            "active_shift_id",
            "device_sequence",
            "step_kind",
            "value_hash",
            "occurred_at",
        )
    }


def _optional_code(payload: dict[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    normalized = str(value).strip().upper()
    return normalized or None


def _service_level(payload: dict[str, Any]) -> dict[str, Any]:
    priority = str(payload.get("priority") or "NORMAL").strip().upper()
    if priority not in MISSION_PRIORITIES:
        raise InventoryRuleError("Operasyon mission priority geçersiz.")

    due_at: datetime | None = None
    raw_due = payload.get("due_at")
    if raw_due is not None:
        try:
            due_at = datetime.fromisoformat(str(raw_due).replace("Z", "+00:00"))
        except (TypeError, ValueError) as error:
            raise InventoryRuleError("Operasyon SLA zamanı geçersiz.") from error
        if due_at.tzinfo is None:
            raise InventoryRuleError("Operasyon SLA zamanı timezone içermelidir.")
        due_at = due_at.astimezone(UTC)
        if due_at <= datetime.now(UTC):
            raise InventoryRuleError("Yeni operasyon mission SLA zamanı gelecekte olmalıdır.")

    estimated_seconds: int | None = None
    raw_estimate = payload.get("estimated_seconds")
    if raw_estimate is not None:
        try:
            estimated_seconds = int(raw_estimate)
        except (TypeError, ValueError) as error:
            raise InventoryRuleError("Operasyon tahmini süresi geçersiz.") from error
        if estimated_seconds < 1 or estimated_seconds > MAX_ESTIMATED_SECONDS:
            raise InventoryRuleError("Operasyon tahmini süresi geçersiz.")

    return {
        "priority": priority,
        "due_at": due_at,
        "estimated_seconds": estimated_seconds,
    }


def build_operational_intent(kind: str, payload: dict[str, Any]) -> dict[str, Any]:
    mission_type = kind.strip().upper()
    sku_id = str(payload.get("sku_id", "")).strip()
    item_barcode = str(payload.get("item_barcode", "")).strip()
    if not sku_id or not item_barcode:
        raise InventoryRuleError("Server-frozen SKU ve taranabilir ürün kimliği zorunludur.")

    planned_text = _decimal_text(payload.get("planned_quantity"))
    if Decimal(planned_text) <= 0:
        raise InventoryRuleError("Planlanan operasyon miktarı sıfırdan büyük olmalıdır.")

    source = _optional_code(payload, "source_location_id")
    destination = _optional_code(payload, "destination_location_id")
    container = _optional_code(payload, "container_id")
    conditions: list[str] = []
    if mission_type == "RECEIVING":
        conditions = sorted(
            {
                str(value).strip().upper()
                for value in (payload.get("allowed_conditions") or [])
                if str(value).strip()
            }
        )
        if not conditions:
            raise InventoryRuleError("En az bir receiving condition kodu zorunludur.")

    if mission_type == "PICKING" and (not source or not container):
        raise InventoryRuleError("Picking source location ve container authority gerektirir.")
    if mission_type == "PUTAWAY" and not destination:
        raise InventoryRuleError("Putaway destination location authority gerektirir.")
    if mission_type == "RECEIVING" and not container:
        raise InventoryRuleError("Receiving container authority gerektirir.")
    if mission_type == "TRANSFER":
        if not source or not destination:
            raise InventoryRuleError("Transfer source ve destination authority gerektirir.")
        if source == destination:
            raise InventoryRuleError("Transfer source ve destination aynı olamaz.")

    return {
        "intent_version": 1,
        "sku_id": sku_id,
        "item_value_hash": operational_value_hash("ITEM", item_barcode),
        "planned_quantity": Decimal(planned_text),
        "source_location_id": source,
        "destination_location_id": destination,
        "container_id": container,
        "allowed_conditions": conditions,
    }


def create_operational_mission(principal: InventoryPrincipal, payload: dict[str, Any]) -> dict[str, Any]:
    principal.validate()
    kind = payload["mission_type"].upper()
    if kind not in DEFINITIONS:
        raise InventoryRuleError("Desteklenmeyen operasyon mission tipi.")
    warehouse = payload["warehouse_id"].strip()
    if warehouse not in principal.warehouse_scope:
        raise PermissionError("Mission deposu kimlik kapsamında değil.")
    operation, steps = DEFINITIONS[kind]
    intent = build_operational_intent(kind, payload)
    service = _service_level(payload)
    mission_id = uuid4()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _assert_active_device(db, principal)
        db.execute(
            """INSERT INTO inventory_operational_missions(
                 tenant_id,mission_id,warehouse_id,mission_type,operation,external_reference,steps,created_by,
                 intent_version,sku_id,item_value_hash,planned_quantity,source_location_id,
                 destination_location_id,container_id,allowed_conditions,priority,due_at,estimated_seconds
               ) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)""",
            (
                principal.tenant_id,
                mission_id,
                warehouse,
                kind,
                operation,
                payload["external_reference"].strip(),
                json.dumps(steps),
                principal.subject,
                intent["intent_version"],
                intent["sku_id"],
                intent["item_value_hash"],
                intent["planned_quantity"],
                intent["source_location_id"],
                intent["destination_location_id"],
                intent["container_id"],
                json.dumps(intent["allowed_conditions"]),
                service["priority"],
                service["due_at"],
                service["estimated_seconds"],
            ),
        )
        db.commit()
    return {
        "mission_id": str(mission_id),
        "mission_type": kind,
        "operation": operation,
        "steps": steps,
        "state": "OPEN",
        "service": {
            "priority": service["priority"],
            "due_at": service["due_at"].isoformat().replace("+00:00", "Z") if service["due_at"] else None,
            "estimated_seconds": service["estimated_seconds"],
        },
        "intent": {
            "sku_id": intent["sku_id"],
            "planned_quantity": _decimal_text(intent["planned_quantity"]),
            "source_location_id": intent["source_location_id"],
            "destination_location_id": intent["destination_location_id"],
            "container_id": intent["container_id"],
            "allowed_conditions": intent["allowed_conditions"],
        },
    }


def claim_operational_mission(principal: InventoryPrincipal, mission_id: UUID, shift_id: str) -> dict[str, Any]:
    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _assert_active_device(db, principal)
        db.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_advisory_key(f"operational:{principal.tenant_id}:{mission_id}"),),
        )
        mission = db.execute(
            "SELECT * FROM inventory_operational_missions WHERE tenant_id=%s AND mission_id=%s FOR UPDATE",
            (principal.tenant_id, mission_id),
        ).fetchone()
        if not mission or mission["warehouse_id"] not in principal.warehouse_scope:
            raise PermissionError("Mission bulunamadı veya depo kapsamı dışında.")
        if int(mission.get("intent_version") or 0) != 1:
            raise InventoryRuleError("Legacy operational mission yeni terminal tarafından claim edilemez.")
        live = db.execute(
            """SELECT * FROM inventory_operational_claims
               WHERE tenant_id=%s AND mission_id=%s AND released_at IS NULL""",
            (principal.tenant_id, mission_id),
        ).fetchone()
        if live:
            if (
                live["employee_id"] == principal.employee_id
                and live["device_id"] == principal.device_id
                and live["shift_id"] == shift_id
            ):
                progress = db.execute(
                    "SELECT count(*) AS n FROM inventory_operational_events WHERE tenant_id=%s AND mission_id=%s",
                    (principal.tenant_id, mission_id),
                ).fetchone()["n"]
                next_step = mission["steps"][progress] if progress < len(mission["steps"]) else None
                return {
                    "mission_id": str(mission_id),
                    "claim_id": str(live["claim_id"]),
                    "state": mission["state"],
                    "next_step": next_step,
                }
            raise InventoryRuleError("Mission başka aktör, cihaz veya vardiya tarafından claim edilmiş.")
        if mission["state"] != "OPEN":
            raise InventoryRuleError("Mission claim edilebilir durumda değil.")
        claim_id = uuid4()
        db.execute(
            """INSERT INTO inventory_operational_claims(
                 tenant_id,claim_id,mission_id,employee_id,device_id,shift_id
               ) VALUES(%s,%s,%s,%s,%s,%s)""",
            (
                principal.tenant_id,
                claim_id,
                mission_id,
                principal.employee_id,
                principal.device_id,
                shift_id,
            ),
        )
        db.execute(
            "UPDATE inventory_operational_missions SET state='CLAIMED' WHERE tenant_id=%s AND mission_id=%s",
            (principal.tenant_id, mission_id),
        )
        _audit(
            db,
            principal,
            "OPERATIONAL_MISSION_CLAIMED",
            None,
            mission["warehouse_id"],
            {"mission_id": str(mission_id), "claim_id": str(claim_id), "shift_id": shift_id},
        )
        db.commit()
        return {
            "mission_id": str(mission_id),
            "claim_id": str(claim_id),
            "state": "CLAIMED",
            "next_step": mission["steps"][0],
        }


def _safe_business_fact(row: dict[str, Any], step_kind: str, normalized: str) -> tuple[str | None, Decimal | None]:
    if int(row.get("intent_version") or 0) != 1:
        raise InventoryRuleError("Operational mission intent authority eksik.")
    if step_kind == "ITEM":
        if operational_value_hash("ITEM", normalized) != row["item_value_hash"]:
            raise InventoryRuleError("Okutulan ürün server-frozen SKU mission kimliğiyle eşleşmiyor.")
        return str(row["sku_id"]), None
    if step_kind == "QUANTITY":
        return None, Decimal(normalized)
    if step_kind == "SOURCE_LOCATION":
        if normalized != row["source_location_id"]:
            raise InventoryRuleError("Source location mission intent ile eşleşmiyor.")
        return normalized, None
    if step_kind == "DESTINATION_LOCATION":
        if normalized != row["destination_location_id"]:
            raise InventoryRuleError("Destination location mission intent ile eşleşmiyor.")
        return normalized, None
    if step_kind == "CONTAINER":
        if normalized != row["container_id"]:
            raise InventoryRuleError("Container mission intent ile eşleşmiyor.")
        return normalized, None
    if step_kind == "CONDITION":
        allowed = {str(value).upper() for value in (row["allowed_conditions"] or [])}
        if normalized not in allowed:
            raise InventoryRuleError("Receiving condition mission policy kapsamında değil.")
        return normalized, None
    if step_kind == "COMPLETE":
        if normalized != "COMPLETE":
            raise InventoryRuleError("Mission tamamlanma kanıtı geçersiz.")
        return "COMPLETE", None
    raise InventoryRuleError("Desteklenmeyen operasyon adımı.")


def _result_from_facts(row: dict[str, Any], facts: list[dict[str, Any]]) -> dict[str, Any]:
    by_kind = {fact["step_kind"]: fact for fact in facts}
    quantity = by_kind.get("QUANTITY", {}).get("numeric_value")
    if quantity is None:
        raise InventoryRuleError("Operational result için quantity evidence eksik.")
    actual = Decimal(str(quantity))
    condition = by_kind.get("CONDITION", {}).get("safe_value")
    planned = Decimal(str(row["planned_quantity"]))
    exact_quantity = actual == planned
    acceptable_condition = condition in (None, "GOOD")
    reconciliation_state = "AUTO_RECONCILED" if exact_quantity and acceptable_condition else "REVIEW_REQUIRED"
    result = {
        "mission_id": str(row["mission_id"]),
        "mission_type": row["mission_type"],
        "sku_id": row["sku_id"],
        "planned_quantity": _decimal_text(planned),
        "actual_quantity": _decimal_text(actual),
        "source_location_id": row["source_location_id"],
        "destination_location_id": row["destination_location_id"],
        "container_id": row["container_id"],
        "condition_code": condition,
        "reconciliation_state": reconciliation_state,
    }
    return {**result, "result_hash": canonical_payload_hash(result)}


def record_operational_event(
    principal: InventoryPrincipal,
    payload: dict[str, Any],
    timestamp: str,
    nonce: str,
    signature: str,
) -> dict[str, Any]:
    principal.validate()
    step_kind = str(payload["step_kind"]).strip().upper()
    normalized_value = normalize_operational_value(step_kind, payload["value"])
    calculated_value_hash = operational_value_hash(step_kind, normalized_value)
    if calculated_value_hash != payload["value_hash"]:
        raise InventoryRuleError("Operational step value hash eşleşmiyor.")
    canonical = event_hash_input(payload)
    calculated = canonical_payload_hash(canonical)
    if calculated != payload["payload_hash"]:
        raise InventoryRuleError("Operational event payload hash eşleşmiyor.")
    try:
        event_id = UUID(payload["event_id"])
        mission_id = UUID(payload["mission_id"])
        claim_id = UUID(payload["claim_id"])
        occurred = datetime.fromisoformat(payload["occurred_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError) as error:
        raise InventoryRuleError("Operational event UUID veya zamanı geçersiz.") from error
    if occurred.tzinfo is None:
        raise InventoryRuleError("Operational event zamanı timezone içermelidir.")
    occurred = occurred.astimezone(UTC)
    shift = payload["active_shift_id"].strip()

    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _verify_device_proof(db, principal, calculated, timestamp, nonce, signature)
        db.execute(
            "SELECT pg_advisory_xact_lock(%s)",
            (_advisory_key(f"operational:{principal.tenant_id}:{mission_id}"),),
        )
        old = db.execute(
            """SELECT e.payload_hash,e.employee_id,e.device_id,e.shift_id,
                      e.mission_id,e.claim_id,m.warehouse_id,r.response
               FROM inventory_operational_events e
               JOIN inventory_operational_event_responses r USING(tenant_id,event_id)
               JOIN inventory_operational_missions m
                 ON m.tenant_id=e.tenant_id AND m.mission_id=e.mission_id
               WHERE e.tenant_id=%s AND e.event_id=%s""",
            (principal.tenant_id, event_id),
        ).fetchone()
        if old:
            if old["payload_hash"] != calculated:
                raise InventoryRuleError("Event ID farklı payload ile tekrar kullanılamaz.")
            if (
                old["employee_id"] != principal.employee_id
                or old["device_id"] != principal.device_id
                or old["shift_id"] != shift
                or old["mission_id"] != mission_id
                or old["claim_id"] != claim_id
                or old["warehouse_id"] not in principal.warehouse_scope
            ):
                raise PermissionError("Operational replay aktör/cihaz/vardiya/mission bağı geçersiz.")
            replay = dict(old["response"])
            replay["idempotent_replay"] = True
            db.commit()
            return replay

        row = db.execute(
            """SELECT m.*,c.employee_id,c.device_id,c.shift_id,c.released_at
               FROM inventory_operational_missions m
               JOIN inventory_operational_claims c
                 ON c.tenant_id=m.tenant_id AND c.mission_id=m.mission_id
               WHERE m.tenant_id=%s AND m.mission_id=%s AND c.claim_id=%s
               FOR UPDATE OF m,c""",
            (principal.tenant_id, mission_id, claim_id),
        ).fetchone()
        if (
            not row
            or row["released_at"] is not None
            or row["employee_id"] != principal.employee_id
            or row["device_id"] != principal.device_id
            or row["shift_id"] != shift
        ):
            raise PermissionError("Mission claim aktör/cihaz/vardiya bağı geçersiz.")
        try:
            shift_attestation = attest_shift_at_event(
                principal.tenant_id,
                principal.employee_id,
                row["warehouse_id"],
                shift,
                payload["occurred_at"],
            )
        except ActiveShiftAuthorityError as error:
            raise RuntimeError("Workforce event vardiya authority kullanılamıyor.") from error
        if shift_attestation is None:
            raise PermissionError("Operational event aktif vardiya penceresi dışında üretildi.")

        prior = db.execute(
            "SELECT count(*) AS n FROM inventory_operational_events WHERE tenant_id=%s AND mission_id=%s",
            (principal.tenant_id, mission_id),
        ).fetchone()["n"]
        steps = row["steps"]
        expected = steps[prior] if prior < len(steps) else None
        if expected is None:
            raise InventoryRuleError("Mission zaten tamamlanmış.")
        if step_kind != expected:
            raise InventoryRuleError(f"Sıradaki adım {expected} olmalıdır.")

        safe_value, numeric_value = _safe_business_fact(row, expected, normalized_value)
        db.execute(
            """INSERT INTO inventory_operational_events(
                 tenant_id,event_id,mission_id,claim_id,employee_id,device_id,shift_id,
                 device_sequence,step_index,step_kind,value_hash,payload_hash,occurred_at,
                 contract_version,safe_value,numeric_value
               ) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s)""",
            (
                principal.tenant_id,
                event_id,
                mission_id,
                claim_id,
                principal.employee_id,
                principal.device_id,
                shift,
                payload["device_sequence"],
                prior,
                expected,
                calculated_value_hash,
                calculated,
                occurred,
                safe_value,
                numeric_value,
            ),
        )

        completed = expected == "COMPLETE"
        response: dict[str, Any] = {
            "event_id": str(event_id),
            "code": "ACCEPTED",
            "mission_id": str(mission_id),
            "completed": completed,
            "next_step": None if completed else steps[prior + 1],
            "idempotent_replay": False,
        }

        if completed:
            facts = db.execute(
                """SELECT step_kind,safe_value,numeric_value
                   FROM inventory_operational_events
                   WHERE tenant_id=%s AND mission_id=%s
                   ORDER BY step_index""",
                (principal.tenant_id, mission_id),
            ).fetchall()
            reconciliation = _result_from_facts(row, facts)
            response["reconciliation"] = reconciliation
            db.execute(
                """UPDATE inventory_operational_missions
                   SET state='COMPLETED',completed_at=now(),actual_quantity=%s,
                       condition_code=%s,reconciliation_state=%s,result_hash=%s,reconciled_at=now()
                   WHERE tenant_id=%s AND mission_id=%s""",
                (
                    Decimal(reconciliation["actual_quantity"]),
                    reconciliation["condition_code"],
                    reconciliation["reconciliation_state"],
                    reconciliation["result_hash"],
                    principal.tenant_id,
                    mission_id,
                ),
            )
            db.execute(
                "UPDATE inventory_operational_claims SET released_at=now() WHERE tenant_id=%s AND claim_id=%s",
                (principal.tenant_id, claim_id),
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'INVENTORY_OPERATIONAL_RESULT_RECONCILED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    mission_id,
                    json.dumps(reconciliation, sort_keys=True),
                ),
            )

        db.execute(
            "INSERT INTO inventory_operational_event_responses VALUES(%s,%s,%s::jsonb,now())",
            (principal.tenant_id, event_id, json.dumps(response, sort_keys=True)),
        )
        db.execute(
            """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
               VALUES(%s,%s,%s,%s,%s::jsonb)""",
            (
                principal.tenant_id,
                uuid4(),
                mission_id,
                "INVENTORY_OPERATIONAL_STEP_ACCEPTED",
                json.dumps(
                    {
                        "event_id": str(event_id),
                        "code": "ACCEPTED",
                        "mission_id": str(mission_id),
                        "completed": completed,
                        "next_step": response["next_step"],
                        "step_kind": expected,
                        "employee_id": principal.employee_id,
                        "device_id": str(principal.device_id),
                        "shift_id": shift,
                    },
                    sort_keys=True,
                ),
            ),
        )
        _audit(
            db,
            principal,
            "OPERATIONAL_STEP_ACCEPTED",
            None,
            row["warehouse_id"],
            {
                "mission_id": str(mission_id),
                "claim_id": str(claim_id),
                "event_id": str(event_id),
                "step_kind": expected,
                "step_index": prior,
                "completed": completed,
            },
        )
        db.commit()
        return response
