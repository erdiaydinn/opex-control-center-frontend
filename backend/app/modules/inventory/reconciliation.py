from __future__ import annotations

from typing import Any
from uuid import UUID


class InventoryReconciliationError(PermissionError):
    pass


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

        rows = db.execute(
            """WITH expected AS (
                 SELECT sku,barcode,expected_quantity,unit_cost
                 FROM inventory_expected_stock
                 WHERE tenant_id=%s AND document_id=%s
               ), counted AS (
                 SELECT e.barcode,sum(e.quantity) AS counted_quantity
                 FROM inventory_events e
                 LEFT JOIN inventory_mission_attempts a
                   ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
                 WHERE e.tenant_id=%s AND e.document_id=%s
                   AND e.event_type IN ('SCAN','UNEXPECTED_SKU')
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
                 GROUP BY e.barcode
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
        "rows": [dict(row) for row in rows],
        "revisions": [dict(row) for row in revisions],
    }
