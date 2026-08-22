from __future__ import annotations

from typing import Any
from uuid import UUID


class InventoryReconciliationError(PermissionError):
    pass


def _wall_to_wall_status(db: Any, tenant_id: str, document_id: UUID, state: str) -> dict[str, Any]:
    status = db.execute(
        """WITH scoped AS (
             SELECT l.location_id,l.completed_event_id
             FROM inventory_document_locations l
             WHERE l.tenant_id=%s AND l.document_id=%s
           ), valid_completed AS (
             SELECT l.location_id
             FROM scoped l
             JOIN inventory_events e
               ON e.tenant_id=%s
              AND e.document_id=%s
              AND e.location_id=l.location_id
              AND e.event_id=l.completed_event_id
              AND e.event_type='LOCATION_COMPLETE'
             JOIN inventory_mission_attempts a
               ON a.tenant_id=e.tenant_id
              AND a.attempt_id=e.attempt_id
              AND a.document_id=e.document_id
              AND a.location_id=e.location_id
              AND a.state='COMPLETED'
             JOIN inventory_mission_lease_closures c
               ON c.tenant_id=e.tenant_id
              AND c.lease_id=e.lease_id
              AND c.state='COMPLETED'
           ), active_attempts AS (
             SELECT count(*)::integer AS n
             FROM inventory_mission_attempts
             WHERE tenant_id=%s AND document_id=%s AND state='ACTIVE'
           ), live_leases AS (
             SELECT count(*)::integer AS n
             FROM inventory_mission_leases ml
             JOIN inventory_mission_attempts a
               ON a.tenant_id=ml.tenant_id AND a.attempt_id=ml.attempt_id
             LEFT JOIN inventory_mission_lease_closures c
               ON c.tenant_id=ml.tenant_id AND c.lease_id=ml.lease_id
             WHERE a.tenant_id=%s AND a.document_id=%s
               AND c.lease_id IS NULL AND ml.valid_until>now()
           )
           SELECT
             (SELECT count(*)::integer FROM scoped) AS required_location_count,
             (SELECT count(*)::integer FROM valid_completed) AS completed_location_count,
             (SELECT n FROM active_attempts) AS active_attempt_count,
             (SELECT n FROM live_leases) AS live_lease_count,
             COALESCE((
               SELECT array_agg(s.location_id ORDER BY s.location_id)
               FROM scoped s
               LEFT JOIN valid_completed v ON v.location_id=s.location_id
               WHERE v.location_id IS NULL
             ),ARRAY[]::text[]) AS remaining_locations,
             COALESCE((
               SELECT array_agg(s.location_id ORDER BY s.location_id)
               FROM scoped s
               WHERE s.completed_event_id IS NOT NULL
                 AND NOT EXISTS (
                   SELECT 1 FROM valid_completed v WHERE v.location_id=s.location_id
                 )
             ),ARRAY[]::text[]) AS invalid_completion_locations""",
        (
            tenant_id,
            document_id,
            tenant_id,
            document_id,
            tenant_id,
            document_id,
            tenant_id,
            document_id,
        ),
    ).fetchone()
    if not status:
        raise InventoryReconciliationError("wall-to-wall status could not be resolved")

    result = dict(status)
    required = int(result["required_location_count"] or 0)
    completed = int(result["completed_location_count"] or 0)
    active_attempts = int(result["active_attempt_count"] or 0)
    live_leases = int(result["live_lease_count"] or 0)
    invalid_locations = list(result.get("invalid_completion_locations") or [])
    remaining_locations = list(result.get("remaining_locations") or [])

    blockers: list[dict[str, Any]] = []
    if required <= 0:
        blockers.append({"code": "EMPTY_SCOPE", "count": 1})
    if remaining_locations:
        blockers.append(
            {
                "code": "LOCATIONS_REMAINING",
                "count": len(remaining_locations),
                "locations": remaining_locations,
            }
        )
    if invalid_locations:
        blockers.append(
            {
                "code": "INVALID_COMPLETION_EVIDENCE",
                "count": len(invalid_locations),
                "locations": invalid_locations,
            }
        )
    if active_attempts:
        blockers.append({"code": "ACTIVE_ATTEMPTS", "count": active_attempts})
    if live_leases:
        blockers.append({"code": "LIVE_LEASES", "count": live_leases})

    result.update(
        {
            "state": state,
            "remaining_location_count": max(required - completed, 0),
            "remaining_locations": remaining_locations,
            "invalid_completion_locations": invalid_locations,
            "blockers": blockers,
            "ready_to_submit": (
                state == "COUNTING"
                and required > 0
                and completed == required
                and active_attempts == 0
                and live_leases == 0
                and not invalid_locations
            ),
        }
    )
    return result


