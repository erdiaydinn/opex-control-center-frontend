from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Literal

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.core.resources import engine

from .repository import _set_tenant


class FieldGovernanceError(ValueError):
    pass


def _fingerprint(value: object) -> str:
    payload = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _allowed_ids(values: frozenset[str]) -> list[str]:
    if not values:
        raise FieldGovernanceError("authorized Field location scope is empty")
    return sorted(values)


async def retire_template_version(
    *,
    tenant_id: str,
    actor_subject: str,
    template_id: str,
    template_version: int,
) -> dict[str, object]:
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        active = await connection.scalar(
            text(
                """
                SELECT EXISTS (
                    SELECT 1 FROM field_missions
                    WHERE tenant_id=CAST(:tenant_id AS UUID)
                      AND template_id=:template_id
                      AND template_version=:template_version
                      AND status='active'
                )
                """
            ),
            {
                "tenant_id": tenant_id,
                "template_id": template_id,
                "template_version": template_version,
            },
        )
        if active:
            raise FieldGovernanceError(
                "template version cannot retire while an active mission uses it"
            )
        result = await connection.execute(
            text(
                """
                UPDATE field_templates
                SET status='retired'
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND template_id=:template_id
                  AND version=:template_version
                  AND status IN ('draft','active')
                RETURNING template_id, version, status
                """
            ),
            {
                "tenant_id": tenant_id,
                "template_id": template_id,
                "template_version": template_version,
            },
        )
        row = result.mappings().first()
        if row is None:
            raise FieldGovernanceError("template version is missing or already retired")
        return {
            **dict(row),
            "retired_by": actor_subject,
            "template_content_mutated": False,
        }


