"""Tenant-bound persistence and governed input resolution for roadmap 13/60."""

from __future__ import annotations

from decimal import Decimal
import json

from . import persistence
from .dpi_authority import DpiSnapshot, KpiObservation


class DpiPersistenceError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise DpiPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_demand_snapshots') IS NOT NULL,
          to_regclass('public.workforce_capacity_snapshots') IS NOT NULL,
          to_regclass('public.workforce_dpi_snapshots') IS NOT NULL
        """
    )
    demand_exists, capacity_exists, dpi_exists = cursor.fetchone()
    if not demand_exists or not capacity_exists or not dpi_exists:
        raise DpiPersistenceError(
            "Workforce V35 DPI schema or governed inputs are missing; apply migrations through 012"
        )
    return configured


def load_latest_governed_pressure_inputs(location_id: str) -> dict[str, object]:
    """Return the newest exact interval with both demand and capacity evidence.

    The caller never supplies required/effective MH. Those values and their
    fingerprints are resolved from tenant-bound immutable authority tables.
    """

    if not location_id.strip():
        raise DpiPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT
              d.interval_start,
              d.interval_minutes,
              d.snapshot_fingerprint,
              d.required_man_hours,
              c.snapshot_fingerprint,
              c.effective_man_hours,
              c.skill_deficit_man_hours,
              d.id,
              c.id
            FROM workforce_demand_snapshots d
            JOIN workforce_capacity_snapshots c
              ON c.tenant_id=d.tenant_id
             AND c.location_id=d.location_id
             AND c.interval_start=d.interval_start
             AND c.interval_minutes=d.interval_minutes
            WHERE d.tenant_id=%s AND d.location_id=%s
            ORDER BY d.interval_start DESC, d.created_at DESC, c.created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        raise DpiPersistenceError(
            "no exact governed demand/capacity interval pair exists for location"
        )
    return {
        "tenant_id": tenant,
        "location_id": location_id,
        "interval_start": row[0],
        "interval_minutes": int(row[1]),
        "demand_snapshot_fingerprint": str(row[2]),
        "required_man_hours": Decimal(str(row[3])),
        "capacity_snapshot_fingerprint": str(row[4]),
        "effective_man_hours": Decimal(str(row[5])),
        "skill_deficit_man_hours": Decimal(str(row[6])),
        "demand_source_ref": f"workforce-demand://{row[7]}",
        "capacity_source_ref": f"workforce-capacity://{row[8]}",
    }


def persist_dpi_snapshot(
    snapshot: DpiSnapshot,
    *,
    kpi_observations: tuple[KpiObservation, ...],
    required_man_hours: Decimal,
    effective_man_hours: Decimal,
    skill_deficit_man_hours: Decimal,
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise DpiPersistenceError("actor_subject is required")
    dpi_id = f"DPI-{snapshot.snapshot_fingerprint[:24]}"
    kpi_payload = [
        item.canonical() for item in sorted(kpi_observations, key=lambda item: item.key)
    ]
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        if snapshot.tenant_id != tenant:
            raise DpiPersistenceError(
                "DPI snapshot tenant does not match runtime tenant authority"
            )
        cursor.execute(
            """
            INSERT INTO workforce_dpi_snapshots (
              tenant_id,id,location_id,interval_start,model_version,
              demand_snapshot_fingerprint,capacity_snapshot_fingerprint,
              required_man_hours,effective_man_hours,skill_deficit_man_hours,
              demand_pressure_index,capacity_gap_man_hours,capacity_sufficient,
              kpi_bad,bad_kpi_keys,manpower_shortage,root_cause,
              automatic_extra_people_permitted,staffing_review_required,
              kpi_observations,explanation,input_fingerprint,snapshot_fingerprint,
              created_by
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,
              %s,%s,%s::jsonb,%s::jsonb,%s,%s,%s
            )
            ON CONFLICT (tenant_id, snapshot_fingerprint) DO NOTHING
            """,
            (
                tenant,
                dpi_id,
                snapshot.location_id,
                snapshot.interval_start,
                snapshot.model_version,
                snapshot.demand_snapshot_fingerprint,
                snapshot.capacity_snapshot_fingerprint,
                required_man_hours,
                effective_man_hours,
                skill_deficit_man_hours,
                snapshot.demand_pressure_index,
                snapshot.capacity_gap_man_hours,
                snapshot.capacity_sufficient,
                snapshot.kpi_bad,
                json.dumps(list(snapshot.bad_kpi_keys)),
                snapshot.manpower_shortage,
                snapshot.root_cause,
                snapshot.automatic_extra_people_permitted,
                snapshot.staffing_review_required,
                json.dumps(kpi_payload, sort_keys=True),
                json.dumps(list(snapshot.explanation)),
                snapshot.input_fingerprint,
                snapshot.snapshot_fingerprint,
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,input_fingerprint,root_cause,manpower_shortage,
                   automatic_extra_people_permitted,created_at
            FROM workforce_dpi_snapshots
            WHERE tenant_id=%s AND snapshot_fingerprint=%s
            """,
            (tenant, snapshot.snapshot_fingerprint),
        )
        row = cursor.fetchone()
        if row is None:
            raise DpiPersistenceError("DPI snapshot persistence failed")
        if str(row[1]) != snapshot.input_fingerprint:
            raise DpiPersistenceError("DPI snapshot fingerprint/input mismatch")
        database.commit()
    return {
        "id": str(row[0]),
        "tenant_id": tenant,
        "input_fingerprint": str(row[1]),
        "snapshot_fingerprint": snapshot.snapshot_fingerprint,
        "root_cause": str(row[2]),
        "manpower_shortage": bool(row[3]),
        "automatic_extra_people_permitted": bool(row[4]),
        "created_at": row[5],
        "idempotent_replay": not inserted,
    }


def get_latest_dpi_snapshot(location_id: str) -> dict[str, object] | None:
    if not location_id.strip():
        raise DpiPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT id,location_id,interval_start,model_version,
                   demand_snapshot_fingerprint,capacity_snapshot_fingerprint,
                   required_man_hours,effective_man_hours,skill_deficit_man_hours,
                   demand_pressure_index,capacity_gap_man_hours,capacity_sufficient,
                   kpi_bad,bad_kpi_keys,manpower_shortage,root_cause,
                   automatic_extra_people_permitted,staffing_review_required,
                   kpi_observations,explanation,input_fingerprint,snapshot_fingerprint,
                   created_by,created_at
            FROM workforce_dpi_snapshots
            WHERE tenant_id=%s AND location_id=%s
            ORDER BY interval_start DESC, created_at DESC
            LIMIT 1
            """,
            (tenant, location_id),
        )
        row = cursor.fetchone()
    if row is None:
        return None
    keys = (
        "id","location_id","interval_start","model_version",
        "demand_snapshot_fingerprint","capacity_snapshot_fingerprint",
        "required_man_hours","effective_man_hours","skill_deficit_man_hours",
        "demand_pressure_index","capacity_gap_man_hours","capacity_sufficient",
        "kpi_bad","bad_kpi_keys","manpower_shortage","root_cause",
        "automatic_extra_people_permitted","staffing_review_required",
        "kpi_observations","explanation","input_fingerprint","snapshot_fingerprint",
        "created_by","created_at",
    )
    result = dict(zip(keys, row, strict=True))
    result["tenant_id"] = tenant
    for key in (
        "required_man_hours","effective_man_hours","skill_deficit_man_hours",
        "demand_pressure_index","capacity_gap_man_hours",
    ):
        result[key] = Decimal(str(result[key]))
    return result
