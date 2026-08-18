from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID


class InventoryExplanationError(PermissionError):
    pass


def _fingerprint(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def explanation_context(
    principal: Any,
    document_id: UUID,
) -> dict[str, Any]:
    """Build bounded, read-only causal evidence for Jarvis from authoritative Inventory truth.

    Free-form audit records, revision reasons, raw barcodes, actor/employee identities and
    device identifiers are deliberately excluded from this context. Count/variance truth is
    derived only from COMPLETED mission attempts; abandoned evidence remains represented
    only as an identity-free lifecycle aggregate. The consumer must treat this structure as
    evidence, never as authorization or executable instructions.
    """
    principal.validate()
    from .production import connect

    with connect() as db:
        runtime = db.execute("SELECT inventory_current_tenant() AS tenant_id").fetchone()
        if not runtime or runtime["tenant_id"] != principal.tenant_id:
            raise InventoryExplanationError(
                "database tenant binding does not match explanation authority"
            )

        document = db.execute(
            """SELECT warehouse_id,state,revision,updated_at
               FROM inventory_documents
               WHERE tenant_id=%s AND id=%s""",
            (principal.tenant_id, document_id),
        ).fetchone()
        if not document or document["warehouse_id"] not in principal.warehouse_scope:
            raise InventoryExplanationError(
                "inventory document is outside explanation authority"
            )

        event_rows = db.execute(
            """SELECT e.event_type,e.location_id,count(*)::integer AS event_count,
                      min(e.occurred_at) AS first_seen_at,max(e.occurred_at) AS last_seen_at
               FROM inventory_events e
               JOIN inventory_mission_attempts a
                 ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
                AND a.document_id=e.document_id AND a.location_id=e.location_id
               WHERE e.tenant_id=%s AND e.document_id=%s
                 AND a.status='COMPLETED'
               GROUP BY e.event_type,e.location_id
               ORDER BY min(e.occurred_at),e.event_type,e.location_id""",
            (principal.tenant_id, document_id),
        ).fetchall()

        attempt_rows = db.execute(
            """SELECT status,count(*)::integer AS attempt_count,
                      count(DISTINCT location_id)::integer AS location_count
               FROM inventory_mission_attempts
               WHERE tenant_id=%s AND document_id=%s
               GROUP BY status ORDER BY status""",
            (principal.tenant_id, document_id),
        ).fetchall()

        revision_rows = db.execute(
            """SELECT revision,state,snapshot_hash,created_at
               FROM inventory_revisions
               WHERE tenant_id=%s AND document_id=%s
               ORDER BY revision""",
            (principal.tenant_id, document_id),
        ).fetchall()

        audit_rows = db.execute(
            """SELECT action,previous_hash,hash,occurred_at
               FROM inventory_audit
               WHERE tenant_id=%s AND document_id=%s
               ORDER BY sequence""",
            (principal.tenant_id, document_id),
        ).fetchall()

        variance = db.execute(
            """WITH expected AS (
                 SELECT barcode,expected_quantity,unit_cost
                 FROM inventory_expected_stock
                 WHERE tenant_id=%s AND document_id=%s
               ), counted AS (
                 SELECT e.barcode,sum(e.quantity) AS counted_quantity
                 FROM inventory_events e
                 JOIN inventory_mission_attempts a
                   ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
                  AND a.document_id=e.document_id AND a.location_id=e.location_id
                 WHERE e.tenant_id=%s AND e.document_id=%s
                   AND e.event_type IN ('SCAN','UNEXPECTED_SKU')
                   AND e.barcode IS NOT NULL
                   AND a.status='COMPLETED'
                 GROUP BY e.barcode
               ), joined AS (
                 SELECT COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0) AS variance,
                        (COALESCE(c.counted_quantity,0)-COALESCE(s.expected_quantity,0))*
                          COALESCE(s.unit_cost,0) AS variance_value
                 FROM expected s
                 FULL OUTER JOIN counted c ON c.barcode=s.barcode
               )
               SELECT count(*) FILTER (WHERE variance<>0)::integer AS variance_line_count,
                      count(*) FILTER (WHERE variance>0)::integer AS positive_line_count,
                      count(*) FILTER (WHERE variance<0)::integer AS negative_line_count,
                      COALESCE(sum(abs(variance)),0) AS absolute_quantity_variance,
                      COALESCE(sum(abs(variance_value)),0) AS absolute_value_variance
               FROM joined""",
            (
                principal.tenant_id,
                document_id,
                principal.tenant_id,
                document_id,
            ),
        ).fetchone()

    evidence = {
        "schema_version": 2,
        "source": "inventory_completed_attempt_truth",
        "read_only": True,
        "free_text_excluded": True,
        "abandoned_attempt_events_excluded_from_stock_truth": True,
        "tenant_id": principal.tenant_id,
        "document_id": str(document_id),
        "warehouse_id": document["warehouse_id"],
        "document": {
            "state": document["state"],
            "revision": document["revision"],
            "updated_at": document["updated_at"],
        },
        "authoritative_events": [dict(row) for row in event_rows],
        "attempt_lifecycle": [dict(row) for row in attempt_rows],
        "revisions": [dict(row) for row in revision_rows],
        "audit_entries": [dict(row) for row in audit_rows],
        "audit_chain_scope": "tenant_global_filtered_to_document",
        "audit_chain_verified_in_context": False,
        "variance_summary": dict(variance or {}),
    }
    return {
        **evidence,
        "context_fingerprint": _fingerprint(evidence),
        "generated_at": datetime.now(UTC),
    }