def reconciliation(
    principal: Any,
    document_id: UUID,
) -> dict[str, Any]:
    """Read authoritative reconciliation without cross-document or abandoned-attempt joins."""
    principal.validate()
    from .production import connect

    with connect() as db:
        runtime = db.execute("SELECT inventory_current_tenant() AS tenant_id").fetchone()
        if not runtime or runtime["tenant_id"] != principal.tenant_id:
            raise InventoryReconciliationError(
                "database tenant binding does not match reconciliation authority"
            )

        document = db.execute(
            """SELECT warehouse_id,state,revision
               FROM inventory_documents
               WHERE tenant_id=%s AND id=%s""",
            (principal.tenant_id, document_id),
        ).fetchone()
        if not document or document["warehouse_id"] not in principal.warehouse_scope:
            raise InventoryReconciliationError(
                "inventory document is outside reconciliation authority"
            )

        wall_to_wall = _wall_to_wall_status(
            db,
            principal.tenant_id,
            document_id,
            str(document["state"]),
        )

        rows = db.execute(
            """WITH expected AS (
                 SELECT sku,barcode,expected_quantity,unit_cost
                 FROM inventory_expected_stock
                 WHERE tenant_id=%s AND document_id=%s
               ), versioned AS (
                 SELECT e.*,
                        row_number() OVER (
                          PARTITION BY e.attempt_id,e.location_id,e.barcode
                          ORDER BY e.count_version DESC
                        ) AS count_version_rank
                 FROM inventory_events e
                 LEFT JOIN inventory_mission_attempts a
                   ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
                 WHERE e.tenant_id=%s AND e.document_id=%s
                   AND e.event_type IN ('SCAN','UNEXPECTED_SKU','RECOUNT')
                   AND e.barcode IS NOT NULL
                   AND (
                     a.state='COMPLETED'
                     OR (
                       e.attempt_id IS NULL
                       AND NOT EXISTS (
                         SELECT 1 FROM inventory_mission_attempts any_attempt
                         WHERE any_attempt.tenant_id=e.tenant_id
                           AND any_attempt.document_id=e.document_id
                       )
                     )
                   )
               ), counted AS (
                 SELECT barcode,sum(quantity) AS counted_quantity
                 FROM versioned WHERE count_version_rank=1
                 GROUP BY barcode
               )
               SELECT COALESCE(s.sku,'UNEXPECTED') AS sku,
                      COALESCE(s.barcode,c.barcode) AS barcode,
                      COALESCE(s.expected_quantity,0) AS expected_quantity,
                      COALESCE(c.counted_quantity,0) AS counted_quantity,
                      COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0) AS variance,
                      (COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0))*
                        COALESCE(s.unit_cost,0) AS variance_value
               FROM expected s
               FULL OUTER JOIN counted c ON c.barcode=s.barcode
               ORDER BY abs(COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0)) DESC""",
            (
                principal.tenant_id,
                document_id,
                principal.tenant_id,
                document_id,
            ),
        ).fetchall()

        revisions = db.execute(
            """SELECT revision,state,actor_subject,employee_id,reason,snapshot_hash,created_at
               FROM inventory_revisions
               WHERE tenant_id=%s AND document_id=%s
               ORDER BY revision""",
            (principal.tenant_id, document_id),
        ).fetchall()

    return {
        "document": dict(document),
        "wall_to_wall": wall_to_wall,
        "rows": [dict(row) for row in rows],
        "revisions": [dict(row) for row in revisions],
    }
