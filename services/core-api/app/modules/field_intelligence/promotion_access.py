from __future__ import annotations

from sqlalchemy import text

from app.core.resources import engine

from .promotion import FieldPromotionError
from .repository import _set_tenant


async def get_promotion_authorization_context(
    *,
    tenant_id: str,
    promotion_id: str,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT p.id, p.location_id, p.consumer_module, p.adapter_key,
                       p.candidate_payload, p.candidate_fingerprint,
                       d.decision AS field_decision,
                       c.id AS consumer_receipt_id
                FROM field_promotion_requests p
                LEFT JOIN field_promotion_decisions d
                  ON d.tenant_id=p.tenant_id AND d.promotion_id=p.id
                LEFT JOIN field_promotion_consumer_receipts c
                  ON c.tenant_id=p.tenant_id AND c.promotion_id=p.id
                WHERE p.tenant_id=CAST(:tenant_id AS UUID)
                  AND p.id=CAST(:promotion_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "promotion_id": promotion_id},
        )
        row = result.mappings().first()
        if row is None:
            raise FieldPromotionError("promotion request not found")
        item = dict(row)
        item["id"] = str(item["id"])
        return item
