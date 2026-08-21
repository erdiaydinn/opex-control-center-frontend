"""Internal constraint-aware optimizer service for roadmap 14/60."""

from __future__ import annotations

from .optimizer_authority import (
    OptimizationCandidate,
    OptimizerProposal,
    OptimizerRequest,
    build_optimizer_proposal,
)
from .optimizer_repository import (
    load_latest_governed_optimizer_input,
    persist_optimizer_proposal,
)


def compute_and_persist_optimizer_proposal(
    *,
    location_id: str,
    candidates: tuple[OptimizationCandidate, ...],
    max_incremental_cost_minor_units: int,
    actor_subject: str,
    required_skill: str | None = None,
    max_actions: int = 4,
    model_version: str = "workforce-optimizer-v1",
) -> tuple[OptimizerProposal, dict[str, object]]:
    """Resolve immutable DPI truth before evaluating trusted candidate capacity."""

    dpi = load_latest_governed_optimizer_input(location_id)
    request = OptimizerRequest(
        tenant_id=str(dpi["tenant_id"]),
        location_id=str(dpi["location_id"]),
        model_version=model_version,
        dpi_snapshot_fingerprint=str(dpi["dpi_snapshot_fingerprint"]),
        root_cause=str(dpi["root_cause"]),
        manpower_shortage=bool(dpi["manpower_shortage"]),
        capacity_gap_man_hours=dpi["capacity_gap_man_hours"],
        skill_deficit_man_hours=dpi["skill_deficit_man_hours"],
        candidates=candidates,
        max_incremental_cost_minor_units=max_incremental_cost_minor_units,
        max_actions=max_actions,
        required_skill=required_skill,
    )
    proposal = build_optimizer_proposal(request)
    receipt = persist_optimizer_proposal(
        proposal,
        dpi_root_cause=request.root_cause,
        dpi_manpower_shortage=request.manpower_shortage,
        candidates=candidates,
        actor_subject=actor_subject,
    )
    return proposal, receipt
