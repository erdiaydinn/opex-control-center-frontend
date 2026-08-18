from __future__ import annotations

from typing import Any
from uuid import UUID


class InventoryReconciliationError(PermissionError):
    pass


def reconciliation(
    principal: Any,
    document_id: UUID,
) -> dict[str, Any]:
    """Read authoritative reconciliation without cross-document barcode joins."""
    principal.validate()
    from .production import connect

    with connect() as db:
        runtime = db.execute("SELECT inventory_current_tenant() AS tenant_id").fetchone()
        if not runtime or runtime["tenant_id"] != principal.tenant_id:
            raise InventoryReconciliationError("database tenant binding does not match reconciliation authority")

        document = db.execute(
            """SELECT warehouse_id,state,revision
               FROM inventory_documents
               WHERE tenant_id=%s AND id=%s""",
            (principal.tenant_id, document_id),
        ).fetchone()
        if not document or document["warehouse_id"] not in principal.warehouse_scope:
            raise InventoryReconciliationError("inventory document is outside reconciliation authority")

        rows = db.execute(
            """WITH expected AS (
                 SELECT sku,barcode,expected_quantity,unit_cost
                 FROM inventory_expected_stock
                 WHERE tenant_id=%s AND document_id=%s
               ), counted AS (
                 SELECT barcode,sum(quantity) AS counted_quantity
                 FROM inventory_events
                 WHERE tenant_id=%s AND document_id=%s
                   AND event_type IN ('SCAN','UNEXPECTED_SKU')
                   AND barcode IS NOT NULL
                 GROUP BY barcode
               )
               SELECT COALESCE(s.sku,'UNEXPECTED') AS sku,
                      COALESCE(s.barcode,c.barcode) AS barcode,
                      COALESCE(s.expected_quantity,0) AS expected_quantity,
                      COALESCE(c.counted_quantity,0) AS counted_quantity,
                      COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0) AS variance,
                      (COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0))*COALESCE(s.unit_cost,0)
                        AS variance_value
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