async def create_recurrence_rule(
    *,
    tenant_id: str,
    actor_subject: str,
    mission_id: str,
    cadence: Literal["daily", "weekly", "monthly"],
    interval_count: int,
    timezone_name: str,
    window_minutes: int,
    effective_from: datetime,
    effective_until: datetime | None,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    allowed = _allowed_ids(allowed_location_ids)
    if effective_from.tzinfo is None or effective_from.utcoffset() is None:
        raise FieldGovernanceError("recurrence effective_from must be timezone-aware")
    if effective_until is not None:
        if effective_until.tzinfo is None or effective_until.utcoffset() is None:
            raise FieldGovernanceError("recurrence effective_until must be timezone-aware")
        if effective_until <= effective_from:
            raise FieldGovernanceError("recurrence effective_until must be after effective_from")

    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        mission = await connection.execute(
            text(
                """
                SELECT m.id,
                       COUNT(t.location_id) AS total_targets,
                       COUNT(t.location_id) FILTER (
                           WHERE t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                       ) AS authorized_targets
                FROM field_missions m
                JOIN field_mission_targets t
                  ON t.tenant_id=m.tenant_id AND t.mission_id=m.id
                WHERE m.tenant_id=CAST(:tenant_id AS UUID)
                  AND m.id=CAST(:mission_id AS UUID)
                  AND m.status IN ('draft','active','closed')
                GROUP BY m.id
                """
            ),
            {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": allowed},
        )
        mission_row = mission.mappings().first()
        if mission_row is None or int(mission_row["total_targets"]) != int(
            mission_row["authorized_targets"]
        ):
            raise FieldGovernanceError(
                "recurrence requires authority over every frozen mission target"
            )

        await connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
            {"lock_key": f"field-recurrence:{tenant_id}:{mission_id}"},
        )
        latest = await connection.scalar(
            text(
                """
                SELECT COALESCE(MAX(revision), 0)
                FROM field_recurrence_rules
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND mission_id=CAST(:mission_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "mission_id": mission_id},
        )
        revision = int(latest or 0) + 1
        rule_payload = {
            "tenant_id": tenant_id,
            "mission_id": mission_id,
            "revision": revision,
            "cadence": cadence,
            "interval_count": interval_count,
            "timezone": timezone_name,
            "window_minutes": window_minutes,
            "effective_from": effective_from.isoformat(),
            "effective_until": effective_until.isoformat() if effective_until else None,
        }
        rule_fingerprint = _fingerprint(rule_payload)
        result = await connection.execute(
            text(
                """
                INSERT INTO field_recurrence_rules (
                    tenant_id, mission_id, revision, cadence, interval_count, timezone,
                    window_minutes, effective_from, effective_until, status,
                    rule_fingerprint, created_by
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :revision,
                    :cadence, :interval_count, :timezone, :window_minutes,
                    :effective_from, :effective_until, 'active', :rule_fingerprint, :created_by
                )
                RETURNING id, created_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "revision": revision,
                "cadence": cadence,
                "interval_count": interval_count,
                "timezone": timezone_name,
                "window_minutes": window_minutes,
                "effective_from": effective_from,
                "effective_until": effective_until,
                "rule_fingerprint": rule_fingerprint,
                "created_by": actor_subject,
            },
        )
        row = result.mappings().one()
        return {
            "id": str(row["id"]),
            **rule_payload,
            "rule_fingerprint": rule_fingerprint,
            "created_at": row["created_at"],
            "snapshot_policy": "each occurrence must resolve and freeze targets independently",
        }


async def list_recurrence_rules(
    *, tenant_id: str, mission_id: str, allowed_location_ids: frozenset[str]
) -> list[dict[str, object]]:
    allowed = _allowed_ids(allowed_location_ids)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT r.id, r.mission_id, r.revision, r.cadence, r.interval_count,
                       r.timezone, r.window_minutes, r.effective_from, r.effective_until,
                       r.status, r.rule_fingerprint, r.created_by, r.created_at
                FROM field_recurrence_rules r
                WHERE r.tenant_id=CAST(:tenant_id AS UUID)
                  AND r.mission_id=CAST(:mission_id AS UUID)
                  AND NOT EXISTS (
                      SELECT 1 FROM field_mission_targets t
                      WHERE t.tenant_id=r.tenant_id AND t.mission_id=r.mission_id
                        AND NOT (t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[])))
                  )
                ORDER BY r.revision DESC
                """
            ),
            {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": allowed},
        )
        rows = []
        for row in result.mappings().all():
            item = dict(row)
            item["id"] = str(item["id"])
            item["mission_id"] = str(item["mission_id"])
            rows.append(item)
        return rows


async def exempt_target(
    *,
    tenant_id: str,
    actor_subject: str,
    mission_id: str,
    location_id: str,
    reason_code: str,
    reason: str,
    evidence_ref: str | None,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    if location_id not in allowed_location_ids:
        raise FieldGovernanceError("target exemption is outside authorized Field scope")
    normalized_reason = reason.strip()
    if not normalized_reason:
        raise FieldGovernanceError("target exemption requires a reason")
    evidence_hash = (
        hashlib.sha256(evidence_ref.strip().encode("utf-8")).hexdigest()
        if evidence_ref and evidence_ref.strip()
        else None
    )
    fingerprint = _fingerprint(
        {
            "tenant_id": tenant_id,
            "mission_id": mission_id,
            "location_id": location_id,
            "reason_code": reason_code,
            "reason": normalized_reason,
            "evidence_ref_hash": evidence_hash,
            "approved_by": actor_subject,
        }
    )
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        target = await connection.execute(
            text(
                """
                SELECT status
                FROM field_mission_targets
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND mission_id=CAST(:mission_id AS UUID)
                  AND location_id=:location_id
                FOR UPDATE
                """
            ),
            {"tenant_id": tenant_id, "mission_id": mission_id, "location_id": location_id},
        )
        row = target.mappings().first()
        if row is None:
            raise FieldGovernanceError("Field target not found")
        if str(row["status"]) in {"verified", "exempt"}:
            raise FieldGovernanceError("verified or already-exempt target cannot be exempted")
        try:
            inserted = await connection.execute(
                text(
                    """
                    INSERT INTO field_target_exemptions (
                        tenant_id, mission_id, location_id, reason_code, reason,
                        evidence_ref_hash, approved_by, exemption_fingerprint
                    ) VALUES (
                        CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :location_id,
                        :reason_code, :reason, :evidence_ref_hash, :approved_by, :fingerprint
                    )
                    RETURNING id, created_at
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "mission_id": mission_id,
                    "location_id": location_id,
                    "reason_code": reason_code,
                    "reason": normalized_reason,
                    "evidence_ref_hash": evidence_hash,
                    "approved_by": actor_subject,
                    "fingerprint": fingerprint,
                },
            )
        except IntegrityError as exc:
            raise FieldGovernanceError("target already has an immutable exemption record") from exc
        await connection.execute(
            text(
                """
                UPDATE field_mission_targets
                SET status='exempt', updated_at=CURRENT_TIMESTAMP
                WHERE tenant_id=CAST(:tenant_id AS UUID)
                  AND mission_id=CAST(:mission_id AS UUID)
                  AND location_id=:location_id
                """
            ),
            {"tenant_id": tenant_id, "mission_id": mission_id, "location_id": location_id},
        )
        inserted_row = inserted.mappings().one()
        return {
            "id": str(inserted_row["id"]),
            "mission_id": mission_id,
            "location_id": location_id,
            "status": "exempt",
            "exemption_fingerprint": fingerprint,
            "evidence_ref_hash": evidence_hash,
            "created_at": inserted_row["created_at"],
        }


