"""PostgreSQL authority for physical inventory workflows; never an in-memory reducer."""
from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any
from uuid import UUID, uuid4

from ..workforce.active_shift import ActiveShiftAuthorityError, attest_shift_at_event
from .production import InventoryPrincipal, _advisory_key, _assert_active_device, _assert_runtime_tenant, _audit, _verify_device_proof, canonical_payload_hash, connect
from .service import InventoryRuleError

DEFINITIONS = {
    "PICKING": ("inventory.pick.capture", ["SOURCE_LOCATION","ITEM","QUANTITY","CONTAINER","COMPLETE"]),
    "PUTAWAY": ("inventory.putaway.capture", ["ITEM","QUANTITY","DESTINATION_LOCATION","COMPLETE"]),
    "RECEIVING": ("inventory.receiving.capture", ["CONTAINER","ITEM","QUANTITY","CONDITION","COMPLETE"]),
    "TRANSFER": ("inventory.transfer.capture", ["SOURCE_LOCATION","ITEM","QUANTITY","DESTINATION_LOCATION","COMPLETE"]),
}

def event_hash_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {k: payload[k] for k in ("event_id","mission_id","claim_id","active_shift_id","device_sequence","step_kind","value_hash","occurred_at")}

def create_operational_mission(principal: InventoryPrincipal, payload: dict[str, Any]) -> dict[str, Any]:
    principal.validate(); kind = payload["mission_type"].upper()
    if kind not in DEFINITIONS: raise InventoryRuleError("Desteklenmeyen operasyon mission tipi.")
    warehouse = payload["warehouse_id"].strip()
    if warehouse not in principal.warehouse_scope: raise PermissionError("Mission deposu kimlik kapsamında değil.")
    operation, steps = DEFINITIONS[kind]; mission_id = uuid4()
    with connect() as db:
        _assert_runtime_tenant(db, principal); _assert_active_device(db, principal)
        db.execute("""INSERT INTO inventory_operational_missions(tenant_id,mission_id,warehouse_id,mission_type,operation,external_reference,steps,created_by) VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb,%s)""",(principal.tenant_id,mission_id,warehouse,kind,operation,payload["external_reference"].strip(),json.dumps(steps),principal.subject))
        db.commit()
    return {"mission_id":str(mission_id),"mission_type":kind,"operation":operation,"steps":steps,"state":"OPEN"}

def claim_operational_mission(principal: InventoryPrincipal, mission_id: UUID, shift_id: str) -> dict[str, Any]:
    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal); _assert_active_device(db, principal); db.execute("SELECT pg_advisory_xact_lock(%s)",(_advisory_key(f"operational:{principal.tenant_id}:{mission_id}"),))
        mission=db.execute("SELECT * FROM inventory_operational_missions WHERE tenant_id=%s AND mission_id=%s FOR UPDATE",(principal.tenant_id,mission_id)).fetchone()
        if not mission or mission["warehouse_id"] not in principal.warehouse_scope: raise PermissionError("Mission bulunamadı veya depo kapsamı dışında.")
        live=db.execute("SELECT * FROM inventory_operational_claims WHERE tenant_id=%s AND mission_id=%s AND released_at IS NULL",(principal.tenant_id,mission_id)).fetchone()
        if live:
            if live["employee_id"]==principal.employee_id and live["device_id"]==principal.device_id and live["shift_id"]==shift_id:
                progress=db.execute("SELECT count(*) AS n FROM inventory_operational_events WHERE tenant_id=%s AND mission_id=%s",(principal.tenant_id,mission_id)).fetchone()["n"]
                next_step=mission["steps"][progress] if progress < len(mission["steps"]) else None
                return {"mission_id":str(mission_id),"claim_id":str(live["claim_id"]),"state":mission["state"],"next_step":next_step}
            raise InventoryRuleError("Mission başka aktör, cihaz veya vardiya tarafından claim edilmiş.")
        if mission["state"] != "OPEN": raise InventoryRuleError("Mission claim edilebilir durumda değil.")
        claim_id=uuid4(); db.execute("INSERT INTO inventory_operational_claims(tenant_id,claim_id,mission_id,employee_id,device_id,shift_id) VALUES(%s,%s,%s,%s,%s,%s)",(principal.tenant_id,claim_id,mission_id,principal.employee_id,principal.device_id,shift_id)); db.execute("UPDATE inventory_operational_missions SET state='CLAIMED' WHERE tenant_id=%s AND mission_id=%s",(principal.tenant_id,mission_id)); _audit(db,principal,"OPERATIONAL_MISSION_CLAIMED",None,mission["warehouse_id"],{"mission_id":str(mission_id),"claim_id":str(claim_id),"shift_id":shift_id}); db.commit()
        return {"mission_id":str(mission_id),"claim_id":str(claim_id),"state":"CLAIMED","next_step":mission["steps"][0]}

