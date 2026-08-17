"""Tenant-bound persistence for Workforce demand authority (roadmap 11/60).

This adapter reuses the canonical Workforce PostgreSQL connection and tenant
binding. It never accepts a database tenant override from request data: a demand
request must match the tenant bound to the runtime identity, and FORCE RLS is the
final authority.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import hashlib
import json

from . import persistence
from .demand_authority import (
    DemandAuthorityError,
    DemandRequest,
    DemandSnapshot,
    LaborStandardVersion,
    build_demand_snapshot,
)


class DemandPersistenceError(RuntimeError):
    pass


def _decimal_text(value: Decimal) -> str:
    if value == Decimal("0"):
        return "0"
    text = format(value.normalize(), "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _standard_fingerprint(standard: LaborStandardVersion) -> str:
    payload = {
        "activity": standard.activity,
        "version": standard.version,
        "seconds_per_unit": _decimal_text(standard.seconds_per_unit),
        "people": _decimal_text(standard.people),
        "effective_from": standard.effective_from.isoformat(),
        "effective_until": (
            standard.effective_until.isoformat() if standard.effective_until else None
        ),
        "status": standard.status,
        "source_ref": standard.source_ref,
        "approved_by": standard.approved_by,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _require_v33_schema(cursor) -> None:
    cursor.execute(
        """
        SELECT
          to_regclass('public.workforce_labor_standard_versions') IS NOT NULL,
          to_regclass('public.workforce_demand_snapshots') IS NOT NULL
        """
    )
    labor_exists, snapshot_exists = cursor.fetchone()
    if not labor_exists or not snapshot_exists:
        raise DemandPersistenceError(
            "Workforce V33 demand schema is missing; apply versioned migration 010 before demand execution"
        )


def _enter_tenant(cursor) -> str:
    configured = persistence.tenant_id()
    cursor.execute("SELECT set_config('app.workforce_tenant', %s, true)", (configured,))
    cursor.execute("SELECT workforce_current_tenant()")
    bound = cursor.fetchone()[0]
    if not bound or str(bound) != configured:
        raise DemandPersistenceError(
            "runtime database identity is not bound to the configured Workforce tenant"
        )
    _require_v33_schema(cursor)
    return configured


def register_labor_standard(standard: LaborStandardVersion) -> dict[str, object]:
    """Append an approved standard or return an exact idempotent replay."""

    fingerprint = _standard_fingerprint(standard)
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            INSERT INTO workforce_labor_standard_versions (
              tenant_id, activity, version, seconds_per_unit, people,
              effective_from, effective_until, status, source_ref, approved_by,
              authority_fingerprint
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (tenant_id, activity, version) DO NOTHING
            """,
            (
                tenant,
                standard.activity,
                standard.version,
                standard.seconds_per_unit,
                standard.people,
                standard.effective_from,
                standard.effective_until,
                standard.status,
                standard.source_ref,
                standard.approved_by,
                fingerprint,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT authority_fingerprint, created_at
            FROM workforce_labor_standard_versions
            WHERE tenant_id=%s AND activity=%s AND version=%s
            """,
            (tenant, standard.activity, standard.version),
        )
        row = cursor.fetchone()
        if row is None or str(row[0]) != fingerprint:
            raise DemandPersistenceError(
                "labor-standard version already exists with different immutable authority"
            )
        database.commit()
        return {
            "tenant_id": tenant,
            "activity": standard.activity,
            "version": standard.version,
            "authority_fingerprint": fingerprint,
            "created_at": row[1],
            "idempotent_replay": not inserted,
        }


def load_effective_labor_standards(
    *,
    at: datetime,
    activities: tuple[str, ...],
) -> tuple[LaborStandardVersion, ...]:
    if not activities:
        return ()
    unique = tuple(sorted(set(activities)))
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        cursor.execute(
            """
            SELECT activity, version, seconds_per_unit, people, effective_from,
                   effective_until, source_ref, approved_by, status
            FROM workforce_labor_standard_versions
            WHERE tenant_id=%s
              AND activity=ANY(%s)
              AND status='approved'
              AND effective_from <= %s
              AND (effective_until IS NULL OR %s < effective_until)
            ORDER BY activity, version
            """,
            (tenant, list(unique), at, at),
        )
        rows = cursor.fetchall()
    return tuple(
        LaborStandardVersion(
            activity=str(row[0]),
            version=int(row[1]),
            seconds_per_unit=Decimal(str(row[2])),
            people=Decimal(str(row[3])),
            effective_from=row[4],
            effective_until=row[5],
            source_ref=str(row[6]),
            approved_by=str(row[7]),
            status=str(row[8]),
        )
        for row in rows
    )


def persist_demand_snapshot(
    snapshot: DemandSnapshot,
    *,
    actor_subject: str,
) -> dict[str, object]:
    if not actor_subject.strip():
        raise DemandPersistenceError("actor_subject is required")
    demand_id = f"DEM-{snapshot.snapshot_fingerprint[:24]}"
    with persistence.connection() as database, database.cursor() as cursor:
        tenant = _enter_tenant(cursor)
        if snapshot.tenant_id != tenant:
            raise DemandPersistenceError(
                "demand snapshot tenant does not match runtime tenant authority"
            )
        cursor.execute(
            """
            INSERT INTO workforce_demand_snapshots (
              tenant_id, id, location_id, interval_start, interval_minutes,
              model_version, input_fingerprint, snapshot_fingerprint,
              base_man_hours, overhead_man_hours, required_man_hours,
              required_people, labor_standard_refs, contributors, created_by
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s
            )
            ON CONFLICT (tenant_id, snapshot_fingerprint) DO NOTHING
            """,
            (
                tenant,
                demand_id,
                snapshot.location_id,
                snapshot.interval_start,
                snapshot.interval_minutes,
                snapshot.model_version,
                snapshot.input_fingerprint,
                snapshot.snapshot_fingerprint,
                snapshot.base_man_hours,
                snapshot.overhead_man_hours,
                snapshot.required_man_hours,
                snapshot.required_people,
                json.dumps(list(snapshot.labor_standard_refs)),
                json.dumps(
                    [item.canonical() for item in snapshot.contributions],
                    sort_keys=True,
                ),
                actor_subject,
            ),
        )
        inserted = cursor.rowcount == 1
        cursor.execute(
            """
            SELECT id, input_fingerprint, required_man_hours, required_people,
                   created_at
            FROM workforce_demand_snapshots
            WHERE tenant_id=%s AND snapshot_fingerprint=%s
            """,
            (tenant, snapshot.snapshot_fingerprint),
        )
        row = cursor.fetchone()
        if row is None:
            raise DemandPersistenceError("demand snapshot persistence failed")
        if str(row[1]) != snapshot.input_fingerprint:
            raise DemandPersistenceError("snapshot fingerprint/input mismatch")
        database.commit()
        return {
            "id": str(row[0]),
            "tenant_id": tenant,
            "input_fingerprint": str(row[1]),
            "snapshot_fingerprint": snapshot.snapshot_fingerprint,
            "required_man_hours": Decimal(str(row[2])),
            "required_people": Decimal(str(row[3])),
            "created_at": row[4],
            "idempotent_replay": not inserted,
        }


def build_and_persist_demand(
    request: DemandRequest,
    *,
    actor_subject: str,
) -> tuple[DemandSnapshot, dict[str, object]]:
    runtime_tenant = persistence.tenant_id()
    if request.tenant_id != runtime_tenant:
        raise DemandAuthorityError(
            "demand request tenant does not match server-authoritative Workforce tenant"
        )
    activities = tuple(
        driver.activity for driver in request.drivers if driver.volume > Decimal("0")
    )
    standards = load_effective_labor_standards(
        at=request.interval_start,
        activities=activities,
    )
    snapshot = build_demand_snapshot(request, standards)
    receipt = persist_demand_snapshot(snapshot, actor_subject=actor_subject)
    return snapshot, receipt
