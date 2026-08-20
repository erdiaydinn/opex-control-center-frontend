from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import text

from app.core.resources import engine


def _fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _dict(row) -> dict[str, object]:
    return dict(row._mapping)


async def build_audit_intelligence_receipt(
    tenant_id: str,
    *,
    location_ids: frozenset[str] | None,
    regions: frozenset[str] | None,
    unrestricted: bool,
) -> dict[str, object]:
    """Compute Audit intelligence deterministically from authoritative tables.

    No LLM performs arithmetic here. The receipt is suitable as a governed Jarvis
    context source only after the caller's normal Audit authorization is resolved.

    Official compliance score surfaces are fenced from quick/focus/custom visit
    scores. Non-official visits still contribute real actions, assurance cases and
    evidence coverage, but can never move the network compliance score/ranking.
    """

    scope_denied = not unrestricted and not location_ids and not regions
    values = {
        "tenant_id": tenant_id,
        "scope_denied": scope_denied,
        "unrestricted": unrestricted,
        "location_ids": sorted(location_ids or ()),
        "regions": sorted(regions or ()),
    }

    async with engine.begin() as connection:
        await connection.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": tenant_id},
        )
        totals_result = await connection.execute(
            text(
                """
                WITH scoped_runs AS (
                    SELECT ar.*
                    FROM audit_runs ar
                    JOIN field_locations fl
                      ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                    WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                      AND NOT :scope_denied
                      AND (
                        :unrestricted
                        OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                        OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                      )
                ), official_scored_runs AS (
                    SELECT *
                    FROM scoped_runs
                    WHERE official_compliance_eligible IS TRUE
                ), scoped_actions AS (
                    SELECT aa.*
                    FROM audit_actions aa
                    JOIN scoped_runs sr
                      ON sr.tenant_id = aa.tenant_id AND sr.id = aa.audit_run_id
                ), repeated AS (
                    SELECT sr.location_id, aa.item_key
                    FROM scoped_actions aa
                    JOIN scoped_runs sr
                      ON sr.tenant_id = aa.tenant_id AND sr.id = aa.audit_run_id
                    GROUP BY sr.location_id, aa.item_key
                    HAVING COUNT(DISTINCT aa.audit_run_id) >= 2
                ), assurance AS (
                    SELECT c.*
                    FROM audit_assurance_cases c
                    JOIN scoped_runs sr
                      ON sr.tenant_id = c.tenant_id AND sr.id = c.audit_run_id
                ), latest_privacy_verification AS (
                    SELECT DISTINCT ON (v.redaction_receipt_id)
                           v.redaction_receipt_id, v.verification_status
                    FROM audit_redaction_verification_events v
                    WHERE v.tenant_id = CAST(:tenant_id AS UUID)
                    ORDER BY v.redaction_receipt_id, v.verified_at DESC, v.id DESC
                ), media_runs AS (
                    SELECT id
                    FROM scoped_runs
                    WHERE source_mode IN ('photo','video','guided_video','mixed')
                ), verified_media_runs AS (
                    SELECT DISTINCT rr.audit_run_id
                    FROM audit_redaction_receipts rr
                    JOIN media_runs mr ON mr.id = rr.audit_run_id
                    JOIN latest_privacy_verification pv
                      ON pv.redaction_receipt_id = rr.id
                     AND pv.verification_status = 'verified'
                    WHERE rr.tenant_id = CAST(:tenant_id AS UUID)
                )
                SELECT
                    (SELECT COUNT(*) FROM scoped_runs)::integer AS total_runs,
                    (SELECT COUNT(*) FROM scoped_runs WHERE status = 'completed')::integer
                      AS completed_runs,
                    (SELECT COUNT(*) FROM official_scored_runs
                      WHERE status = 'completed')::integer AS official_completed_runs,
                    (SELECT ROUND(AVG(final_score), 2)
                       FROM official_scored_runs
                      WHERE status = 'completed' AND final_score IS NOT NULL)
                      AS average_completed_score,
                    (SELECT COUNT(*) FROM scoped_actions
                      WHERE priority = 'critical'
                        AND status NOT IN ('closed','ai_verified','human_verified'))::integer
                      AS critical_open_actions,
                    (SELECT COUNT(*) FROM scoped_actions
                      WHERE due_at < CURRENT_TIMESTAMP
                        AND status NOT IN ('closed','ai_verified','human_verified'))::integer
                      AS overdue_actions,
                    (SELECT COUNT(*) FROM repeated)::integer AS repeat_findings,
                    (SELECT COUNT(*) FROM assurance
                      WHERE state IN ('MANAGER_REVIEW','MANAGER_UNASSIGNED'))::integer
                      AS manager_review_cases,
                    (SELECT COUNT(*) FROM assurance
                      WHERE state IN ('OPERATIONS_STANDARDS_REVIEW',
                                      'OPERATIONS_STANDARDS_UNASSIGNED'))::integer
                      AS standards_review_cases,
                    (SELECT COUNT(*) FROM assurance
                      WHERE state LIKE '%UNASSIGNED')::integer
                      AS unassigned_assurance_cases,
                    (SELECT COUNT(*) FROM media_runs)::integer AS media_runs,
                    (SELECT COUNT(*) FROM verified_media_runs)::integer
                      AS privacy_verified_media_runs,
                    CASE
                      WHEN (SELECT COUNT(*) FROM media_runs) = 0 THEN NULL
                      ELSE ROUND(
                        100.0 * (SELECT COUNT(*) FROM verified_media_runs)
                        / (SELECT COUNT(*) FROM media_runs),
                        2
                      )
                    END AS evidence_coverage_percent
                """
            ),
            values,
        )
        totals = _dict(totals_result.one())

        risk_result = await connection.execute(
            text(
                """
                WITH scoped_runs AS (
                    SELECT ar.*, fl.name AS location_name, fl.region
                    FROM audit_runs ar
                    JOIN field_locations fl
                      ON fl.tenant_id = ar.tenant_id AND fl.location_id = ar.location_id
                    WHERE ar.tenant_id = CAST(:tenant_id AS UUID)
                      AND NOT :scope_denied
                      AND (
                        :unrestricted
                        OR ar.location_id = ANY(CAST(:location_ids AS VARCHAR[]))
                        OR COALESCE(fl.region, '') = ANY(CAST(:regions AS VARCHAR[]))
                      )
                ), official_scored_runs AS (
                    SELECT *
                    FROM scoped_runs
                    WHERE official_compliance_eligible IS TRUE
                ), action_counts AS (
                    SELECT sr.location_id,
                           COUNT(*) FILTER (
                             WHERE aa.priority = 'critical'
                               AND aa.status NOT IN ('closed','ai_verified','human_verified')
                           )::integer AS critical_open,
                           COUNT(*) FILTER (
                             WHERE aa.due_at < CURRENT_TIMESTAMP
                               AND aa.status NOT IN ('closed','ai_verified','human_verified')
                           )::integer AS overdue
                    FROM scoped_runs sr
                    LEFT JOIN audit_actions aa
                      ON aa.tenant_id = sr.tenant_id AND aa.audit_run_id = sr.id
                    GROUP BY sr.location_id
                ), latest_score AS (
                    SELECT DISTINCT ON (location_id)
                           location_id, final_score, completed_at
                    FROM official_scored_runs
                    WHERE status = 'completed' AND final_score IS NOT NULL
                    ORDER BY location_id, completed_at DESC NULLS LAST, started_at DESC
                )
                SELECT sr.location_id,
                       MAX(sr.location_name) AS location_name,
                       MAX(sr.region) AS region,
                       COALESCE(MAX(ac.critical_open), 0)::integer AS critical_open,
                       COALESCE(MAX(ac.overdue), 0)::integer AS overdue,
                       MAX(ls.final_score) AS latest_score,
                       MAX(ls.completed_at) AS latest_completed_at
                FROM scoped_runs sr
                LEFT JOIN action_counts ac ON ac.location_id = sr.location_id
                LEFT JOIN latest_score ls ON ls.location_id = sr.location_id
                GROUP BY sr.location_id
                ORDER BY COALESCE(MAX(ac.critical_open), 0) DESC,
                         COALESCE(MAX(ac.overdue), 0) DESC,
                         MAX(ls.final_score) ASC NULLS LAST,
                         sr.location_id
                LIMIT 20
                """
            ),
            values,
        )
        risk_locations = [_dict(row) for row in risk_result]

    computed_at = datetime.now(UTC).isoformat()
    facts: dict[str, object] = {
        **totals,
        "risk_locations": risk_locations,
    }
    source_contract = {
        "tables": [
            "audit_runs",
            "audit_actions",
            "audit_assurance_cases",
            "audit_redaction_receipts",
            "audit_redaction_verification_events",
            "field_locations",
        ],
        "calculation_version": "audit.intelligence.summary.v2",
        "score_authority": {
            "official_compliance_only": True,
            "eligibility_column": "audit_runs.official_compliance_eligible",
            "non_official_score_modes": ["FOCUS_SCORE"],
        },
        "scope": {
            "unrestricted": unrestricted,
            "location_ids": sorted(location_ids or ()),
            "regions": sorted(regions or ()),
        },
    }
    fingerprint_payload = {
        "computed_at": computed_at,
        "facts": facts,
        "source_contract": source_contract,
    }
    return {
        "receipt_type": "audit_intelligence_summary",
        "computed_at": computed_at,
        "facts": facts,
        "source_contract": source_contract,
        "receipt_fingerprint": _fingerprint(fingerprint_payload),
        "llm_computed_metrics": False,
    }
