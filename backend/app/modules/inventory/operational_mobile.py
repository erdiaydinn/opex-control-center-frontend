"""Read-only mobile discovery projection for operational inventory missions."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from .operational_mission import DEFINITIONS, _decimal_text
from .production import (
    InventoryPrincipal,
    _assert_active_device,
    _assert_runtime_tenant,
    connect,
)


def _project_operational_mobile_row(
    row: dict[str, Any],
    principal: InventoryPrincipal,
    active_shift_id: str,
) -> dict[str, Any] | None:
    mission_type = str(row["mission_type"]).strip().upper()
    if mission_type not in DEFINITIONS:
        return None
    operation, canonical_steps = DEFINITIONS[mission_type]
    steps = [str(value).strip().upper() for value in (row.get("steps") or [])]
    if operation != row.get("operation") or steps != canonical_steps:
        return None

    state = str(row.get("state") or "").strip().upper()
    if state not in {"OPEN", "CLAIMED"}:
        return None

    live_employee = row.get("claim_employee_id")
    live_device = row.get("claim_device_id")
    live_shift = row.get("claim_shift_id")
    if state == "CLAIMED":
        if (
            live_employee != principal.employee_id
            or str(live_device) != str(principal.device_id)
            or live_shift != active_shift_id
        ):
            return None
        claim_status = "RESUMABLE"
    else:
        if live_employee is not None or live_device is not None or live_shift is not None:
            return None
        claim_status = "AVAILABLE"

    completed_steps = int(row.get("completed_steps") or 0)
    if completed_steps < 0 or completed_steps >= len(steps):
        return None
    next_step = steps[completed_steps]

    planned = Decimal(str(row["planned_quantity"]))
    stored_conditions = [
        str(value).strip().upper()
        for value in (row.get("allowed_conditions") or [])
        if str(value).strip()
    ]
    # Conditions are executable mission guidance only for RECEIVING. Historical
    # rows may carry the old default GOOD value for other mission types; never
    # project that irrelevant field into a terminal contract that cannot execute it.
    allowed_conditions = stored_conditions if "CONDITION" in canonical_steps else []
    if "CONDITION" in canonical_steps and not allowed_conditions:
        return None

    return {
        "mission_id": str(row["mission_id"]),
        "warehouse_id": str(row["warehouse_id"]),
        "mission_type": mission_type,
        "operation": operation,
        "external_reference": str(row["external_reference"]),
        "state": state,
        "steps": steps,
        "completed_steps": completed_steps,
        "total_steps": len(steps),
        "next_step": next_step,
        "claim_status": claim_status,
        "runtime_profile": "EAY_TERMINAL",
        "sku_id": str(row["sku_id"]),
        "planned_quantity": _decimal_text(planned),
        "source_location_id": row.get("source_location_id"),
        "destination_location_id": row.get("destination_location_id"),
        "container_id": row.get("container_id"),
        "allowed_conditions": allowed_conditions,
    }


def list_operational_mobile_missions(
    principal: InventoryPrincipal,
    active_shift_id: str,
) -> list[dict[str, Any]]:
    principal.validate()
    shift_id = str(active_shift_id).strip()
    if not shift_id:
        return []
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _assert_active_device(db, principal)
        rows = db.execute(
            """SELECT
                 m.mission_id,m.warehouse_id,m.mission_type,m.operation,
                 m.external_reference,m.steps,m.state,m.sku_id,m.planned_quantity,
                 m.source_location_id,m.destination_location_id,m.container_id,
                 m.allowed_conditions,m.created_at,
                 c.employee_id AS claim_employee_id,
                 c.device_id AS claim_device_id,
                 c.shift_id AS claim_shift_id,
                 count(e.event_id)::integer AS completed_steps
               FROM inventory_operational_missions m
               LEFT JOIN inventory_operational_claims c
                 ON c.tenant_id=m.tenant_id
                AND c.mission_id=m.mission_id
                AND c.released_at IS NULL
               LEFT JOIN inventory_operational_events e
                 ON e.tenant_id=m.tenant_id
                AND e.mission_id=m.mission_id
               WHERE m.tenant_id=%s
                 AND m.warehouse_id=ANY(%s)
                 AND m.state IN ('OPEN','CLAIMED')
                 AND m.intent_version=1
               GROUP BY
                 m.mission_id,m.warehouse_id,m.mission_type,m.operation,
                 m.external_reference,m.steps,m.state,m.sku_id,m.planned_quantity,
                 m.source_location_id,m.destination_location_id,m.container_id,
                 m.allowed_conditions,m.created_at,
                 c.employee_id,c.device_id,c.shift_id
               ORDER BY m.created_at,m.mission_id""",
            (principal.tenant_id, list(principal.warehouse_scope)),
        ).fetchall()
    projected = [
        _project_operational_mobile_row(dict(row), principal, shift_id)
        for row in rows
    ]
    return [row for row in projected if row is not None]