async def preview_server_targeting(
    *,
    tenant_id: str,
    allowed_location_ids: frozenset[str],
    criterion: Literal["field.overdue", "field.rework", "field.unseen"],
) -> dict[str, object]:
    status_by_criterion = {
        "field.overdue": "overdue",
        "field.rework": "rework",
        "field.unseen": "unseen",
    }
    status_value = status_by_criterion[criterion]
    allowed = _allowed_ids(allowed_location_ids)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        result = await connection.execute(
            text(
                """
                SELECT DISTINCT t.location_id
                FROM field_mission_targets t
                JOIN field_missions m ON m.tenant_id=t.tenant_id AND m.id=t.mission_id
                WHERE t.tenant_id=CAST(:tenant_id AS UUID)
                  AND t.status=:target_status
                  AND m.status='active'
                  AND t.location_id=ANY(CAST(:allowed_ids AS VARCHAR[]))
                ORDER BY t.location_id
                """
            ),
            {"tenant_id": tenant_id, "target_status": status_value, "allowed_ids": allowed},
        )
        location_ids = [str(row["location_id"]) for row in result.mappings().all()]
    snapshot = {
        "criterion": criterion,
        "source_authority": "eay_core_field_status",
        "tenant_id": tenant_id,
        "location_ids": location_ids,
    }
    return {
        "criterion": criterion,
        "source_authority": "eay_core_field_status",
        "location_ids": location_ids,
        "target_count": len(location_ids),
        "snapshot_fingerprint": _fingerprint(snapshot),
        "browser_location_authority": False,
    }


