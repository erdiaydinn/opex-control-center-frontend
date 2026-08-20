"""Signed mobile claim admission for Inventory operational missions.

Claiming a physical Picking/Putaway/Receiving/Transfer mission changes server
state and therefore must not rely on OIDC plus a caller-supplied device id alone.
The command is bound to the server-derived active shift and managed device using
the same timestamp/nonce/P-256 proof contract as terminal event mutations.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from .operational_mission import claim_operational_mission
from .production import (
    InventoryPrincipal,
    _assert_runtime_tenant,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)
from .service import InventoryRuleError


def operational_claim_hash(mission_id: str | UUID, active_shift_id: str) -> str:
    return canonical_payload_hash(
        {
            "active_shift_id": str(active_shift_id).strip(),
            "mission_id": str(UUID(str(mission_id))),
        }
    )


def _accepted_progress_step(
    db: Any,
    principal: InventoryPrincipal,
    mission_id: UUID,
) -> tuple[str, int]:
    """Project immutable accepted event progress; never mutate or rebind old evidence."""

    mission = db.execute(
        """SELECT warehouse_id,state,steps,completed_at
           FROM inventory_operational_missions
           WHERE tenant_id=%s AND mission_id=%s""",
        (principal.tenant_id, mission_id),
    ).fetchone()
    if not mission or mission["warehouse_id"] not in principal.warehouse_scope:
        raise PermissionError("Mission bulunamadı veya depo kapsamı dışında.")
    if mission["completed_at"] is not None or mission["state"] == "COMPLETED":
        raise InventoryRuleError("Tamamlanmış operational mission yeniden claim edilemez.")

    progress = int(
        db.execute(
            """SELECT count(*) AS n
               FROM inventory_operational_events
               WHERE tenant_id=%s AND mission_id=%s""",
            (principal.tenant_id, mission_id),
        ).fetchone()["n"]
    )
    steps = list(mission["steps"] or [])
    if not steps or progress < 0 or progress >= len(steps):
        raise InventoryRuleError("Operational mission evidence/state authority tutarsız.")
    return str(steps[progress]), progress


def claim_operational_mission_signed(
    principal: InventoryPrincipal,
    mission_id: UUID,
    active_shift_id: str,
    timestamp: str,
    nonce: str,
    signature: str,
):
    """Verify one fresh hardware-backed claim command, then enter canonical claim authority.

    Historical operational events remain bound to their original claim/device/shift.
    A supervisor release or managed-device replacement may reopen the mission, but a
    new claim must resume from the first unaccepted canonical step instead of step 0.
    """

    principal.validate()
    command_hash = operational_claim_hash(mission_id, active_shift_id)
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _verify_device_proof(db, principal, command_hash, timestamp, nonce, signature)
        resume_step, resume_progress = _accepted_progress_step(db, principal, mission_id)
        # Nonce consumption is committed before the claim transaction. The
        # canonical claim function independently re-checks active device state,
        # tenant scope and mission concurrency. A failed business claim may be
        # retried only with a fresh nonce/signature.
        db.commit()

    result = claim_operational_mission(principal, mission_id, active_shift_id)
    canonical_step = result.get("next_step")
    if resume_progress > 0 and canonical_step != resume_step:
        # The canonical claim row owns admission; this only corrects the mobile
        # projection after a governed release. No historical event is rewritten.
        result = {
            **result,
            "next_step": resume_step,
            "resumed_from_accepted_steps": resume_progress,
        }
    return result
