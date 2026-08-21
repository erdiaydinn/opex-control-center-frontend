"""What-if and replanning recommendations layered on Workforce pressure truth.

This module never edits a roster. It produces auditable recommendations for a human
manager to accept/reject after legal, contractual, employee and local policy gates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from .pressure_model import EffectiveCapacityInput, OperationalStrain, evaluate_depot_pressure

ZERO = Decimal("0")


class ReplanAction(StrEnum):
    ADD_CAPACITY = "add_capacity"
    REALLOCATE_CAPACITY = "reallocate_capacity"
    DEFER_NON_CRITICAL_WORK = "defer_non_critical_work"
    INVESTIGATE_PROCESS = "investigate_process"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, slots=True)
class ScenarioInput:
    required_man_hours: Decimal
    capacity: EffectiveCapacityInput
    strain: OperationalStrain
    transferable_man_hours: Decimal = ZERO
    deferrable_man_hours: Decimal = ZERO

    def __post_init__(self) -> None:
        if self.transferable_man_hours < ZERO or self.deferrable_man_hours < ZERO:
            raise ValueError("scenario capacity/workload adjustments cannot be negative")


@dataclass(frozen=True, slots=True)
class ScenarioRecommendation:
    action: ReplanAction
    baseline_gap_man_hours: Decimal
    residual_gap_man_hours: Decimal
    transferable_man_hours_used: Decimal
    deferred_man_hours_used: Decimal
    human_approval_required: bool
    commentary_code: str


def recommend_replan(scenario: ScenarioInput) -> ScenarioRecommendation:
    baseline = evaluate_depot_pressure(
        required_man_hours=scenario.required_man_hours,
        capacity=scenario.capacity,
        strain=scenario.strain,
    )

    if not baseline.manpower_shortage_detected:
        if scenario.strain.kpi >= Decimal("0.6") or scenario.strain.backlog >= Decimal("0.6"):
            return ScenarioRecommendation(
                action=ReplanAction.INVESTIGATE_PROCESS,
                baseline_gap_man_hours=baseline.capacity_gap_man_hours,
                residual_gap_man_hours=ZERO,
                transferable_man_hours_used=ZERO,
                deferred_man_hours_used=ZERO,
                human_approval_required=True,
                commentary_code="capacity_sufficient_replanning_not_primary_fix",
            )
        return ScenarioRecommendation(
            action=ReplanAction.NO_CHANGE,
            baseline_gap_man_hours=baseline.capacity_gap_man_hours,
            residual_gap_man_hours=ZERO,
            transferable_man_hours_used=ZERO,
            deferred_man_hours_used=ZERO,
            human_approval_required=False,
            commentary_code="no_replan_required",
        )

    gap = baseline.capacity_gap_man_hours
    transferable = min(gap, scenario.transferable_man_hours)
    gap -= transferable
    deferred = min(gap, scenario.deferrable_man_hours)
    gap -= deferred

    if transferable > ZERO:
        action = ReplanAction.REALLOCATE_CAPACITY
        commentary = "reallocate_eligible_capacity_before_adding_labor"
    elif deferred > ZERO:
        action = ReplanAction.DEFER_NON_CRITICAL_WORK
        commentary = "defer_policy_eligible_work_before_adding_labor"
    else:
        action = ReplanAction.ADD_CAPACITY
        commentary = "capacity_gap_remains_after_safe_internal_options"

    if gap > ZERO and (transferable > ZERO or deferred > ZERO):
        commentary = "internal_replan_reduces_but_does_not_close_capacity_gap"

    return ScenarioRecommendation(
        action=action,
        baseline_gap_man_hours=baseline.capacity_gap_man_hours,
        residual_gap_man_hours=max(ZERO, gap),
        transferable_man_hours_used=transferable,
        deferred_man_hours_used=deferred,
        human_approval_required=True,
        commentary_code=commentary,
    )
