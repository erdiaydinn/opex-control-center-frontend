from __future__ import annotations

import hashlib
import json
from uuid import UUID

from sqlalchemy import text

from app.core.resources import engine

from .promotion import FieldPromotionError
from .repository import _set_tenant

ADAPTER_KEY = "planogram.compliance_observation.v1"


def _fingerprint(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _required(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FieldPromotionError(f"Planogram compliance requires non-blank {key}")
    return value.strip()


def _positive_facing(value: object) -> int:
    if isinstance(value, bool):
        raise FieldPromotionError(
            "Planogram compliance actual_facing_count must be positive integer"
        )
    try:
        facing = int(str(value))
    except (TypeError, ValueError) as exc:
        raise FieldPromotionError(
            "Planogram compliance actual_facing_count must be positive integer"
        ) from exc
    if facing < 1:
        raise FieldPromotionError(
            "Planogram compliance actual_facing_count must be positive integer"
        )
    return facing


def _candidate(payload: dict[str, object], location_id: str) -> dict[str, object]:
    plan_version_id = _required(payload, "plan_version_id")
    try:
        UUID(plan_version_id)
    except ValueError as exc:
        raise FieldPromotionError(
            "Planogram compliance plan_version_id must be UUID"
        ) from exc
    return {
        "candidate_type": "planogram_compliance_observation",
        "location_id": location_id,
        "plan_version_id": plan_version_id,
        "sku": _required(payload, "sku"),
        "actual_aisle_id": _required(payload, "actual_aisle_id"),
        "actual_module_id": _required(payload, "actual_module_id"),
        "actual_shelf_no": _required(payload, "actual_shelf_no"),
        "actual_facing_count": _positive_facing(payload.get("actual_facing_count")),
        "planogram_truth_write_permitted": False,
        "requires_planogram_assignment_validation": True,
    }


async def create_planogram_compliance_promotion(
    *,
    tenant_id: str,
    actor_subject: str,
    evidence_id: str,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    if not allowed_location_ids:
        raise FieldPromotionError("no authorized Field locations for promotion")
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        evidence_result = await connection.execute(
            text(
                """
                SELECT e.id, e.mission_id, e.location_id, e.fingerprint, e.payload,
                       review.id AS review_id, target.status AS target_status,
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
                    SELECT r.id, r.decision
                    FROM field_reviews r
                    WHERE r.tenant_id=e.tenant_id AND r.evidence_id=e.id
                    ORDER BY r.reviewed_at DESC, r.id DESC
                    LIMIT 1
                ) review ON TRUE
                WHERE e.tenant_id=CAST(:tenant_id AS UUID)
                  AND e.id=CAST(:evidence_id AS UUID)
                  AND e.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                  AND review.decision='accept'
                """
            ),
            {
                "tenant_id": tenant_id,
                "evidence_id": evidence_id,
                "allowed_ids": sorted(allowed_location_ids),
            },
        )
        evidence = evidence_result.mappings().first()
        if evidence is None:
            raise FieldPromotionError(
                "promotion requires accepted evidence in authorized scope"
            )
        if str(evidence["latest_evidence_id"]) != str(evidence["id"]):
            raise FieldPromotionError("stale Field evidence cannot be promoted")
        if str(evidence["target_status"]) != "verified":
            raise FieldPromotionError("promotion requires a verified Field target")

        candidate = _candidate(
            dict(evidence["payload"]),
            str(evidence["location_id"]),
        )
        candidate_fingerprint = _fingerprint(candidate)
        proposal_fingerprint = _fingerprint(
            {
                "tenant_id": tenant_id,
                "evidence_id": str(evidence["id"]),
                "review_id": str(evidence["review_id"]),
                "source_evidence_fingerprint": str(evidence["fingerprint"]),
                "consumer_module": "planogram",
                "adapter_key": ADAPTER_KEY,
                "adapter_version": 1,
                "candidate_fingerprint": candidate_fingerprint,
            }
        )
        insert_result = await connection.execute(
            text(
                """
                INSERT INTO field_promotion_requests (
                    tenant_id, evidence_id, review_id, mission_id, location_id,
                    consumer_module, adapter_key, adapter_version,
                    source_evidence_fingerprint, candidate_payload,
                    candidate_fingerprint, proposal_fingerprint, requested_by
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:evidence_id AS UUID),
                    CAST(:review_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                    'planogram', :adapter_key, 1, :source_evidence_fingerprint,
                    CAST(:candidate_payload AS JSONB), :candidate_fingerprint,
                    :proposal_fingerprint, :requested_by
                )
                ON CONFLICT (tenant_id, proposal_fingerprint) DO NOTHING
                RETURNING id, requested_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "evidence_id": str(evidence["id"]),
                "review_id": str(evidence["review_id"]),
                "mission_id": str(evidence["mission_id"]),
                "location_id": str(evidence["location_id"]),
                "adapter_key": ADAPTER_KEY,
                "source_evidence_fingerprint": str(evidence["fingerprint"]),
                "candidate_payload": json.dumps(
                    candidate,
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                "candidate_fingerprint": candidate_fingerprint,
                "proposal_fingerprint": proposal_fingerprint,
                "requested_by": actor_subject,
            },
        )
        row = insert_result.mappings().first()
        if row is None:
            existing = await connection.execute(
                text(
                    """
                    SELECT id, requested_at
                    FROM field_promotion_requests
                    WHERE tenant_id=CAST(:tenant_id AS UUID)
                      AND proposal_fingerprint=:proposal_fingerprint
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "proposal_fingerprint": proposal_fingerprint,
                },
            )
            row = existing.mappings().one()
        return {
            "id": str(row["id"]),
            "evidence_id": str(evidence["id"]),
            "review_id": str(evidence["review_id"]),
            "mission_id": str(evidence["mission_id"]),
            "location_id": str(evidence["location_id"]),
            "consumer_module": "planogram",
            "adapter_key": ADAPTER_KEY,
            "adapter_version": 1,
            "candidate": candidate,
            "candidate_fingerprint": candidate_fingerprint,
            "proposal_fingerprint": proposal_fingerprint,
            "requested_at": row["requested_at"],
            "state": "proposed",
            "truth_mutation_permitted": False,
        }
