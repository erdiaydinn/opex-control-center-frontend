"""Internal DPI service that resolves governed demand/capacity before classify."""

from __future__ import annotations

from .dpi_authority import DpiRequest, DpiSnapshot, KpiObservation, build_dpi_snapshot
from .dpi_repository import (
    load_latest_governed_pressure_inputs,
    persist_dpi_snapshot,
)


def compute_and_persist_dpi(
    *,
    location_id: str,
    kpi_observations: tuple[KpiObservation, ...],
    actor_subject: str,
    model_version: str = "workforce-dpi-v1",
) -> tuple[DpiSnapshot, dict[str, object]]:
    """Classify pressure from immutable Workforce authority, never browser MH."""

    inputs = load_latest_governed_pressure_inputs(location_id)
    request = DpiRequest(
        tenant_id=str(inputs["tenant_id"]),
        location_id=str(inputs["location_id"]),
        interval_start=inputs["interval_start"],
        model_version=model_version,
        demand_snapshot_fingerprint=str(inputs["demand_snapshot_fingerprint"]),
        capacity_snapshot_fingerprint=str(inputs["capacity_snapshot_fingerprint"]),
        required_man_hours=inputs["required_man_hours"],
        effective_man_hours=inputs["effective_man_hours"],
        skill_deficit_man_hours=inputs["skill_deficit_man_hours"],
        kpis=kpi_observations,
        demand_source_ref=str(inputs["demand_source_ref"]),
        capacity_source_ref=str(inputs["capacity_source_ref"]),
    )
    snapshot = build_dpi_snapshot(request)
    receipt = persist_dpi_snapshot(
        snapshot,
        kpi_observations=kpi_observations,
        required_man_hours=request.required_man_hours,
        effective_man_hours=request.effective_man_hours,
        skill_deficit_man_hours=request.skill_deficit_man_hours,
        actor_subject=actor_subject,
    )
    return snapshot, receipt
