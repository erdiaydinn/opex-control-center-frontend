"""Governed recovery for stranded operational mission claims."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from .production import (
    InventoryPrincipal,
    _advisory_key,
    _assert_runtime_tenant,
    _audit,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)
from .service import InventoryRuleError


def operational_release_hash(mission_id: str | UUID, reason: str) -> str:
    normalized_reason = str(reason).strip()
    if len(normalized_reason) < 3 or len(normalized_reason) > 500:
        raise InventoryRuleError("Operational release nedeni 3-500 karakter olmalıdır.")
    return canonical_payload_hash(
        {
            "mission_id": str(UUID(str(mission_id))),
            "reason": normalized_reason,
        }
    )


def release_operational_claim(
    principal: InventoryPrincipal,
    mission_id: str | UUID,
    reason: str,
    timestamp: str,
    nonce: str,
    signature: str,
) -> dict:
    """Release one live claim without rewriting any previously accepted step evidence."""

    principal.validate()
    mission_uuid = UUID(str(mission_id))
    normalized_reason = str(reason).strip()
    command_hash = operational_release_hash(mission_uuid, normalized_reason)

    with connect() as db:
        try:
            _assert_runtime_tenant(db, principal)
            _verify_device_proof(db, principal, command_hash, timestamp, nonce, signature)
            db.execute(
                "SELECT pg_advisory_xact_lock(%s)",
                (_advisory_key(f"operational:{principal.tenant_id}:{mission_uuid}"),),
            )
            mission = db.execute(
                """SELECT mission_id,warehouse_id,state,completed_at
                   FROM inventory_operational_missions
                   WHERE tenant_id=%s AND mission_id=%s
                   FOR UPDATE""",
                (principal.tenant_id, mission_uuid),
            ).fetchone()
            if not mission or mission["warehouse_id"] not in principal.warehouse_scope:
                raise PermissionError("Operational mission bulunamadı veya depo kapsamı dışında.")
            if mission["completed_at"] is not None or mission["state"] == "COMPLETED":
                raise InventoryRuleError("Tamamlanmış operational mission release edilemez.")

            live = db.execute(
                """SELECT claim_id,employee_id,device_id,shift_id
                   FROM inventory_operational_claims
                   WHERE tenant_id=%s AND mission_id=%s AND released_at IS NULL
                   FOR UPDATE""",
                (principal.tenant_id, mission_uuid),
            ).fetchone()
            if not live:
                if mission["state"] == "OPEN":
                    db.commit()
                    return {
                        "mission_id": str(mission_uuid),
                        "state": "OPEN",
                        "idempotent": True,
                        "evidence_policy": "PRESERVE_NO_REBIND",
                    }
                raise InventoryRuleError("Mission state ile live claim authority tutarsız.")

            if str(live["employee_id"]) == principal.employee_id:
                raise InventoryRuleError(
                    "Claim sahibi kendi operational claim'ini supervisor release ile kapatamaz."
                )

            release_reason = f"SUPERVISOR:{normalized_reason}"
            db.execute(
                """UPDATE inventory_operational_claims
                   SET released_at=now(),release_reason=%s
                   WHERE tenant_id=%s AND claim_id=%s AND released_at IS NULL""",
                (release_reason, principal.tenant_id, live["claim_id"]),
            )
            db.execute(
                """UPDATE inventory_operational_missions
                   SET state='OPEN'
                   WHERE tenant_id=%s AND mission_id=%s AND state='CLAIMED'""",
                (principal.tenant_id, mission_uuid),
            )

            record = {
                "mission_id": str(mission_uuid),
                "released_claim_id": str(live["claim_id"]),
                "released_employee_id": str(live["employee_id"]),
                "released_device_id": str(live["device_id"]),
                "released_shift_id": str(live["shift_id"]),
                "reason": normalized_reason,
                "evidence_policy": "PRESERVE_NO_REBIND",
            }
            _audit(
                db,
                principal,
                "OPERATIONAL_CLAIM_SUPERVISOR_RELEASED",
                None,
                mission["warehouse_id"],
                record,
            )
            db.execute(
                """INSERT INTO inventory_outbox(tenant_id,id,aggregate_id,event_type,payload)
                   VALUES(%s,%s,%s,'OPERATIONAL_CLAIM_SUPERVISOR_RELEASED',%s::jsonb)""",
                (
                    principal.tenant_id,
                    uuid4(),
                    mission_uuid,
                    json.dumps(record, sort_keys=True),
                ),
            )
            db.commit()
            return {
                "mission_id": str(mission_uuid),
                "released_claim_id": str(live["claim_id"]),
                "state": "OPEN",
                "idempotent": False,
                "evidence_policy": "PRESERVE_NO_REBIND",
            }
        except Exception:
            db.rollback()
            raise