async def request_export(
    *,
    tenant_id: str,
    actor_subject: str,
    format_name: Literal["csv", "xlsx", "json"],
    mission_id: str | None,
    allowed_location_ids: frozenset[str],
) -> dict[str, object]:
    allowed = _allowed_ids(allowed_location_ids)
    scope_snapshot: dict[str, object] = {
        "location_ids": allowed,
        "mission_id": mission_id,
    }
    scope_fingerprint = _fingerprint(scope_snapshot)
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        if mission_id is not None:
            unauthorized = await connection.scalar(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1 FROM field_mission_targets
                        WHERE tenant_id=CAST(:tenant_id AS UUID)
                          AND mission_id=CAST(:mission_id AS UUID)
                          AND NOT (location_id=ANY(CAST(:allowed_ids AS VARCHAR[])))
                    )
                    """
                ),
                {"tenant_id": tenant_id, "mission_id": mission_id, "allowed_ids": allowed},
            )
            if unauthorized:
                raise FieldGovernanceError("export request exceeds authorized Field location scope")
        result = await connection.execute(
            text(
                """
                INSERT INTO field_export_requests (
                    tenant_id, mission_id, format, scope_snapshot, scope_fingerprint, requested_by
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:mission_id AS UUID), :format,
                    CAST(:scope_snapshot AS JSONB), :scope_fingerprint, :requested_by
                )
                RETURNING id, requested_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "mission_id": mission_id,
                "format": format_name,
                "scope_snapshot": json.dumps(scope_snapshot, sort_keys=True),
                "scope_fingerprint": scope_fingerprint,
                "requested_by": actor_subject,
            },
        )
        row = result.mappings().one()
        return {
            "id": str(row["id"]),
            "format": format_name,
            "mission_id": mission_id,
            "scope_fingerprint": scope_fingerprint,
            "requested_at": row["requested_at"],
            "state": "pending_approval",
            "export_materialization_permitted": False,
        }


async def decide_export(
    *,
    tenant_id: str,
    actor_subject: str,
    export_request_id: str,
    decision: Literal["approve", "reject"],
    reason: str | None,
) -> dict[str, object]:
    normalized_reason = (reason or "").strip() or None
    if decision == "reject" and normalized_reason is None:
        raise FieldGovernanceError("export rejection requires a reason")
    async with engine.begin() as connection:
        await _set_tenant(connection, tenant_id)
        request = await connection.execute(
            text(
                """
                SELECT r.id, r.requested_by, r.scope_fingerprint, d.id AS decision_id
                FROM field_export_requests r
                LEFT JOIN field_export_decisions d
                  ON d.tenant_id=r.tenant_id AND d.export_request_id=r.id
                WHERE r.tenant_id=CAST(:tenant_id AS UUID)
                  AND r.id=CAST(:request_id AS UUID)
                """
            ),
            {"tenant_id": tenant_id, "request_id": export_request_id},
        )
        request_row = request.mappings().first()
        if request_row is None:
            raise FieldGovernanceError("export request not found")
        if request_row["decision_id"] is not None:
            raise FieldGovernanceError("export request already has an immutable decision")
        if str(request_row["requested_by"]) == actor_subject:
            raise FieldGovernanceError("export requester cannot approve their own export")
        decision_fingerprint = _fingerprint(
            {
                "tenant_id": tenant_id,
                "request_id": export_request_id,
                "scope_fingerprint": str(request_row["scope_fingerprint"]),
                "decision": decision,
                "reason": normalized_reason,
                "decided_by": actor_subject,
            }
        )
        result = await connection.execute(
            text(
                """
                INSERT INTO field_export_decisions (
                    tenant_id, export_request_id, decision, reason, decided_by, decision_fingerprint
                ) VALUES (
                    CAST(:tenant_id AS UUID), CAST(:request_id AS UUID), :decision,
                    :reason, :decided_by, :fingerprint
                )
                RETURNING id, decided_at
                """
            ),
            {
                "tenant_id": tenant_id,
                "request_id": export_request_id,
                "decision": decision,
                "reason": normalized_reason,
                "decided_by": actor_subject,
                "fingerprint": decision_fingerprint,
            },
        )
        row = result.mappings().one()
        return {
            "id": str(row["id"]),
            "export_request_id": export_request_id,
            "decision": decision,
            "decision_fingerprint": decision_fingerprint,
            "decided_at": row["decided_at"],
            "state": "approved_for_materialization" if decision == "approve" else "rejected",
            "export_materialization_permitted": decision == "approve",
            "automatic_external_delivery_permitted": False,
        }
