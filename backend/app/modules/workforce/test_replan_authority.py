from decimal import Decimal

import pytest

from .replan_authority import (
    CostAssumption,
    KpiSensitivity,
    ReplanAuthorityError,
    ReplanBaseline,
    ReplanScenarioRequest,
    ScenarioShock,
    build_replan_scenario,
)


BASELINE_DPI = Decimal("10") / Decimal("10.7")


def baseline() -> ReplanBaseline:
    return ReplanBaseline(
        demand_snapshot_fingerprint="a" * 64,
        capacity_snapshot_fingerprint="b" * 64,
        dpi_snapshot_fingerprint="c" * 64,
        optimizer_proposal_fingerprint="d" * 64,
        required_man_hours=Decimal("10"),
        effective_man_hours=Decimal("10.7"),
        demand_pressure_index=BASELINE_DPI,
        current_optimizer_cost_minor_units=0,
    )


def request(*shocks: ScenarioShock) -> ReplanScenarioRequest:
    return ReplanScenarioRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        model_version="workforce-replan-v1",
        baseline=baseline(),
        shocks=tuple(shocks),
        kpi_sensitivities=(
            KpiSensitivity(
                kpi_key="picking_seconds_per_order",
                delta_per_dpi_point=Decimal("100"),
                model_version="kpi-sensitivity-v1",
                source_ref="model://sanitized/picking-sensitivity-v1",
            ),
            KpiSensitivity(
                kpi_key="otp_4_25_pct",
                delta_per_dpi_point=Decimal("-8"),
                model_version="kpi-sensitivity-v1",
                source_ref="model://sanitized/otp-sensitivity-v1",
            ),
        ),
        cost_assumption=CostAssumption(
            incremental_cost_minor_units_per_man_hour=Decimal("1000"),
            model_version="labor-cost-v1",
            source_ref="cost://sanitized/labor-v1",
        ),
    )


def test_absence_what_if_returns_recommendation_kpi_and_cost_delta() -> None:
    scenario = build_replan_scenario(
        request(
            ScenarioShock(
                shock_id="absence-1",
                shock_type="absence",
                capacity_loss_man_hours=Decimal("1"),
                source_ref="scenario://absence/E11",
            )
        )
    )
    assert scenario.scenario_required_man_hours == Decimal("10")
    assert scenario.scenario_effective_man_hours == Decimal("9.7")
    assert scenario.scenario_gap_man_hours == Decimal("0.3")
    assert scenario.recommendation == "rerun_constraint_optimizer_for_capacity_loss"
    assert scenario.replan_required is True
    assert scenario.cost_delta_minor_units == 300
    assert scenario.predicted_kpi_deltas["picking_seconds_per_order"] > Decimal("0")
    assert scenario.predicted_kpi_deltas["otp_4_25_pct"] < Decimal("0")
    assert scenario.automatic_apply_permitted is False
    assert scenario.human_approval_required is True


def test_order_spike_what_if_increases_required_mh_and_cost() -> None:
    scenario = build_replan_scenario(
        request(
            ScenarioShock(
                shock_id="orders-1",
                shock_type="order_spike",
                demand_delta_man_hours=Decimal("2"),
                source_ref="scenario://orders/+20pct",
            )
        )
    )
    assert scenario.scenario_required_man_hours == Decimal("12")
    assert scenario.scenario_effective_man_hours == Decimal("10.7")
    assert scenario.scenario_gap_man_hours == Decimal("1.3")
    assert scenario.cost_delta_minor_units == 1300
    assert scenario.recommendation == "rerun_constraint_optimizer_for_demand_spike"
    assert scenario.predicted_kpi_deltas["picking_seconds_per_order"] > Decimal("0")


def test_inbound_delay_what_if_returns_resequence_recommendation() -> None:
    scenario = build_replan_scenario(
        request(
            ScenarioShock(
                shock_id="inbound-1",
                shock_type="inbound_delay",
                demand_delta_man_hours=Decimal("1.5"),
                source_ref="scenario://inbound/delay-90m",
            )
        )
    )
    assert scenario.scenario_gap_man_hours == Decimal("0.8")
    assert scenario.cost_delta_minor_units == 800
    assert scenario.recommendation == "resequence_intraday_work_and_rerun_optimizer"
    assert scenario.replan_required is True


def test_scenario_order_is_deterministic() -> None:
    a = ScenarioShock(
        shock_id="a",
        shock_type="absence",
        capacity_loss_man_hours=Decimal("0.5"),
        source_ref="scenario://absence/a",
    )
    b = ScenarioShock(
        shock_id="b",
        shock_type="order_spike",
        demand_delta_man_hours=Decimal("0.5"),
        source_ref="scenario://orders/b",
    )
    left = build_replan_scenario(request(a, b))
    right = build_replan_scenario(request(b, a))
    assert left.input_fingerprint == right.input_fingerprint
    assert left.scenario_fingerprint == right.scenario_fingerprint


def test_kpi_predictions_are_explicit_scenario_estimates_not_observed_truth() -> None:
    scenario = build_replan_scenario(
        request(
            ScenarioShock(
                shock_id="orders",
                shock_type="order_spike",
                demand_delta_man_hours=Decimal("1"),
                source_ref="scenario://orders",
            )
        )
    )
    assert scenario.assumptions["predictions_are_scenario_estimates_not_observed_kpis"] is True
    sensitivities = scenario.assumptions["kpi_sensitivities"]
    assert all(item["source_ref"].startswith("model://sanitized/") for item in sensitivities)


def test_scenario_never_allows_automatic_apply() -> None:
    scenario = build_replan_scenario(
        request(
            ScenarioShock(
                shock_id="huge",
                shock_type="order_spike",
                demand_delta_man_hours=Decimal("100"),
                source_ref="scenario://orders/huge",
            )
        )
    )
    assert scenario.automatic_apply_permitted is False
    assert scenario.human_approval_required is True


def test_invalid_unproven_shock_and_duplicate_ids_fail_closed() -> None:
    with pytest.raises(ReplanAuthorityError, match="source_ref"):
        ScenarioShock(
            shock_id="bad",
            shock_type="absence",
            capacity_loss_man_hours=Decimal("1"),
            source_ref="",
        )
    duplicated = ScenarioShock(
        shock_id="same",
        shock_type="order_spike",
        demand_delta_man_hours=Decimal("1"),
        source_ref="scenario://orders/same",
    )
    with pytest.raises(ReplanAuthorityError, match="shock ids must be unique"):
        request(duplicated, duplicated)
