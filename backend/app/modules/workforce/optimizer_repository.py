"""Tenant-bound optimizer persistence and immutable DPI input resolution."""

from __future__ import annotations

from decimal import Decimal
import hashlib
import json

from . import persistence
from .optimizer_authority import OptimizationCandidate, OptimizerProposal


class OptimizerPersistenceError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise OptimizerPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_dpi_snapshots') IS NOT NULL,
          to_regclass('public.workforce_optimizer_proposals') IS NOT NULL
        """
    )
    dpi_exists, optimizer_exists = cursor.fetchone()
    if not dpi_exists or not optimizer_exists:
        raise OptimizerPersistenceError(
            "Workforce V36 optimizer schema or governed DPI authority is missing"
        )
    return configured


def load_latest_governed_optimizer_input(location_id: str) -> dict[str, object]:
    if not location_id.strip():
        raise OptimizerPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT snapshot_fingerprint,root_cause,manpower_shortage,
                   capacity_gap_man_hours,skill_deficit_man_hours,created_at,id
            FROM workforce_dpi_snapshots
            WHERE tenant_id=%s AND location_id=%s
            ORDER BY interval_start DESC, created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise OptimizerPersistenceError("no governed DPI snapshot exists for location")
    return {
        "tenant_id": tenant,
        "location_id": location_id,
        "dpi_snapshot_fingerprint": str(row[0]),
        "root_cause": str(row[1]),
        "manpower_shortage": bool(row[2]),
        "capacity_gap_man_hours": Decimal(str(row[3])),
        "skill_deficit_man_hours": Decimal(str(row[4])),
        "dpi_created_at": row[5],
        "dpi_id": str(row[6]),
    }


def _candidate_pool_fingerprint(candidates: tuple[OptimizationCandidate, ...]) -> str:
    canonical = json.dumps(
        [candidate.canonical() for candidate in sorted(candidates, key=lambda item: item.candidate_id)],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def persist_optimizer_proposal(
    proposal: OptimizerProposal,
    *,
    dpi_root_cause: str,
    dpi_manpower_shortage: bool,
    candidates: tuple[OptimizationCandidate, ...],
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise OptimizerPersistenceError("actor_subject is required")
    proposal_id = f"OPT-{proposal.proposal_fingerprint[:24]}"
    candidate_pool_fingerprint = _candidate_pool_fingerprint(candidates)
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        if proposal.tenant_id != tenant:
            raise OptimizerPersistenceError(
                "optimizer proposal tenant does not match runtime tenant authority"
            )
        cursor.execute(
            """
            INSERT INTO workforce_optimizer_proposals (
              tenant_id,id,location_id,model_version,dpi_snapshot_fingerprint,
              dpi_root_cause,dpi_manpower_shortage,input_fingerprint,
              proposal_fingerprint,recommendation_type,selected_candidate_ids,
              selected_actions,target_gap_man_hours,covered_gap_man_hours,
              remaining_gap_man_hours,incremental_cost_minor_units,feasible,
              automatic_execution_permitted,human_approval_required,explanation,
              candidate_pool_fingerprint,created_by
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s,
              %s,%s,%s,%s::jsonb,%s,%s
            )
            ON CONFLICT (tenant_id, proposal_fingerprint) DO NOTHING
            """,
            (
                tenant,
                proposal_id,
                proposal.location_id,
                proposal.model_version,
                proposal.dpi_snapshot_fingerprint,
                dpi_root_cause,
                dpi_manpower_shortage,
                proposal.input_fingerprint,
                proposal.proposal_fingerprint,
                proposal.recommendation_type,
                json.dumps(list(proposal.selected_candidate_ids)),
                json.dumps(list(proposal.selected_actions), sort_keys=True),
                proposal.target_gap_man_hours,
                proposal.covered_gap_man_hours,
                proposal.remaining_gap_man_hours,
                proposal.incremental_cost_minor_units,
                proposal.feasible,
                proposal.automatic_execution_permitted,
                proposal.human_approval_required,
                json.dumps(list(proposal.explanation)),
                candidate_pool_fingerprint,
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,input_fingerprint,recommendation_type,feasible,
                   automatic_execution_permitted,human_approval_required,created_at
            FROM workforce_optimizer_proposals
            WHERE tenant_id=%s AND proposal_fingerprint=%s
            """,
            (tenant, proposal.proposal_fingerprint),
        )
        row = cursor.fetchone()
        if row is None:
            raise OptimizerPersistenceError("optimizer proposal persistence failed")
        if str(row[1]) != proposal.input_fingerprint:
            raise OptimizerPersistenceError("optimizer proposal fingerprint/input mismatch")
        database.commit()
    return {
        "id": str(row[0]),
        "tenant_id": tenant,
        "input_fingerprint": str(row[1]),
        "proposal_fingerprint": proposal.proposal_fingerprint,
        "recommendation_type": str(row[2]),
        "feasible": bool(row[3]),
        "automatic_execution_permitted": bool(row[4]),
        "human_approval_required": bool(row[5]),
        "created_at": row[6],
        "idempotent_replay": not inserted,
    }


def get_latest_optimizer_proposal(location_id: str) -> dict[str, object] | None:
    if not location_id.strip():
        raise OptimizerPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT id,location_id,model_version,dpi_snapshot_fingerprint,
                   dpi_root_cause,dpi_manpower_shortage,input_fingerprint,
                   proposal_fingerprint,recommendation_type,selected_candidate_ids,
                   selected_actions,target_gap_man_hours,covered_gap_man_hours,
                   remaining_gap_man_hours,incremental_cost_minor_units,feasible,
                   automatic_execution_permitted,human_approval_required,explanation,
                   candidate_pool_fingerprint,created_by,created_at
            FROM workforce_optimizer_proposals
            WHERE tenant_id=%s AND location_id=%s
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    keys = (
        "id","location_id","model_version","dpi_snapshot_fingerprint",
        "dpi_root_cause","dpi_manpower_shortage","input_fingerprint",
        "proposal_fingerprint","recommendation_type","selected_candidate_ids",
        "selected_actions","target_gap_man_hours","covered_gap_man_hours",
        "remaining_gap_man_hours","incremental_cost_minor_units","feasible",
        "automatic_execution_permitted","human_approval_required","explanation",
        "candidate_pool_fingerprint","created_by","created_at",
    )
    result = dict(zip(keys, row, strict=True))
    result["tenant_id"] = tenant
    for key in ("target_gap_man_hours","covered_gap_man_hours","remaining_gap_man_hours"):
        result[key] = Decimal(str(result[key]))
    return result
