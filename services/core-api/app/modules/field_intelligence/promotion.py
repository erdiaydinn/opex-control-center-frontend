from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .repository import _set_tenant


class FieldPromotionError(ValueError):
    pass


ConsumerModule = Literal["inventory", "planogram", "budget"]
CandidateBuilder = Callable[[dict[str, object], str], dict[str, object]]


@dataclass(frozen=True)
class PromotionAdapter:
    key: str
    version: int
    consumer_module: ConsumerModule
    consumer_permission: str
    build_candidate: CandidateBuilder


def _canonical_fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _required_text(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FieldPromotionError(f"promotion adapter requires non-blank field {key}")
    return value.strip()


def _positive_decimal(payload: dict[str, object], key: str, *, allow_zero: bool = False) -> str:
    value = payload.get(key)
    if isinstance(value, bool) or value is None:
        raise FieldPromotionError(f"promotion adapter requires numeric field {key}")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise FieldPromotionError(f"promotion adapter requires numeric field {key}") from exc
    if not parsed.is_finite() or parsed < 0 or (parsed == 0 and not allow_zero):
        comparator = "non-negative" if allow_zero else "positive"
        raise FieldPromotionError(f"promotion adapter requires {comparator} field {key}")
    return format(parsed.normalize(), "f")


def _build_planogram_fixture_candidate(
    payload: dict[str, object], location_id: str
) -> dict[str, object]:
    candidate: dict[str, object] = {
        "candidate_type": "planogram_fixture_measurement",
        "location_id": location_id,
        "fixture_id": _required_text(payload, "fixture_id"),
        "width_mm": _positive_decimal(payload, "width_mm"),
        "height_mm": _positive_decimal(payload, "height_mm"),
        "depth_mm": _positive_decimal(payload, "depth_mm"),
        "physical_master_write_permitted": False,
        "requires_planogram_validation_and_approval": True,
    }
    if payload.get("aisle_width_mm") is not None:
        candidate["aisle_width_mm"] = _positive_decimal(payload, "aisle_width_mm")
    if payload.get("capacity_units") is not None:
        candidate["capacity_units"] = _positive_decimal(
            payload,
            "capacity_units",
            allow_zero=True,
        )
    return candidate


def _build_inventory_count_candidate(
    payload: dict[str, object], location_id: str
) -> dict[str, object]:
    sku = payload.get("sku")
    pallet_id = payload.get("pallet_id")
    sku = None if not isinstance(sku, str) or not sku.strip() else sku.strip()
    if not isinstance(pallet_id, str) or not pallet_id.strip():
        pallet_id = None
    else:
        pallet_id = pallet_id.strip()
    if sku is None and pallet_id is None:
        raise FieldPromotionError("inventory promotion requires sku or pallet_id")
    return {
        "candidate_type": "inventory_count_observation",
        "location_id": location_id,
        "sku": sku,
        "pallet_id": pallet_id,
        "quantity": _positive_decimal(payload, "quantity", allow_zero=True),
        "uom": _required_text(payload, "uom"),
        "inventory_truth_write_permitted": False,
        "requires_inventory_reconciliation_and_approval": True,
    }


def _build_budget_support_candidate(
    payload: dict[str, object], location_id: str
) -> dict[str, object]:
    currency = _required_text(payload, "currency").upper()
    if len(currency) != 3 or not currency.isalpha():
        raise FieldPromotionError("budget promotion currency must be an ISO-like three-letter code")
    expense_date = _required_text(payload, "expense_date")
    try:
        date.fromisoformat(expense_date)
    except ValueError as exc:
        raise FieldPromotionError("budget promotion expense_date must be ISO date") from exc
    return {
        "candidate_type": "budget_supporting_evidence",
        "location_id": location_id,
        "cost_center": _required_text(payload, "cost_center"),
        "amount_minor_units": _positive_decimal(
            payload,
            "amount_minor_units",
            allow_zero=True,
        ),
        "currency": currency,
        "expense_date": expense_date,
        "financial_posting_permitted": False,
        "requires_finance_reconciliation_and_approval": True,
    }


ADAPTERS = {
    "planogram.fixture_measurement.v1": PromotionAdapter(
        key="planogram.fixture_measurement.v1",
        version=1,
        consumer_module="planogram",
        consumer_permission="action:planogram:acceptFieldEvidence",
        build_candidate=_build_planogram_fixture_candidate,
    ),
    "inventory.count_observation.v1": PromotionAdapter(
        key="inventory.count_observation.v1",
        version=1,
        consumer_module="inventory",
        consumer_permission="action:inventory:acceptFieldEvidence",
        build_candidate=_build_inventory_count_candidate,
    ),
    "budget.supporting_evidence.v1": PromotionAdapter(
        key="budget.supporting_evidence.v1",
        version=1,
        consumer_module="budget",
        consumer_permission="action:budget:acceptFieldEvidence",
        build_candidate=_build_budget_support_candidate,
    ),
}


def get_adapter(adapter_key: str) -> PromotionAdapter:
    try:
        return ADAPTERS[adapter_key]
    except KeyError as exc:
        raise FieldPromotionError("unsupported governed Field promotion adapter") from exc


def _state(decision: str | None, consumer_decision: str | None) -> str:
    if decision is None:
        return "proposed"
    if decision == "reject":
        return "field_rejected"
    if consumer_decision is None:
        return "field_approved_pending_consumer"
    if consumer_decision == "reject":
        return "consumer_rejected"
    return "consumer_accepted_handoff"


async def create_promotion_request(
    *,
    tenant_id: str,
    actor_subject: str,
    evidence_id: str,
    adapter_key: str,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    if not allowed_location_ids:
        raise FieldPromotionError("no authorized Field locations for promotion")
    adapter = get_adapter(adapter_key)

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        evidence_result = await connection.execute(
            text("""
                SELECT e.id, e.mission_id, e.location_id, e.fingerprint, e.payload,
                       review.id AS review_id, review.reviewer_subject,
                       target.status AS target_status,
                       latest.id AS latest_evidence_id
                FROM field_evidence e
                JOIN field_mission_targets target ON target.tenant_id=e.tenant_id
                  AND target.mission_id=e.mission_id AND target.location_id=e.location_id
                JOIN LATERAL (
                    SELECT candidate.id
                    FROM field_evidence candidate
                    WHERE candidate.tenant_id=e.tenant_id
                      AND candidate.mission_id=e.mission_id
                      AND candidate.location_id=e.location_id
                    ORDER BY candidate.submitted_at DESC, candidate.id DESC
                    LIMIT 1
                ) latest ON TRUE
                JOIN LATERAL (
                    SELECT r.id, r.reviewer_subject, r.decision
                    FROM field_reviews r
                    WHERE r.tenant_id=e.tenant_id AND r.evidence_id=e.id
                    ORDER BY r.reviewed_at DESC, r.id DESC
                    LIMIT 1
                ) review ON TRUE
                WHERE e.tenant_id=CAST(:tenant_id AS UUID)
                  AND e.id=CAST(:evidence_id AS UUID)
                  AND e.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                  AND review.decision='accept'
                """),
            {
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "allowed_ids": sorted(allowed_location_ids),
            },
        )
        evidence = evidence_result.mappings().first()
        if evidence is None:
            raise FieldPromotionError("promotion requires accepted evidence in authorized scope")
        if str(evidence["latest_evidence_id"]) != str(evidence["id"]):
            raise FieldPromotionError("stale Field evidence cannot be promoted")
        if str(evidence["target_status"]) != "verified":
            raise FieldPromotionError("promotion requires a verified Field target")

        source_payload = dict(evidence["payload"])
        candidate = adapter.build_candidate(source_payload, str(evidence["location_id"]))
        candidate_fingerprint = _canonical_fingerprint(candidate)
        proposal_fingerprint = _canonical_fingerprint(
            {
                "tenant_id": tenant_id,
                "evidence_id": str(evidence["id"]),
                "review_id": str(evidence["review_id"]),
                "source_evidence_fingerprint": str(evidence["fingerprint"]),
                "consumer_module": adapter.consumer_module,
                "adapter_key": adapter.key,
                "adapter_version": adapter.version,
                "candidate_fingerprint": candidate_fingerprint,
            }
        )

        insert_result = await connection.execute(
            text("""
                INSERT INTO field_promotion_requests (
                    tenant_id, evidence_id, review_id, mission_id, location_id,
                    consumer_module, adapter_key, adapter_version,
                    source_evidence_fingerprint, candidate_payload,
                    candidate_fingerprint, proposal_fingerprint, requested_by
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:evidence_id AS UUID), CAST(:review_id AS
                    UUID),
                    CAST(:mission_id AS UUID), :location_id, :consumer_module, :adapter_key,
                    :adapter_version, :source_evidence_fingerprint, CAST(:candidate_payload AS
                    JSONB),
                    :candidate_fingerprint, :proposal_fingerprint, :requested_by
                )
                ON CONFLICT (tenant_id, proposal_fingerprint) DO NOTHING
                RETURNING id, requested_at
                """),
            {
                "tenant_id": tenant_id,
                "evidence_id": str(evidence["id"]),
                "review_id": str(evidence["review_id"]),
                "mission_id": str(evidence["mission_id"]),
                "location_id": str(evidence["location_id"]),
                "consumer_module": adapter.consumer_module,
                "adapter_key": adapter.key,
                "adapter_version": adapter.version,
                "source_evidence_fingerprint": str(evidence["fingerprint"]),
                "candidate_payload": json.dumps(candidate, ensure_ascii=False, sort_keys=True),
                "candidate_fingerprint": candidate_fingerprint,
                "proposal_fingerprint": proposal_fingerprint,
                "requested_by": actor_subject,
            },
        )
        inserted = insert_result.mappings().first()
        if inserted is None:
            existing_result = await connection.execute(
                text("""
                    SELECT id, requested_at, requested_by
                    FROM field_promotion_requests
                    WHERE tenant_id=CAST(:tenant_id AS UUID)
                      AND proposal_fingerprint=:proposal_fingerprint
                    """),
                {"tenant_id": tenant_id, "proposal_fingerprint": proposal_fingerprint},
            )
            inserted = existing_result.mappings().one()

        return {
            "id": str(inserted["id"]),
            "evidence_id": str(evidence["id"]),
            "review_id": str(evidence["review_id"]),
            "mission_id": str(evidence["mission_id"]),
            "location_id": str(evidence["location_id"]),
            "consumer_module": adapter.consumer_module,
            "adapter_key": adapter.key,
            "adapter_version": adapter.version,
            "candidate": candidate,
            "candidate_fingerprint": candidate_fingerprint,
            "proposal_fingerprint": proposal_fingerprint,
            "requested_at": inserted["requested_at"],
            "state": "proposed",
            "truth_mutation_permitted": False,
        }


async def list_promotion_requests(
    *,
    tenant_id: str,
    allowed_location_ids: frozenset[str],
    limit: int = 100,
) -> list[dict[str, object]]:
    if not allowed_location_ids:
        return []
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text("""
                SELECT p.id, p.evidence_id, p.review_id, p.mission_id, p.location_id,
                       p.consumer_module, p.adapter_key, p.adapter_version,
                       p.source_evidence_fingerprint, p.candidate_payload,
                       p.candidate_fingerprint, p.proposal_fingerprint,
                       p.requested_by, p.requested_at,
                       d.decision, d.decided_by, d.reason AS decision_reason,
                       d.decision_fingerprint, d.decided_at,
                       c.decision AS consumer_decision, c.accepted_by,
                       c.destination_candidate_ref_hash, c.reason AS consumer_reason,
                       c.receipt_fingerprint, c.created_at AS consumer_decided_at
                FROM field_promotion_requests p
                LEFT JOIN field_promotion_decisions d ON d.tenant_id=p.tenant_id AND
                d.promotion_id=p.id
                LEFT JOIN field_promotion_consumer_receipts c ON c.tenant_id=p.tenant_id AND
                c.promotion_id=p.id
                WHERE p.tenant_id=CAST(:tenant_id AS UUID)
                  AND p.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                ORDER BY p.requested_at DESC, p.id DESC
                LIMIT :limit
                """),
            {
                "tenant_id": tenant_id,
                "allowed_ids": sorted(allowed_location_ids),
                "limit": limit,
            },
        )
        items: list[dict[str, object]] = []
        for row in result.mappings().all():
            item = dict(row)
            for key in ("id", "evidence_id", "review_id", "mission_id"):
                item[key] = str(item[key])
            item["state"] = _state(
                str(item["decision"]) if item.get("decision") else None,
                str(item["consumer_decision"]) if item.get("consumer_decision") else None,
            )
            item["truth_mutation_permitted"] = False
            items.append(item)
        return items


async def decide_promotion_request(
    *,
    tenant_id: str,
    actor_subject: str,
    promotion_id: str,
    decision: Literal["approve", "reject"],
    reason: str | None,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    normalized_reason = (reason or "").strip() or None
    if decision == "reject" and normalized_reason is None:
        raise FieldPromotionError("promotion rejection requires a reason")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        request_result = await connection.execute(
            text("""
                SELECT p.id, p.location_id, p.requested_by, p.proposal_fingerprint,
                       p.consumer_module, p.adapter_key, p.adapter_version,
                       existing.id AS existing_decision_id
                FROM field_promotion_requests p
                LEFT JOIN field_promotion_decisions existing
                  ON existing.tenant_id=p.tenant_id AND existing.promotion_id=p.id
                WHERE p.tenant_id=CAST(:tenant_id AS UUID)
                  AND p.id=CAST(:promotion_id AS UUID)
                  AND p.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                """),
            {
                "tenant_id": tenant_id,
                "promotion_id": promotion_id,
                "allowed_ids": sorted(allowed_location_ids),
            },
        )
        request = request_result.mappings().first()
        if request is None:
            raise FieldPromotionError("promotion request not found in authorized scope")
        if request["existing_decision_id"] is not None:
            raise FieldPromotionError("promotion request already has an immutable decision")
        if str(request["requested_by"]) == actor_subject:
            raise FieldPromotionError(
                "promotion proposer cannot approve or reject their own proposal"
            )

        decision_fingerprint = _canonical_fingerprint(
            {
                "tenant_id": tenant_id,
                "promotion_id": promotion_id,
                "proposal_fingerprint": str(request["proposal_fingerprint"]),
                "decision": decision,
                "decided_by": actor_subject,
                "reason": normalized_reason,
            }
        )
        try:
            decision_result = await connection.execute(
                text("""
                    INSERT INTO field_promotion_decisions (
                        tenant_id, promotion_id, decision, decided_by, reason,
                        decision_fingerprint
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:promotion_id AS UUID), :decision,
                        :decided_by, :reason, :decision_fingerprint
                    )
                    RETURNING id, decided_at
                    """),
                {
                    "tenant_id": tenant_id,
                    "promotion_id": promotion_id,
                    "decision": decision,
                    "decided_by": actor_subject,
                    "reason": normalized_reason,
                    "decision_fingerprint": decision_fingerprint,
                },
            )
        except IntegrityError as exc:
            raise FieldPromotionError(
                "promotion decision collided with a concurrent reviewer"
            ) from exc
        row = decision_result.mappings().one()
        return {
            "id": str(row["id"]),
            "promotion_id": promotion_id,
            "decision": decision,
            "decision_fingerprint": decision_fingerprint,
            "decided_at": row["decided_at"],
            "state": (
                "field_approved_pending_consumer" if decision == "approve" else "field_rejected"
            ),
            "truth_mutation_permitted": False,
        }


async def record_consumer_receipt(
    *,
    tenant_id: str,
    actor_subject: str,
    promotion_id: str,
    consumer_module: ConsumerModule,
    decision: Literal["accept", "reject"],
    destination_candidate_ref: str | None,
    reason: str | None,
) -> dict[str, object]:
    normalized_reason = (reason or "").strip() or None
    normalized_ref = (destination_candidate_ref or "").strip() or None
    if decision == "accept" and normalized_ref is None:
        raise FieldPromotionError(
            "consumer acceptance requires an opaque destination candidate reference"
        )
    if decision == "reject" and normalized_reason is None:
        raise FieldPromotionError("consumer rejection requires a reason")
    if decision == "reject":
        normalized_ref = None

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        request_result = await connection.execute(
            text("""
                SELECT p.id, p.requested_by, p.consumer_module, p.proposal_fingerprint,
                       p.candidate_fingerprint, p.location_id,
                       d.decision AS field_decision, d.decided_by, d.decision_fingerprint,
                       existing.id AS existing_receipt_id
                FROM field_promotion_requests p
                JOIN field_promotion_decisions d ON d.tenant_id=p.tenant_id AND
                d.promotion_id=p.id
                LEFT JOIN field_promotion_consumer_receipts existing
                  ON existing.tenant_id=p.tenant_id AND existing.promotion_id=p.id
                WHERE p.tenant_id=CAST(:tenant_id AS UUID)
                  AND p.id=CAST(:promotion_id AS UUID)
                """),
            {"tenant_id": tenant_id, "promotion_id": promotion_id},
        )
        request = request_result.mappings().first()
        if request is None:
            raise FieldPromotionError("approved promotion request not found")
        if str(request["consumer_module"]) != consumer_module:
            raise FieldPromotionError("consumer module does not match governed promotion adapter")
        if str(request["field_decision"]) != "approve":
            raise FieldPromotionError("consumer cannot accept a Field-rejected promotion")
        if request["existing_receipt_id"] is not None:
            raise FieldPromotionError("promotion already has an immutable consumer receipt")
        if str(request["requested_by"]) == actor_subject:
            raise FieldPromotionError("promotion proposer cannot self-accept the consumer handoff")

        destination_ref_hash = (
            hashlib.sha256(normalized_ref.encode("utf-8")).hexdigest()
            if normalized_ref is not None
            else None
        )
        receipt_fingerprint = _canonical_fingerprint(
            {
                "tenant_id": tenant_id,
                "promotion_id": promotion_id,
                "proposal_fingerprint": str(request["proposal_fingerprint"]),
                "field_decision_fingerprint": str(request["decision_fingerprint"]),
                "candidate_fingerprint": str(request["candidate_fingerprint"]),
                "consumer_module": consumer_module,
                "decision": decision,
                "accepted_by": actor_subject,
                "destination_candidate_ref_hash": destination_ref_hash,
                "reason": normalized_reason,
            }
        )
        try:
            receipt_result = await connection.execute(
                text("""
                    INSERT INTO field_promotion_consumer_receipts (
                        tenant_id, promotion_id, consumer_module, decision,
                        accepted_by, destination_candidate_ref_hash, reason, receipt_fingerprint
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:promotion_id AS UUID), :consumer_module,
                        :decision, :accepted_by, :destination_candidate_ref_hash, :reason,
                        :receipt_fingerprint
                    )
                    RETURNING id, created_at
                    """),
                {
                    "tenant_id": tenant_id,
                    "promotion_id": promotion_id,
                    "consumer_module": consumer_module,
                    "decision": decision,
                    "accepted_by": actor_subject,
                    "destination_candidate_ref_hash": destination_ref_hash,
                    "reason": normalized_reason,
                    "receipt_fingerprint": receipt_fingerprint,
                },
            )
        except IntegrityError as exc:
            raise FieldPromotionError(
                "consumer receipt collided with a concurrent acceptance"
            ) from exc
        row = receipt_result.mappings().one()
        return {
            "id": str(row["id"]),
            "promotion_id": promotion_id,
            "consumer_module": consumer_module,
            "decision": decision,
            "receipt_fingerprint": receipt_fingerprint,
            "destination_candidate_ref_hash": destination_ref_hash,
            "created_at": row["created_at"],
            "state": "consumer_accepted_handoff" if decision == "accept" else "consumer_rejected",
            "truth_mutation_permitted": False,
            "consumer_truth_requires_separate_module_workflow": True,
        }
