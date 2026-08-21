from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .promotion import FieldPromotionError


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


async def get_promotion_context_in_session(
    session: AsyncSession,
    *,
    tenant_id: str,
    promotion_id: str,
) -> dict[str, Any]:
    row = (
        (
            await session.execute(
                text(
                    """
                    SELECT p.id, p.evidence_id, p.location_id, p.consumer_module,
                           p.adapter_key, p.requested_by, p.proposal_fingerprint,
                           p.candidate_payload, p.candidate_fingerprint,
                           d.decision AS field_decision,
                           d.decision_fingerprint,
                           c.id AS consumer_receipt_id,
                           c.decision AS consumer_decision
                    FROM field_promotion_requests p
                    LEFT JOIN field_promotion_decisions d
                      ON d.tenant_id=p.tenant_id AND d.promotion_id=p.id
                    LEFT JOIN field_promotion_consumer_receipts c
                      ON c.tenant_id=p.tenant_id AND c.promotion_id=p.id
                    WHERE p.tenant_id=CAST(:tenant_id AS UUID)
                      AND p.id=CAST(:promotion_id AS UUID)
                    FOR UPDATE OF p
                    """
                ),
                {"tenant_id": tenant_id, "promotion_id": promotion_id},
            )
        )
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise FieldPromotionError("promotion request not found")
    return dict(row)


async def record_consumer_receipt_in_session(
    session: AsyncSession,
    *,
    tenant_id: str,
    actor_subject: str,
    context: dict[str, Any],
    consumer_module: Literal["inventory", "planogram", "budget"],
    destination_candidate_ref: str,
) -> dict[str, Any]:
    if str(context.get("consumer_module")) != consumer_module:
        raise FieldPromotionError("consumer module does not match governed promotion adapter")
    if str(context.get("field_decision") or "") != "approve":
        raise FieldPromotionError("consumer cannot accept a Field-rejected promotion")
    if context.get("consumer_receipt_id") is not None:
        raise FieldPromotionError("promotion already has an immutable consumer receipt")
    if str(context.get("requested_by")) == actor_subject:
        raise FieldPromotionError("promotion proposer cannot self-accept the consumer handoff")
    normalized_ref = destination_candidate_ref.strip()
    if not normalized_ref:
        raise FieldPromotionError("consumer acceptance requires destination candidate reference")

    destination_ref_hash = hashlib.sha256(normalized_ref.encode("utf-8")).hexdigest()
    receipt_fingerprint = _fingerprint(
        {
            "tenant_id": tenant_id,
            "promotion_id": str(context["id"]),
            "proposal_fingerprint": str(context["proposal_fingerprint"]),
            "field_decision_fingerprint": str(context["decision_fingerprint"]),
            "candidate_fingerprint": str(context["candidate_fingerprint"]),
            "consumer_module": consumer_module,
            "decision": "accept",
            "accepted_by": actor_subject,
            "destination_candidate_ref_hash": destination_ref_hash,
            "reason": None,
        }
    )
    row = (
        (
            await session.execute(
                text(
                    """
                    INSERT INTO field_promotion_consumer_receipts (
                        tenant_id, promotion_id, consumer_module, decision,
                        accepted_by, destination_candidate_ref_hash, reason,
                        receipt_fingerprint
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:promotion_id AS UUID),
                        :consumer_module, 'accept', :accepted_by,
                        :destination_candidate_ref_hash, NULL, :receipt_fingerprint
                    )
                    RETURNING id, created_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "promotion_id": str(context["id"]),
                    "consumer_module": consumer_module,
                    "accepted_by": actor_subject,
                    "destination_candidate_ref_hash": destination_ref_hash,
                    "receipt_fingerprint": receipt_fingerprint,
                },
            )
        )
        .mappings()
        .one()
    )
    return {
        "id": str(row["id"]),
        "decision": "accept",
        "receipt_fingerprint": receipt_fingerprint,
        "destination_candidate_ref_hash": destination_ref_hash,
        "created_at": row["created_at"],
    }
