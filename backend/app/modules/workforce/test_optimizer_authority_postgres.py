from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .dpi_authority import DpiRequest, KpiObservation, build_dpi_snapshot
from .dpi_repository import persist_dpi_snapshot
from .optimizer_authority import OptimizationCandidate
from .optimizer_repository import get_latest_optimizer_proposal
from .optimizer_service import compute_and_persist_optimizer_proposal


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

AT = datetime(2026, 8, 17, 14, 0, tzinfo=timezone.utc)


def _persist_dpi(
    location_id: str,
    *,
    required: str,
    effective: str,
    skill_deficit: str = "0",
    bad_kpi: bool = True,
) -> str:
    kpis = (
        KpiObservation(
            key="picking_seconds_per_order",
            actual=Decimal("210" if bad_kpi else "100"),
            target=Decimal("120"),
            direction="lower_is_better",
            source_ref=f"kpi://sanitized/{location_id}/picking",
        ),
    )
    request = DpiRequest(
        tenant_id="tenant-a",
        location_id=location_id,
        interval_start=AT,
        model_version="workforce-dpi-v1",
        demand_snapshot_fingerprint=("a" if location_id.endswith("NO") else "c") * 64,
        capacity_snapshot_fingerprint=("b" if location_id.endswith("NO") else "d") * 64,
        required_man_hours=Decimal(required),
        effective_man_hours=Decimal(effective),
        skill_deficit_man_hours=Decimal(skill_deficit),
        kpis=kpis,
        demand_source_ref=f"workforce-demand://{location_id}",
        capacity_source_ref=f"workforce-capacity://{location_id}",
    )
    snapshot = build_dpi_snapshot(request)
    persist_dpi_snapshot(
        snapshot,
        kpi_observations=kpis,
        required_man_hours=request.required_man_hours,
        effective_man_hours=request.effective_man_hours,
        skill_deficit_man_hours=request.skill_deficit_man_hours,
        actor_subject="dpi-engine",
    )
    return snapshot.snapshot_fingerprint


def _candidate(candidate_id: str, gain: str, cost: int) -> OptimizationCandidate:
    return OptimizationCandidate(
        candidate_id=candidate_id,
        action_type="call_in",
        capacity_gain_man_hours=Decimal(gain),
        incremental_cost_minor_units=cost,
        source_ref=f"availability://sanitized/{candidate_id}",
    )


def test_execution_root_cause_from_database_blocks_staffing_even_with_cheap_candidate() -> None:
    dpi_fp = _persist_dpi("WH-OPT-NO", required="10", effective="10.7")
    proposal, receipt = compute_and_persist_optimizer_proposal(
        location_id="WH-OPT-NO",
        candidates=(_candidate("CHEAP", "8", 1),),
        max_incremental_cost_minor_units=10_000,
        actor_subject="optimizer-engine",
    )

    assert proposal.dpi_snapshot_fingerprint == dpi_fp
    assert proposal.recommendation_type == "no_staffing_change"
    assert proposal.selected_candidate_ids == ()
    assert proposal.automatic_execution_permitted is False
    assert receipt["idempotent_replay"] is False

    replay, replay_receipt = compute_and_persist_optimizer_proposal(
        location_id="WH-OPT-NO",
        candidates=(_candidate("CHEAP", "8", 1),),
        max_incremental_cost_minor_units=10_000,
        actor_subject="optimizer-engine",
    )
    assert replay == proposal
    assert replay_receipt["idempotent_replay"] is True

    latest = get_latest_optimizer_proposal("WH-OPT-NO")
    assert latest is not None
    assert latest["recommendation_type"] == "no_staffing_change"
    assert latest["automatic_execution_permitted"] is False


def test_governed_manpower_gap_selects_feasible_low_cost_proposal_without_execution() -> None:
    _persist_dpi("WH-OPT-GAP", required="10", effective="8")
    proposal, receipt = compute_and_persist_optimizer_proposal(
        location_id="WH-OPT-GAP",
        candidates=(
            _candidate("A", "1.5", 120),
            _candidate("B", "0.5", 20),
            _candidate("C", "2", 200),
        ),
        max_incremental_cost_minor_units=1_000,
        actor_subject="optimizer-engine",
    )

    assert proposal.recommendation_type == "capacity_gap_proposal"
    assert proposal.selected_candidate_ids == ("A", "B")
    assert proposal.remaining_gap_man_hours == Decimal("0")
    assert proposal.incremental_cost_minor_units == 140
    assert proposal.feasible is True
    assert proposal.automatic_execution_permitted is False
    assert proposal.human_approval_required is True
    assert receipt["automatic_execution_permitted"] is False
