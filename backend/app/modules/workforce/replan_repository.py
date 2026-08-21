"""Tenant-bound persistence and authority resolution for roadmap 15/60."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json

from . import persistence
from .replan_authority import (
    CostAssumption,
    KpiSensitivity,
    ReplanBaseline,
    ReplanScenario,
)


class ReplanPersistenceError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise ReplanPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_dpi_snapshots') IS NOT NULL,
          to_regclass('public.workforce_optimizer_proposals') IS NOT NULL,
          to_regclass('public.workforce_replan_model_versions') IS NOT NULL,
          to_regclass('public.workforce_replan_scenarios') IS NOT NULL,
          to_regclass('public.workforce_replan_proposals') IS NOT NULL
        """
    )
    if not all(cursor.fetchone()):
        raise ReplanPersistenceError(
            "Workforce V37 replan schema or governed baseline authority is missing"
        )
    return configured


def load_latest_replan_baseline(location_id: str) -> tuple[str, ReplanBaseline]:
    if not location_id.strip():
        raise ReplanPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT
              d.demand_snapshot_fingerprint,
              d.capacity_snapshot_fingerprint,
              d.snapshot_fingerprint,
              o.proposal_fingerprint,
              d.required_man_hours,
              d.effective_man_hours,
              d.demand_pressure_index,
              o.incremental_cost_minor_units
            FROM workforce_optimizer_proposals o
            JOIN workforce_dpi_snapshots d
              ON d.tenant_id=o.tenant_id
             AND d.snapshot_fingerprint=o.dpi_snapshot_fingerprint
             AND d.location_id=o.location_id
            WHERE o.tenant_id=%s AND o.location_id=%s
            ORDER BY o.created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise ReplanPersistenceError(
            "no optimizer proposal linked to governed DPI exists for replan baseline"
        )
    return tenant, ReplanBaseline(
        demand_snapshot_fingerprint=str(row[0]),
        capacity_snapshot_fingerprint=str(row[1]),
        dpi_snapshot_fingerprint=str(row[2]),
        optimizer_proposal_fingerprint=str(row[3]),
        required_man_hours=Decimal(str(row[4])),
        effective_man_hours=Decimal(str(row[5])),
        demand_pressure_index=Decimal(str(row[6])),
        current_optimizer_cost_minor_units=int(row[7]),
    )


