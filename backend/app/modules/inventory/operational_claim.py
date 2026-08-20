"""Signed mobile claim admission for Inventory operational missions.

Claiming a physical Picking/Putaway/Receiving/Transfer mission changes server
state and therefore must not rely on OIDC plus a caller-supplied device id alone.
The command is bound to the server-derived active shift and managed device using
the same timestamp/nonce/P-256 proof contract as terminal event mutations.
"""
from __future__ import annotations

from uuid import UUID

from .operational_mission import claim_operational_mission
from .production import (
    InventoryPrincipal,
    _assert_runtime_tenant,
    _verify_device_proof,
    canonical_payload_hash,
    connect,
)


def operational_claim_hash(mission_id: str | UUID, active_shift_id: str) -> str:
    return canonical_payload_hash(
        {
            "active_shift_id": str(active_shift_id).strip(),
            "mission_id": str(UUID(str(mission_id))),
        }
    )


def claim_operational_mission_signed(
    principal: InventoryPrincipal,
    mission_id: UUID,
    active_shift_id: str,
    timestamp: str,
    nonce: str,
    signature: str,
):
    """Verify one fresh hardware-backed claim command, then enter canonical claim authority."""

    principal.validate()
    command_hash = operational_claim_hash(mission_id, active_shift_id)
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        _verify_device_proof(db, principal, command_hash, timestamp, nonce, signature)
        # Nonce consumption is committed before the claim transaction. The
        # canonical claim function independently re-checks active device state,
        # tenant scope and mission concurrency. A failed business claim may be
        # retried only with a fresh nonce/signature.
        db.commit()
    return claim_operational_mission(principal, mission_id, active_shift_id)
