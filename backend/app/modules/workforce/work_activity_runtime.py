"""Persistence-backed runtime adapter for generic Workforce activity demand.

The adapter resolves tenant-approved effective activity and labor-standard rows,
then delegates calculation to the deterministic work-activity demand authority.
It never falls back to starter templates or guessed timings.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from . import persistence
from .work_activity_authority import (
    ActivityLaborStandardVersion,
    WorkActivityDemandRequest,
    WorkActivityDemandSnapshot,
    WorkActivityVersion,
    WorkloadSignal,
    build_work_activity_demand_snapshot,
)
from .work_activity_catalog import WorkActivityCatalogError, resolve_catalog_activity
from .work_activity_labor_catalog import ActivityLaborCatalogError, resolve_labor_standard


class WorkActivityRuntimeError(ValueError):
    """Raised when runtime demand cannot be built from governed authority."""


def _activity(row: dict) -> WorkActivityVersion:
    return WorkActivityVersion(
        tenant_id=str(row["tenant_id"]),
        activity_key=str(row["activity_key"]),
        version=int(row["version"]),
        display_name=str(row["display_name"]),
        category=str(row["category"]),
        unit_key=str(row["unit_key"]),
        demand_mode=str(row["demand_mode"]),
        effective_from=datetime.fromisoformat(str(row["effective_from"])),
        effective_until=datetime.fromisoformat(str(row["effective_until"])) if row.get("effective_until") else None,
        source_ref=str(row["source_ref"]),
        approved_by=str(row["approved_by"]),
        required_skill_keys=tuple(row.get("required_skill_keys") or ()),
        required_certification_keys=tuple(row.get("required_certification_keys") or ()),
        required_equipment_keys=tuple(row.get("required_equipment_keys") or ()),
        safety_tags=tuple(row.get("safety_tags") or ()),
        location_types=tuple(row.get("location_types") or ()),
        status=str(row.get("status") or "APPROVED"),
    )


def _labor(row: dict) -> ActivityLaborStandardVersion:
    return ActivityLaborStandardVersion(
        tenant_id=str(row["tenant_id"]),
        activity_key=str(row["activity_key"]),
        version=int(row["version"]),
        seconds_per_unit=Decimal(str(row["seconds_per_unit"])),
        people=Decimal(str(row["people"])),
        effective_from=datetime.fromisoformat(str(row["effective_from"])),
        effective_until=datetime.fromisoformat(str(row["effective_until"])) if row.get("effective_until") else None,
        source_ref=str(row["source_ref"]),
        approved_by=str(row["approved_by"]),
        status=str(row.get("status") or "APPROVED"),
    )


def _validate_worksite_compatibility(worksite_id: str, activity_rows: dict[str, dict]) -> None:
    constrained = [row for row in activity_rows.values() if row.get("location_types")]
    if not constrained:
        return

    # Lazy import avoids creating a module initialization cycle with the
    # canonical Employee Master / worksite service.
    from . import service

    worksite = next(
        (row for row in service.list_warehouses() if str(row.get("id")) == str(worksite_id)),
        None,
    )
    if worksite is None:
        raise WorkActivityRuntimeError("Governed worksite was not found for activity demand.")
    location_type = str(worksite.get("location_type") or "").strip()
    if not location_type:
        raise WorkActivityRuntimeError(
            "Worksite classification is required before constrained activity demand can run."
        )

    incompatible = [
        str(row["activity_key"])
        for row in constrained
        if location_type not in {str(value) for value in row.get("location_types") or []}
    ]
    if incompatible:
        raise WorkActivityRuntimeError(
            "Worksite type is not eligible for activities: " + ", ".join(sorted(incompatible))
        )


def build_catalog_demand_snapshot(
    *,
    worksite_id: str,
    interval_start: datetime,
    interval_minutes: int,
    model_version: str,
    signals: list[dict],
) -> WorkActivityDemandSnapshot:
    if interval_start.tzinfo is None or interval_start.utcoffset() is None:
        raise WorkActivityRuntimeError("interval_start must be timezone-aware")
    tenant_id = persistence.tenant_id()
    day = interval_start.date().isoformat()
    activity_rows: dict[str, dict] = {}
    labor_rows: dict[str, dict] = {}
    workload_signals: list[WorkloadSignal] = []

    for payload in signals:
        key = str(payload["activity_key"])
        if key not in activity_rows:
            try:
                activity_rows[key] = resolve_catalog_activity(key, day)
                labor_rows[key] = resolve_labor_standard(key, day)
            except (WorkActivityCatalogError, ActivityLaborCatalogError) as error:
                raise WorkActivityRuntimeError(str(error)) from error
        workload_signals.append(
            WorkloadSignal(
                driver_key=str(payload["driver_key"]),
                activity_key=key,
                demand_mode=str(payload["demand_mode"]),
                quantity=Decimal(str(payload["quantity"])),
                source_ref=str(payload["source_ref"]),
            )
        )

    _validate_worksite_compatibility(str(worksite_id), activity_rows)

    request = WorkActivityDemandRequest(
        tenant_id=tenant_id,
        location_id=str(worksite_id),
        interval_start=interval_start,
        interval_minutes=int(interval_minutes),
        model_version=str(model_version),
        signals=tuple(workload_signals),
    )
    return build_work_activity_demand_snapshot(
        request,
        tuple(_activity(row) for row in activity_rows.values()),
        tuple(_labor(row) for row in labor_rows.values()),
    )