def load_approved_replan_model(
    model_version: str,
) -> tuple[tuple[KpiSensitivity, ...], CostAssumption, str]:
    if not model_version.strip():
        raise ReplanPersistenceError("model_version is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT kpi_sensitivities,incremental_cost_minor_units_per_man_hour,
                   source_ref,authority_fingerprint
            FROM workforce_replan_model_versions
            WHERE tenant_id=%s AND model_version=%s AND status='approved'
              AND effective_from <= now()
            """,
            (tenant, model_version),
        )
        rows = cursor.fetchall()
    if len(rows) != 1:
        raise ReplanPersistenceError(
            "exactly one approved effective replan model version is required"
        )
    raw_sensitivities, cost_per_mh, source_ref, authority_fingerprint = rows[0]
    try:
        sensitivities = tuple(
            KpiSensitivity(
                kpi_key=str(item["kpi_key"]),
                delta_per_dpi_point=Decimal(str(item["delta_per_dpi_point"])),
                model_version=model_version,
                source_ref=str(item["source_ref"]),
            )
            for item in raw_sensitivities
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ReplanPersistenceError("approved replan KPI sensitivity payload is invalid") from error
    cost = CostAssumption(
        incremental_cost_minor_units_per_man_hour=Decimal(str(cost_per_mh)),
        model_version=model_version,
        source_ref=str(source_ref),
    )
    return sensitivities, cost, str(authority_fingerprint)


def _proposal_fingerprint(scenario: ReplanScenario) -> str:
    canonical = json.dumps(
        {
            "scenario_fingerprint": scenario.scenario_fingerprint,
            "recommendation": scenario.recommendation,
            "replan_required": scenario.replan_required,
            "automatic_apply_permitted": scenario.automatic_apply_permitted,
            "human_approval_required": scenario.human_approval_required,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def persist_replan_scenario_and_proposal(
    scenario: ReplanScenario,
    *,
    baseline: ReplanBaseline,
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise ReplanPersistenceError("actor_subject is required")
    scenario_id = f"SCN-{scenario.scenario_fingerprint[:24]}"
    proposal_fingerprint = _proposal_fingerprint(scenario)
    proposal_id = f"RPL-{proposal_fingerprint[:24]}"

    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        if scenario.tenant_id != tenant:
            raise ReplanPersistenceError(
                "replan scenario tenant does not match runtime tenant authority"
            )
        cursor.execute(
            """
            INSERT INTO workforce_replan_scenarios (
              tenant_id,id,location_id,model_version,input_fingerprint,
              scenario_fingerprint,baseline_demand_snapshot_fingerprint,
              baseline_capacity_snapshot_fingerprint,baseline_dpi_snapshot_fingerprint,
              baseline_optimizer_proposal_fingerprint,baseline_required_man_hours,
              baseline_effective_man_hours,scenario_required_man_hours,
              scenario_effective_man_hours,baseline_gap_man_hours,scenario_gap_man_hours,
              gap_delta_man_hours,baseline_dpi,scenario_dpi,dpi_delta,
              predicted_kpi_deltas,estimated_scenario_cost_minor_units,
              cost_delta_minor_units,shocks,assumptions,created_by
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
              %s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s
            )
            ON CONFLICT (tenant_id, scenario_fingerprint) DO NOTHING
            """,
            (
                tenant,
                scenario_id,
                scenario.location_id,
                scenario.model_version,
                scenario.input_fingerprint,
                scenario.scenario_fingerprint,
                baseline.demand_snapshot_fingerprint,
                baseline.capacity_snapshot_fingerprint,
                baseline.dpi_snapshot_fingerprint,
                baseline.optimizer_proposal_fingerprint,
                scenario.baseline_required_man_hours,
                scenario.baseline_effective_man_hours,
                scenario.scenario_required_man_hours,
                scenario.scenario_effective_man_hours,
                scenario.baseline_gap_man_hours,
                scenario.scenario_gap_man_hours,
                scenario.gap_delta_man_hours,
                scenario.baseline_dpi,
                scenario.scenario_dpi,
                scenario.dpi_delta,
                json.dumps({key: str(value) for key, value in scenario.predicted_kpi_deltas.items()}),
                scenario.estimated_scenario_cost_minor_units,
                scenario.cost_delta_minor_units,
                json.dumps(list(scenario.shocks), sort_keys=True),
                json.dumps(scenario.assumptions, sort_keys=True),
                actor_subject,
            ),
        )
        scenario_inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,input_fingerprint
            FROM workforce_replan_scenarios
            WHERE tenant_id=%s AND scenario_fingerprint=%s
            """,
            (tenant, scenario.scenario_fingerprint),
        )
        scenario_row = cursor.fetchone()
        if scenario_row is None or str(scenario_row[1]) != scenario.input_fingerprint:
            raise ReplanPersistenceError("replan scenario immutable replay mismatch")

        cursor.execute(
            """
            INSERT INTO workforce_replan_proposals (
              tenant_id,id,location_id,scenario_fingerprint,recommendation,
              replan_required,automatic_apply_permitted,human_approval_required,
              proposal_fingerprint,created_by
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, scenario_fingerprint) DO NOTHING
            """,
            (
                tenant,
                proposal_id,
                scenario.location_id,
                scenario.scenario_fingerprint,
                scenario.recommendation,
                scenario.replan_required,
                scenario.automatic_apply_permitted,
                scenario.human_approval_required,
                proposal_fingerprint,
                actor_subject,
            ),
        )
        proposal_inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,proposal_fingerprint,automatic_apply_permitted
            FROM workforce_replan_proposals
            WHERE tenant_id=%s AND scenario_fingerprint=%s
            """,
            (tenant, scenario.scenario_fingerprint),
        )
        proposal_row = cursor.fetchone()
        if proposal_row is None or str(proposal_row[1]) != proposal_fingerprint:
            raise ReplanPersistenceError("replan proposal immutable replay mismatch")
        if bool(proposal_row[2]):
            raise ReplanPersistenceError("automatic replan apply authority must remain false")
        database.commit()

    return {
        "scenario_id": str(scenario_row[0]),
        "proposal_id": str(proposal_row[0]),
        "scenario_fingerprint": scenario.scenario_fingerprint,
        "proposal_fingerprint": proposal_fingerprint,
        "automatic_apply_permitted": False,
        "scenario_idempotent_replay": not scenario_inserted,
        "proposal_idempotent_replay": not proposal_inserted,
    }


def get_latest_replan_scenario(location_id: str) -> dict[str, object] | None:
    if not location_id.strip():
        raise ReplanPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT s.id,s.location_id,s.model_version,s.scenario_fingerprint,
                   s.baseline_required_man_hours,s.baseline_effective_man_hours,
                   s.scenario_required_man_hours,s.scenario_effective_man_hours,
                   s.baseline_gap_man_hours,s.scenario_gap_man_hours,s.gap_delta_man_hours,
                   s.baseline_dpi,s.scenario_dpi,s.dpi_delta,s.predicted_kpi_deltas,
                   s.estimated_scenario_cost_minor_units,s.cost_delta_minor_units,
                   s.shocks,s.assumptions,p.recommendation,p.replan_required,
                   p.automatic_apply_permitted,p.human_approval_required,
                   p.proposal_fingerprint,s.created_by,s.created_at
            FROM workforce_replan_scenarios s
            JOIN workforce_replan_proposals p
              ON p.tenant_id=s.tenant_id AND p.scenario_fingerprint=s.scenario_fingerprint
            WHERE s.tenant_id=%s AND s.location_id=%s
            ORDER BY s.created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    keys = (
        "id","location_id","model_version","scenario_fingerprint",
        "baseline_required_man_hours","baseline_effective_man_hours",
        "scenario_required_man_hours","scenario_effective_man_hours",
        "baseline_gap_man_hours","scenario_gap_man_hours","gap_delta_man_hours",
        "baseline_dpi","scenario_dpi","dpi_delta","predicted_kpi_deltas",
        "estimated_scenario_cost_minor_units","cost_delta_minor_units","shocks",
        "assumptions","recommendation","replan_required","automatic_apply_permitted",
        "human_approval_required","proposal_fingerprint","created_by","created_at",
    )
    result = dict(zip(keys, row, strict=True))
    result["tenant_id"] = tenant
    for key in (
        "baseline_required_man_hours","baseline_effective_man_hours",
        "scenario_required_man_hours","scenario_effective_man_hours",
        "baseline_gap_man_hours","scenario_gap_man_hours","gap_delta_man_hours",
        "baseline_dpi","scenario_dpi","dpi_delta",
    ):
        result[key] = Decimal(str(result[key]))
    return result
