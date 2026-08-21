"""Coherent read authority for the Workforce intraday command center.

The command center never combines independent "latest" rows. It resolves one DPI
snapshot and joins the exact immutable demand/capacity fingerprints that produced
it. Optional replan evidence is exposed only when its baseline DPI fingerprint is
that same snapshot. No scheduling or staffing mutation is performed here.
"""

from __future__ import annotations

from decimal import Decimal

from . import persistence


class CommandCenterAuthorityError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    tenant = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (tenant,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != tenant:
        raise CommandCenterAuthorityError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_demand_snapshots') IS NOT NULL,
          to_regclass('public.workforce_capacity_snapshots') IS NOT NULL,
          to_regclass('public.workforce_dpi_snapshots') IS NOT NULL,
          to_regclass('public.workforce_replan_scenarios') IS NOT NULL,
          to_regclass('public.workforce_replan_proposals') IS NOT NULL
        """
    )
    if not all(cursor.fetchone()):
        raise CommandCenterAuthorityError(
            "governed Workforce demand/capacity/DPI/replan schema is incomplete"
        )
    return tenant


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def get_command_center_authority(location_id: str) -> dict[str, object] | None:
    """Return one fingerprint-coherent authority bundle for a location."""
    if not location_id.strip():
        raise CommandCenterAuthorityError("location_id is required")

    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT
              p.id,
              p.interval_start,
              p.model_version,
              p.snapshot_fingerprint,
              p.demand_snapshot_fingerprint,
              p.capacity_snapshot_fingerprint,
              p.required_man_hours,
              p.effective_man_hours,
              p.skill_deficit_man_hours,
              p.demand_pressure_index,
              p.capacity_gap_man_hours,
              p.capacity_sufficient,
              p.kpi_bad,
              p.bad_kpi_keys,
              p.manpower_shortage,
              p.root_cause,
              p.automatic_extra_people_permitted,
              p.staffing_review_required,
              p.kpi_observations,
              p.explanation,
              p.created_at,
              d.id,
              d.interval_start,
              d.interval_minutes,
              d.model_version,
              d.required_people,
              d.labor_standard_refs,
              d.contributors,
              d.created_at,
              c.id,
              c.interval_start,
              c.interval_minutes,
              c.model_version,
              c.scheduled_man_hours,
              c.absence_man_hours,
              c.break_man_hours,
              c.unavailable_man_hours,
              c.net_available_man_hours,
              c.skill_feasible_man_hours,
              c.skill_deficit_man_hours,
              c.productivity_factor,
              c.effective_man_hours,
              c.scheduled_fte,
              c.effective_capacity,
              c.skill_deficits,
              c.unused_worker_hours,
              c.source_refs,
              c.contributors,
              c.created_at,
              r.id,
              r.scenario_fingerprint,
              r.scenario_gap_man_hours,
              r.scenario_dpi,
              r.dpi_delta,
              r.predicted_kpi_deltas,
              r.estimated_scenario_cost_minor_units,
              r.cost_delta_minor_units,
              r.shocks,
              rp.recommendation,
              rp.replan_required,
              rp.automatic_apply_permitted,
              rp.human_approval_required,
              rp.proposal_fingerprint,
              r.created_at
            FROM workforce_dpi_snapshots p
            JOIN workforce_demand_snapshots d
              ON d.tenant_id=p.tenant_id
             AND d.location_id=p.location_id
             AND d.snapshot_fingerprint=p.demand_snapshot_fingerprint
            JOIN workforce_capacity_snapshots c
              ON c.tenant_id=p.tenant_id
             AND c.location_id=p.location_id
             AND c.snapshot_fingerprint=p.capacity_snapshot_fingerprint
            LEFT JOIN LATERAL (
              SELECT s.*
              FROM workforce_replan_scenarios s
              WHERE s.tenant_id=p.tenant_id
                AND s.location_id=p.location_id
                AND s.baseline_dpi_snapshot_fingerprint=p.snapshot_fingerprint
              ORDER BY s.created_at DESC
              LIMIT 1
            ) r ON true
            LEFT JOIN workforce_replan_proposals rp
              ON rp.tenant_id=r.tenant_id
             AND rp.scenario_fingerprint=r.scenario_fingerprint
            WHERE p.tenant_id=%s AND p.location_id=%s
            ORDER BY p.interval_start DESC, p.created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()

    if row is None:
        return None

    if row[1] != row[22] or row[1] != row[30]:
        raise CommandCenterAuthorityError(
            "DPI fingerprints resolve to demand/capacity snapshots from different intervals"
        )
    if int(row[23]) != int(row[31]):
        raise CommandCenterAuthorityError(
            "DPI fingerprints resolve to demand/capacity snapshots with different interval widths"
        )

    return {
        "tenant_id": tenant,
        "location_id": location_id,
        "interval_start": row[1],
        "interval_minutes": int(row[23]),
        "dpi": {
            "id": str(row[0]),
            "model_version": str(row[2]),
            "snapshot_fingerprint": str(row[3]),
            "demand_snapshot_fingerprint": str(row[4]),
            "capacity_snapshot_fingerprint": str(row[5]),
            "required_man_hours": _decimal(row[6]),
            "effective_man_hours": _decimal(row[7]),
            "skill_deficit_man_hours": _decimal(row[8]),
            "demand_pressure_index": _decimal(row[9]),
            "capacity_gap_man_hours": _decimal(row[10]),
            "capacity_sufficient": bool(row[11]),
            "kpi_bad": bool(row[12]),
            "bad_kpi_keys": list(row[13] or []),
            "manpower_shortage": bool(row[14]),
            "root_cause": str(row[15]),
            "automatic_extra_people_permitted": bool(row[16]),
            "staffing_review_required": bool(row[17]),
            "kpi_observations": list(row[18] or []),
            "explanation": list(row[19] or []),
            "created_at": row[20],
        },
        "demand": {
            "id": str(row[21]),
            "model_version": str(row[24]),
            "required_people": _decimal(row[25]),
            "labor_standard_refs": list(row[26] or []),
            "contributors": list(row[27] or []),
            "created_at": row[28],
        },
        "capacity": {
            "id": str(row[29]),
            "model_version": str(row[32]),
            "scheduled_man_hours": _decimal(row[33]),
            "absence_man_hours": _decimal(row[34]),
            "break_man_hours": _decimal(row[35]),
            "unavailable_man_hours": _decimal(row[36]),
            "net_available_man_hours": _decimal(row[37]),
            "skill_feasible_man_hours": _decimal(row[38]),
            "skill_deficit_man_hours": _decimal(row[39]),
            "productivity_factor": _decimal(row[40]),
            "effective_man_hours": _decimal(row[41]),
            "scheduled_fte": _decimal(row[42]),
            "effective_capacity": _decimal(row[43]),
            "skill_deficits": dict(row[44] or {}),
            "unused_worker_hours": dict(row[45] or {}),
            "source_refs": list(row[46] or []),
            "contributors": list(row[47] or []),
            "created_at": row[48],
        },
        "replan": None if row[49] is None else {
            "id": str(row[49]),
            "scenario_fingerprint": str(row[50]),
            "scenario_gap_man_hours": _decimal(row[51]),
            "scenario_dpi": _decimal(row[52]),
            "dpi_delta": _decimal(row[53]),
            "predicted_kpi_deltas": dict(row[54] or {}),
            "estimated_scenario_cost_minor_units": int(row[55]),
            "cost_delta_minor_units": int(row[56]),
            "shocks": list(row[57] or []),
            "recommendation": str(row[58]),
            "replan_required": bool(row[59]),
            "automatic_apply_permitted": bool(row[60]),
            "human_approval_required": bool(row[61]),
            "proposal_fingerprint": str(row[62]),
            "created_at": row[63],
        },
    }
