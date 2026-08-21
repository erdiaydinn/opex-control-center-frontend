from decimal import Decimal

import pytest

from .optimizer_authority import (
    OptimizationCandidate,
    OptimizerAuthorityError,
    OptimizerRequest,
    build_optimizer_proposal,
)


DPI_FP = "d" * 64


def candidate(
    candidate_id: str,
    *,
    action_type: str = "call_in",
    gain: str = "1",
    cost: int = 100,
    available: bool = True,
    legal: bool = True,
    skill_target: str | None = None,
) -> OptimizationCandidate:
    return OptimizationCandidate(
        candidate_id=candidate_id,
        action_type=action_type,
        capacity_gain_man_hours=Decimal(gain),
        incremental_cost_minor_units=cost,
        available=available,
        legal_eligible=legal,
        skill_target=skill_target,
        source_ref=f"availability://sanitized/{candidate_id}",
    )


def request(
    *,
    root_cause: str,
    manpower_shortage: bool,
    gap: str,
    skill_gap: str = "0",
    candidates: tuple[OptimizationCandidate, ...] = (),
    required_skill: str | None = None,
    budget: int = 10_000,
    max_actions: int = 4,
) -> OptimizerRequest:
    return OptimizerRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        model_version="workforce-optimizer-v1",
        dpi_snapshot_fingerprint=DPI_FP,
        root_cause=root_cause,
        manpower_shortage=manpower_shortage,
        capacity_gap_man_hours=Decimal(gap),
        skill_deficit_man_hours=Decimal(skill_gap),
        candidates=candidates,
        max_incremental_cost_minor_units=budget,
        max_actions=max_actions,
        required_skill=required_skill,
    )


def test_bad_kpi_execution_root_cause_never_becomes_staffing_proposal() -> None:
    proposal = build_optimizer_proposal(
        request(
            root_cause="execution_or_process",
            manpower_shortage=False,
            gap="0",
            candidates=(
                candidate("cheap-extra-person", gain="8", cost=1),
                candidate("extend", action_type="extend_shift", gain="8", cost=1),
            ),
        )
    )
    assert proposal.recommendation_type == "no_staffing_change"
    assert proposal.selected_candidate_ids == ()
    assert proposal.incremental_cost_minor_units == 0
    assert proposal.automatic_execution_permitted is False
    assert proposal.human_approval_required is False


def test_true_manpower_gap_selects_lowest_cost_feasible_combination() -> None:
    proposal = build_optimizer_proposal(
        request(
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            gap="2",
            candidates=(
                candidate("A", gain="1.5", cost=120),
                candidate("B", gain="0.5", cost=20),
                candidate("C", gain="2", cost=200),
                candidate("D", gain="1", cost=90),
            ),
        )
    )
    assert proposal.selected_candidate_ids == ("A", "B")
    assert proposal.covered_gap_man_hours == Decimal("2.0")
    assert proposal.remaining_gap_man_hours == Decimal("0")
    assert proposal.incremental_cost_minor_units == 140
    assert proposal.feasible is True
    assert proposal.automatic_execution_permitted is False
    assert proposal.human_approval_required is True


def test_skill_mix_constraint_filters_generic_and_wrong_skill_candidates() -> None:
    proposal = build_optimizer_proposal(
        request(
            root_cause="skill_mix_constraint",
            manpower_shortage=False,
            gap="1",
            skill_gap="1",
            required_skill="picking",
            candidates=(
                candidate("generic", action_type="call_in", gain="2", cost=1),
                candidate(
                    "wrong-skill",
                    action_type="skill_reassign",
                    gain="2",
                    cost=1,
                    skill_target="inbound",
                ),
                candidate(
                    "picker-transfer",
                    action_type="skill_reassign",
                    gain="1",
                    cost=50,
                    skill_target="picking",
                ),
            ),
        )
    )
    assert proposal.recommendation_type == "skill_targeted_capacity_proposal"
    assert proposal.selected_candidate_ids == ("picker-transfer",)
    assert proposal.feasible is True
    assert proposal.automatic_execution_permitted is False


def test_unavailable_illegal_and_over_budget_candidates_are_not_selected() -> None:
    proposal = build_optimizer_proposal(
        request(
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            gap="1",
            budget=100,
            candidates=(
                candidate("unavailable", gain="5", cost=1, available=False),
                candidate("illegal", gain="5", cost=1, legal=False),
                candidate("expensive", gain="5", cost=101),
                candidate("valid", gain="1", cost=100),
            ),
        )
    )
    assert proposal.selected_candidate_ids == ("valid",)
    assert proposal.incremental_cost_minor_units == 100


def test_infeasible_pool_reports_remaining_gap_instead_of_inventing_capacity() -> None:
    proposal = build_optimizer_proposal(
        request(
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            gap="3",
            candidates=(candidate("A", gain="1", cost=10),),
        )
    )
    assert proposal.covered_gap_man_hours == Decimal("1")
    assert proposal.remaining_gap_man_hours == Decimal("2")
    assert proposal.feasible is False
    assert proposal.automatic_execution_permitted is False


def test_candidate_order_is_deterministic() -> None:
    a = candidate("A", gain="1", cost=50)
    b = candidate("B", gain="1", cost=50)
    left = build_optimizer_proposal(
        request(
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            gap="2",
            candidates=(a, b),
        )
    )
    right = build_optimizer_proposal(
        request(
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            gap="2",
            candidates=(b, a),
        )
    )
    assert left.input_fingerprint == right.input_fingerprint
    assert left.proposal_fingerprint == right.proposal_fingerprint
    assert left.selected_candidate_ids == right.selected_candidate_ids == ("A", "B")


def test_inconsistent_manpower_root_cause_fails_closed() -> None:
    with pytest.raises(OptimizerAuthorityError, match="requires manpower_shortage=true"):
        build_optimizer_proposal(
            request(
                root_cause="manpower_capacity_shortage",
                manpower_shortage=False,
                gap="1",
                candidates=(candidate("A"),),
            )
        )


def test_skill_constraint_requires_required_skill() -> None:
    with pytest.raises(OptimizerAuthorityError, match="requires required_skill"):
        request(
            root_cause="skill_mix_constraint",
            manpower_shortage=False,
            gap="1",
            skill_gap="1",
        )
