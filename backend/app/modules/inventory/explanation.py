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
    device identifiers are deliberately excluded. Once mission-attempt authority exists for
    a document, only COMPLETED attempts may contribute count/variance truth. Historical
    pre-v5 documents with no mission attempts retain their legacy aggregate semantics.
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
               LEFT JOIN inventory_mission_attempts a
                 ON a.tenant_id=e.tenant_id AND a.attempt_id=e.attempt_id
               WHERE e.tenant_id=%s AND e.document_id=%s
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
               GROUP BY e.event_type,e.location_id
               ORDER BY min(e.occurred_at),e.event_type,e.location_id""",
            (principal.tenant_id, document_id),
        ).fetchall()

        attempt_rows = db.execute(
            """SELECT state,count(*)::integer AS attempt_count,
                      count(DISTINCT location_id)::integer AS location_count
               FROM inventory_mission_attempts
               WHERE tenant_id=%s AND document_id=%s
               GROUP BY state ORDER BY state""",
            (principal.tenant_id, document_id),
        ).fetchall()

        lease_closure_rows = db.execute(
            """SELECT c.state,count(*)::integer AS closure_count,
                      min(c.closed_at) AS first_closed_at,max(c.closed_at) AS last_closed_at
               FROM inventory_mission_lease_closures c
               JOIN inventory_mission_leases l
                 ON l.tenant_id=c.tenant_id AND l.lease_id=c.lease_id
               JOIN inventory_mission_attempts a
                 ON a.tenant_id=l.tenant_id AND a.attempt_id=l.attempt_id
               WHERE c.tenant_id=%s AND a.document_id=%s
               GROUP BY c.state ORDER BY c.state""",
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
               ), versioned AS (
                 SELECT e.*,row_number() OVER (
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

    authoritative_events = [dict(row) for row in event_rows]
    evidence = {
        "schema_version": 3,
        "source": "inventory_completed_attempt_truth",
        "read_only": True,
        "free_text_excluded": True,
        "recovery_reasons_free_text_excluded": True,
        "abandoned_attempt_events_excluded_from_stock_truth": True,
        "superseded_attempt_evidence_preserved": True,
        "tenant_id": principal.tenant_id,
        "document_id": str(document_id),
        "warehouse_id": document["warehouse_id"],
        "document": {
            "state": document["state"],
            "revision": document["revision"],
            "updated_at": document["updated_at"],
        },
        # Keep the established `events` key for downstream compatibility while
        # making its authority semantics explicit for new consumers.
        "events": authoritative_events,
        "authoritative_events": authoritative_events,
        "attempt_lifecycle": [dict(row) for row in attempt_rows],
        "lease_closure_lifecycle": [dict(row) for row in lease_closure_rows],
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
