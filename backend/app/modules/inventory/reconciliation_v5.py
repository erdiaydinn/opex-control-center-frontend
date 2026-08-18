"""Inventory v5 reconciliation: only completed mission attempts contribute to stock truth."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .production import InventoryPrincipal, _assert_runtime_tenant, connect


def reconciliation_v5(principal: InventoryPrincipal, document_id: UUID) -> dict[str, Any]:
    principal.validate()
    with connect() as db:
        _assert_runtime_tenant(db, principal)
        document = db.execute(
            "SELECT warehouse_id,state,revision FROM inventory_documents WHERE tenant_id=%s AND id=%s",
            (principal.tenant_id, document_id),
        ).fetchone()
        if not document or document["warehouse_id"] not in principal.warehouse_scope:
            raise PermissionError("Sayım bulunamadı veya depo kapsamı dışında.")
        rows = db.execute(
            """WITH counted AS (
                 SELECT e.barcode,sum(e.quantity) AS counted_quantity
                 FROM inventory_events e
                 JOIN inventory_mission_attempts a
                   ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
                 WHERE e.tenant_id=%s AND e.document_id=%s
                   AND e.event_type IN ('SCAN','UNEXPECTED_SKU')
                   AND e.barcode IS NOT NULL
                   AND a.status='COMPLETED'
                   AND a.document_id=e.document_id
                   AND a.location_id=e.location_id
                 GROUP BY e.barcode
               )
               SELECT COALESCE(s.sku,'UNEXPECTED') AS sku,COALESCE(s.barcode,c.barcode) AS barcode,
                      COALESCE(s.expected_quantity,0) AS expected_quantity,
                      COALESCE(c.counted_quantity,0) AS counted_quantity,
                      COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0) AS variance,
                      (COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0))*COALESCE(s.unit_cost,0) AS variance_value
               FROM inventory_expected_stock s
               FULL OUTER JOIN counted c ON c.barcode=s.barcode
               WHERE (s.tenant_id=%s AND s.document_id=%s) OR s.document_id IS NULL
               ORDER BY abs(COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0)) DESC""",
            (principal.tenant_id, document_id, principal.tenant_id, document_id),
        ).fetchall()
        revisions = db.execute(
            """SELECT revision,state,actor_subject,employee_id,reason,snapshot_hash,created_at
               FROM inventory_revisions WHERE tenant_id=%s AND document_id=%s ORDER BY revision""",
            (principal.tenant_id, document_id),
        ).fetchall()
        attempts = db.execute(
            """SELECT attempt_id,location_id,status,employee_id,device_id,active_shift_id,
                      created_at,completed_at,abandoned_at,abandonment_reason
               FROM inventory_mission_attempts
               WHERE tenant_id=%s AND document_id=%s ORDER BY created_at,attempt_id""",
            (principal.tenant_id, document_id),
        ).fetchall()
    return {
        "document": dict(document),
        "rows": [dict(row) for row in rows],
        "revisions": [dict(row) for row in revisions],
        "attempts": [dict(row) for row in attempts],
    }
