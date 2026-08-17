from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .capacity_authority import CapacityWorker, EffectiveCapacityRequest, build_effective_capacity_snapshot
from .capacity_repository import persist_capacity_snapshot
from .demand_authority import DemandSnapshot
from .demand_repository import persist_demand_snapshot
from .dpi_authority import DpiRequest, KpiObservation, build_dpi_snapshot
from .dpi_repository import persist_dpi_snapshot
from .optimizer_authority import OptimizationCandidate
from .optimizer_service import compute_and_persist_optimizer_proposal
from .replan_authority import ScenarioShock
from .replan_repository import get_latest_replan_scenario
from .replan_service import compute_and_persist_replan_scenario


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

AT = datetime(2026, 8, 17, 15, 0, tzinfo=timezone.utc)
LOCATION = "WH-RPL-001"
MODEL_VERSION = "workforce-replan-v1"


def _seed_baseline_chain() -> None:
    demand = DemandSnapshot(
        tenant_id="tenant-a",
        location_id=LOCATION,
        interval_start=AT,
        interval_minutes=60,
        model_version="workforce-demand-v1",
        input_fingerprint="1" * 64,
        snapshot_fingerprint="2" * 64,
        base_man_hours=Decimal("10"),
        overhead_man_hours=Decimal("0"),
        required_man_hours=Decimal("10"),
        required_people=Decimal("10"),
        contributions=(),
        labor_standard_refs=(),
    )
    persist_demand_snapshot(demand, actor_subject="demand-engine")

    capacity = build_effective_capacity_snapshot(
        EffectiveCapacityRequest(
            tenant_id="tenant-a",
            location_id=LOCATION,
            interval_start=AT,
            interval_minutes=60,
            model_version="workforce-capacity-v1",
            workers=tuple(
                CapacityWorker(
                    employee_id=f"RPL-E{i:02d}",
                    scheduled_hours=Decimal("1"),
                    skills=frozenset({"picking"}),
                    source_ref=f"roster://sanitized/RPL-E{i:02d}",
                )
                for i in range(1, 11)
            )
            + (
                CapacityWorker(
                    employee_id="RPL-E11",
                    scheduled_hours=Decimal("0.7"),
                    skills=frozenset({"picking"}),
                    source_ref="roster://sanitized/RPL-E11",
                ),
            ),
            source_refs=("schedule://sanitized/WH-RPL-001",),
        )
    )
    persist_capacity_snapshot(capacity, actor_subject="capacity-engine")

    kpis = (
        KpiObservation(
            key="picking_seconds_per_order",
            actual=Decimal("210"),
            target=Decimal("120"),
            direction="lower_is_better",
            source_ref="kpi://sanitized/WH-RPL-001/picking",
        ),
    )
    dpi_request = DpiRequest(
        tenant_id="tenant-a",
        location_id=LOCATION,
        interval_start=AT,
        model_version="workforce-dpi-v1",
        demand_snapshot_fingerprint=demand.snapshot_fingerprint,
        capacity_snapshot_fingerprint=capacity.snapshot_fingerprint,
        required_man_hours=Decimal("10"),
        effective_man_hours=Decimal("10.7"),
        skill_deficit_man_hours=Decimal("0"),
        kpis=kpis,
        demand_source_ref="workforce-demand://WH-RPL-001",
        capacity_source_ref="workforce-capacity://WH-RPL-001",
    )
    dpi = build_dpi_snapshot(dpi_request)
    persist_dpi_snapshot(
        dpi,
        kpi_observations=kpis,
        required_man_hours=dpi_request.required_man_hours,
        effective_man_hours=dpi_request.effective_man_hours,
        skill_deficit_man_hours=dpi_request.skill_deficit_man_hours,
        actor_subject="dpi-engine",
    )
    compute_and_persist_optimizer_proposal(
        location_id=LOCATION,
        candidates=(
            OptimizationCandidate(
                candidate_id="SHOULD-NOT-BE-USED",
                action_type="call_in",
                capacity_gain_man_hours=Decimal("8"),
                incremental_cost_minor_units=1,
                source_ref="availability://sanitized/cheap",
            ),
        ),
        max_incremental_cost_minor_units=10_000,
        actor_subject="optimizer-engine",
    )


def test_absence_scenario_uses_governed_baseline_and_approved_model() -> None:
    _seed_baseline_chain()
    shock = ScenarioShock(
        shock_id="absence-rpl",
        shock_type="absence",
        capacity_loss_man_hours=Decimal("1"),
        source_ref="scenario://absence/RPL-E11",
    )
    scenario, receipt = compute_and_persist_replan_scenario(
        location_id=LOCATION,
        model_version=MODEL_VERSION,
        shocks=(shock,),
        actor_subject="manager-a",
    )

    assert scenario.baseline_required_man_hours == Decimal("10")
    assert scenario.baseline_effective_man_hours == Decimal("10.7")
    assert scenario.scenario_effective_man_hours == Decimal("9.7")
    assert scenario.scenario_gap_man_hours == Decimal("0.3")
    assert scenario.recommendation == "rerun_constraint_optimizer_for_capacity_loss"
    assert scenario.cost_delta_minor_units == 300
    assert scenario.predicted_kpi_deltas["picking_seconds_per_order"] > Decimal("0")
    assert scenario.automatic_apply_permitted is False
    assert receipt["automatic_apply_permitted"] is False
    assert receipt["scenario_idempotent_replay"] is False

    replay, replay_receipt = compute_and_persist_replan_scenario(
        location_id=LOCATION,
        model_version=MODEL_VERSION,
        shocks=(shock,),
        actor_subject="manager-a",
    )
    assert replay == scenario
    assert replay_receipt["scenario_idempotent_replay"] is True
    assert replay_receipt["proposal_idempotent_replay"] is True

    latest = get_latest_replan_scenario(LOCATION)
    assert latest is not None
    assert latest["scenario_gap_man_hours"] == Decimal("0.3")
    assert latest["cost_delta_minor_units"] == 300
    assert latest["automatic_apply_permitted"] is False