def record_operational_event(principal: InventoryPrincipal,payload:dict[str,Any],timestamp:str,nonce:str,signature:str)->dict[str,Any]:
    principal.validate(); canonical=event_hash_input(payload); calculated=canonical_payload_hash(canonical)
    if calculated != payload["payload_hash"]: raise InventoryRuleError("Operational event payload hash eşleşmiyor.")
    try:
        event_id=UUID(payload["event_id"]); mission_id=UUID(payload["mission_id"]); claim_id=UUID(payload["claim_id"])
        occurred=datetime.fromisoformat(payload["occurred_at"].replace("Z","+00:00"))
    except (TypeError, ValueError) as error:
        raise InventoryRuleError("Operational event UUID veya zamanı geçersiz.") from error
    if occurred.tzinfo is None:
        raise InventoryRuleError("Operational event zamanı timezone içermelidir.")
    occurred=occurred.astimezone(UTC); shift=payload["active_shift_id"].strip()
    with connect() as db:
        _assert_runtime_tenant(db,principal); _verify_device_proof(db,principal,calculated,timestamp,nonce,signature)
        db.execute("SELECT pg_advisory_xact_lock(%s)",(_advisory_key(f"operational:{principal.tenant_id}:{mission_id}"),))
        old=db.execute("SELECT e.payload_hash,r.response FROM inventory_operational_events e JOIN inventory_operational_event_responses r USING(tenant_id,event_id) WHERE e.tenant_id=%s AND e.event_id=%s",(principal.tenant_id,event_id)).fetchone()
        if old:
            if old["payload_hash"]!=calculated: raise InventoryRuleError("Event ID farklı payload ile tekrar kullanılamaz.")
            db.commit(); return old["response"]
        row=db.execute("""SELECT m.*,c.employee_id,c.device_id,c.shift_id,c.released_at FROM inventory_operational_missions m JOIN inventory_operational_claims c ON c.tenant_id=m.tenant_id AND c.mission_id=m.mission_id WHERE m.tenant_id=%s AND m.mission_id=%s AND c.claim_id=%s FOR UPDATE OF m,c""",(principal.tenant_id,mission_id,claim_id)).fetchone()
        if not row or row["released_at"] is not None or row["employee_id"]!=principal.employee_id or row["device_id"]!=principal.device_id or row["shift_id"]!=shift: raise PermissionError("Mission claim aktör/cihaz/vardiya bağı geçersiz.")
        try:
            shift_attestation=attest_shift_at_event(principal.tenant_id,principal.employee_id,row["warehouse_id"],shift,payload["occurred_at"])
        except ActiveShiftAuthorityError as error:
            raise RuntimeError("Workforce event vardiya authority kullanılamıyor.") from error
        if shift_attestation is None:
            raise PermissionError("Operational event aktif vardiya penceresi dışında üretildi.")
        prior=db.execute("SELECT count(*) AS n FROM inventory_operational_events WHERE tenant_id=%s AND mission_id=%s",(principal.tenant_id,mission_id)).fetchone()["n"]
        steps=row["steps"]; expected=steps[prior] if prior < len(steps) else None
        if expected is None: raise InventoryRuleError("Mission zaten tamamlanmış.")
        if payload["step_kind"] != expected: raise InventoryRuleError(f"Sıradaki adım {expected} olmalıdır.")
        db.execute("""INSERT INTO inventory_operational_events(tenant_id,event_id,mission_id,claim_id,employee_id,device_id,shift_id,device_sequence,step_index,step_kind,value_hash,payload_hash,occurred_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(principal.tenant_id,event_id,mission_id,claim_id,principal.employee_id,principal.device_id,shift,payload["device_sequence"],prior,expected,payload["value_hash"],calculated,occurred))
        completed=expected=="COMPLETE"; response={"event_id":str(event_id),"code":"ACCEPTED","mission_id":str(mission_id),"completed":completed,"next_step":None if completed else steps[prior+1]}
        db.execute("INSERT INTO inventory_operational_event_responses VALUES(%s,%s,%s::jsonb,now())",(principal.tenant_id,event_id,json.dumps(response)))
        db.execute("INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload) VALUES(%s,%s,%s,%s,%s::jsonb)",(principal.tenant_id,uuid4(),mission_id,"INVENTORY_OPERATIONAL_STEP_ACCEPTED",json.dumps({**response,"step_kind":expected,"employee_id":principal.employee_id,"device_id":str(principal.device_id),"shift_id":shift})))
        _audit(db,principal,"OPERATIONAL_STEP_ACCEPTED",None,row["warehouse_id"],{"mission_id":str(mission_id),"claim_id":str(claim_id),"event_id":str(event_id),"step_kind":expected,"step_index":prior,"completed":completed})
        if completed:
            db.execute("UPDATE inventory_operational_missions SET state='COMPLETED',completed_at=now() WHERE tenant_id=%s AND mission_id=%s",(principal.tenant_id,mission_id)); db.execute("UPDATE inventory_operational_claims SET released_at=now() WHERE tenant_id=%s AND claim_id=%s",(principal.tenant_id,claim_id))
        db.commit(); return response
