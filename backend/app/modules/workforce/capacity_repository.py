"""Tenant-bound persistence for roadmap 12/60 effective capacity snapshots."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import json

from . import persistence
from .capacity_authority import EffectiveCapacitySnapshot


class CapacityPersistenceError(RuntimeError):
    pass


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise CapacityPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    cursor.execute(
        "SELECT to_regclass('public.workforce_capacity_snapshots') IS NOT NULL"
    )
    if not bool(cursor.fetchone()[0]):
        raise CapacityPersistenceError(
            "Workforce V34 capacity schema is missing; apply migration 011 before capacity execution"
        )
    return configured


def persist_capacity_snapshot(
    snapshot: EffectiveCapacitySnapshot,
    *,
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise CapacityPersistenceError("actor_subject is required")
    capacity_id = f"CAP-{snapshot.snapshot_fingerprint[:24]}"
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        if snapshot.tenant_id != tenant:
            raise CapacityPersistenceError(
                "capacity snapshot tenant does not match runtime tenant authority"
            )
        cursor.execute(
            """
            INSERT INTO workforce_capacity_snapshots (
              tenant_id,id,location_id,interval_start,interval_minutes,model_version,
              input_fingerprint,snapshot_fingerprint,scheduled_man_hours,
              absence_man_hours,break_man_hours,unavailable_man_hours,
              net_available_man_hours,skill_feasible_man_hours,skill_deficit_man_hours,
              productivity_factor,effective_man_hours,scheduled_fte,effective_capacity,
              skill_deficits,unused_worker_hours,source_refs,contributors,created_by
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
              %s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s
            )
            ON CONFLICT (tenant_id, snapshot_fingerprint) DO NOTHING
            """,
            (
                tenant,
                capacity_id,
                snapshot.location_id,
                snapshot.interval_start,
                snapshot.interval_minutes,
                snapshot.model_version,
                snapshot.input_fingerprint,
                snapshot.snapshot_fingerprint,
                snapshot.scheduled_man_hours,
                snapshot.absence_man_hours,
                snapshot.break_man_hours,
                snapshot.unavailable_man_hours,
                snapshot.net_available_man_hours,
                snapshot.skill_feasible_man_hours,
                snapshot.skill_deficit_man_hours,
                snapshot.productivity_factor,
                snapshot.effective_man_hours,
                snapshot.scheduled_fte,
                snapshot.effective_capacity,
                json.dumps(
                    {key: str(value) for key, value in snapshot.skill_deficits.items()},
                    sort_keys=True,
                ),
                json.dumps(
                    {key: str(value) for key, value in snapshot.unused_worker_hours.items()},
                    sort_keys=True,
                ),
                json.dumps(list(snapshot.source_refs)),
                json.dumps(list(snapshot.contributors), sort_keys=True),
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id,input_fingerprint,effective_capacity,effective_man_hours,created_at
            FROM workforce_capacity_snapshots
            WHERE tenant_id=%s AND snapshot_fingerprint=%s
            """,
            (tenant, snapshot.snapshot_fingerprint),
        )
        row = cursor.fetchone()
        if row is None:
            raise CapacityPersistenceError("capacity snapshot persistence failed")
        if str(row[1]) != snapshot.input_fingerprint:
            raise CapacityPersistenceError("capacity snapshot fingerprint/input mismatch")
        database.commit()
        return {
            "id": str(row[0]),
            "tenant_id": tenant,
            "input_fingerprint": str(row[1]),
            "snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "effective_capacity": Decimal(str(row[2])),
            "effective_man_hours": Decimal(str(row[3])),
            "created_at": row[4],
            "idempotent_replay": not inserted,
        }


def get_latest_capacity_snapshot(location_id: str) -> dict[str, object] | None:
    if not location_id.strip():
        raise CapacityPersistenceError("location_id is required")
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT id,location_id,interval_start,interval_minutes,model_version,
                   input_fingerprint,snapshot_fingerprint,scheduled_man_hours,
                   absence_man_hours,break_man_hours,unavailable_man_hours,
                   net_available_man_hours,skill_feasible_man_hours,
                   skill_deficit_man_hours,productivity_factor,effective_man_hours,
                   scheduled_fte,effective_capacity,skill_deficits,unused_worker_hours,
                   source_refs,contributors,created_by,created_at
            FROM workforce_capacity_snapshots
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
        "id","location_id","interval_start","interval_minutes","model_version",
        "input_fingerprint","snapshot_fingerprint","scheduled_man_hours",
        "absence_man_hours","break_man_hours","unavailable_man_hours",
        "net_available_man_hours","skill_feasible_man_hours",
        "skill_deficit_man_hours","productivity_factor","effective_man_hours",
        "scheduled_fte","effective_capacity","skill_deficits","unused_worker_hours",
        "source_refs","contributors","created_by","created_at",
    )
    result = dict(zip(keys, row, strict=True))
    result["tenant_id"] = tenant
    for key in (
        "scheduled_man_hours","absence_man_hours","break_man_hours",
        "unavailable_man_hours","net_available_man_hours",
        "skill_feasible_man_hours","skill_deficit_man_hours","productivity_factor",
        "effective_man_hours","scheduled_fte","effective_capacity",
    ):
        result[key] = Decimal(str(result[key]))
    return result
