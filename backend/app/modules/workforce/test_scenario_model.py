from decimal import Decimal

from app.modules.workforce.pressure_model import EffectiveCapacityInput, OperationalStrain
from app.modules.workforce.scenario_model import ReplanAction, ScenarioInput, recommend_replan


def test_reallocate_before_adding_labor_when_safe_capacity_exists():
    result = recommend_replan(
        ScenarioInput(
            required_man_hours=Decimal("12"),
            capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("9")),
            strain=OperationalStrain(backlog=Decimal("0.4"), kpi=Decimal("0.4")),
            transferable_man_hours=Decimal("2"),
        )
    )
    assert result.action is ReplanAction.REALLOCATE_CAPACITY
    assert result.transferable_man_hours_used == Decimal("2")
    assert result.residual_gap_man_hours == Decimal("1")
    assert result.human_approval_required is True


def test_policy_eligible_work_can_be_deferred_but_not_silently_executed():
    result = recommend_replan(
        ScenarioInput(
            required_man_hours=Decimal("10"),
            capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("8")),
            strain=OperationalStrain(),
            deferrable_man_hours=Decimal("2"),
        )
    )
    assert result.action is ReplanAction.DEFER_NON_CRITICAL_WORK
    assert result.residual_gap_man_hours == Decimal("0")
    assert result.human_approval_required is True


def test_bad_kpi_with_enough_capacity_recommends_process_investigation_not_more_people():
    result = recommend_replan(
        ScenarioInput(
            required_man_hours=Decimal("8"),
            capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("10")),
            strain=OperationalStrain(kpi=Decimal("0.9")),
            transferable_man_hours=Decimal("5"),
        )
    )
    assert result.action is ReplanAction.INVESTIGATE_PROCESS
    assert result.commentary_code == "capacity_sufficient_replanning_not_primary_fix"


def test_stable_depot_requires_no_replan_or_human_action():
    result = recommend_replan(
        ScenarioInput(
            required_man_hours=Decimal("6"),
            capacity=EffectiveCapacityInput(scheduled_man_hours=Decimal("7")),
            strain=OperationalStrain(),
        )
    )
    assert result.action is ReplanAction.NO_CHANGE
    assert result.human_approval_required is False
