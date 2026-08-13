from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from sqlalchemy import text

from .permissions import BudgetUnitOfWork


def _canonical(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


async def emit_financial_event(
    uow: BudgetUnitOfWork,
    *,
    event_type: str,
    aggregate_type: str,
    aggregate_id: UUID,
    payload: dict[str, Any],
    cost_center_id: UUID | None = None,
) -> dict[str, object]:
    chain_key = f"{uow.tenant_id}:{cost_center_id or '__global__'}"
    await uow.session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:chain_key, 0))"),
        {"chain_key": chain_key},
    )
    previous_result = await uow.session.execute(
        text(
            """
            SELECT chain_seq,event_hash FROM financial_event
             WHERE tenant_id=:tenant
               AND cost_center_id IS NOT DISTINCT FROM :center
             ORDER BY chain_seq DESC LIMIT 1
            """
        ),
        {"tenant": uow.tenant_id, "center": cost_center_id},
    )
    previous = previous_result.first()
    sequence = 1 if previous is None else previous.chain_seq + 1
    previous_hash = None if previous is None else previous.event_hash
    canonical_payload = _canonical(payload)
    material = "|".join(
        [
            str(uow.tenant_id),
            "" if cost_center_id is None else str(cost_center_id),
            str(sequence),
            event_type,
            aggregate_type,
            str(aggregate_id),
            uow.actor,
            canonical_payload,
            previous_hash or "",
        ]
    )
    event_hash = hashlib.sha256(material.encode("utf-8")).hexdigest()
    result = await uow.session.execute(
        text(
            """
            INSERT INTO financial_event(
              tenant_id,cost_center_id,chain_seq,event_type,aggregate_type,aggregate_id,
              actor_id,payload,prev_hash,event_hash
            ) VALUES (
              :tenant,:center,:sequence,:event_type,:aggregate_type,:aggregate_id,
              :actor,CAST(:payload AS jsonb),:previous_hash,:event_hash
            ) RETURNING id,chain_seq,event_hash,prev_hash,created_at
            """
        ),
        {
            "tenant": uow.tenant_id,
            "center": cost_center_id,
            "sequence": sequence,
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "actor": uow.actor,
            "payload": canonical_payload,
            "previous_hash": previous_hash,
            "event_hash": event_hash,
        },
    )
    return dict(result.one()._mapping)
