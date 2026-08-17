from decimal import Decimal

from .optimizer_authority import OptimizerRequest, OptimizationCandidate, build_optimizer_proposal
from .override_learning_authority import (
    ApprovedOverrideLearningPolicy,
    OverrideLearningObservation,
    apply_approved_learning_policy,
    build_override_learning_draft,
)


PROPOSAL_FP = "a" * 64


def observation(
    override_id: str,
    *,
    reason: str,
    action_type: str,
    worked: bool | None,
) -> OverrideLearningObservation:
    return OverrideLearningObservation(
        override_id=override_id,
        optimizer_proposal_fingerprint=PROPOSAL_FP,
        decision="modified",
        reason_code=reason,
        action_type=action_type,
        worked=worked,
        pre_kpi_context_ref=f"kpi://sanitized/pre/{override_id}",
        post_kpi_context_ref=(
            f"kpi://sanitized/post/{override_id}" if worked is not None else None
        ),
        source_ref=f"override://sanitized/{override_id}",
    )


def candidate(candidate_id: str, action_type: str, cost: int) -> OptimizationCandidate:
    return OptimizationCandidate(
        candidate_id=candidate_id,
        action_type=action_type,
        capacity_gain_man_hours=Decimal("2"),
        incremental_cost_minor_units=cost,
        source_ref=f"availability://sanitized/{candidate_id}",
    )


def optimizer(candidates: tuple[OptimizationCandidate, ...]):
    return build_optimizer_proposal(
        OptimizerRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            model_version="workforce-optimizer-v1",
            dpi_snapshot_fingerprint="d" * 64,
            root_cause="manpower_capacity_shortage",
            manpower_shortage=True,
            capacity_gap_man_hours=Decimal("2"),
            skill_deficit_man_hours=Decimal("0"),
            candidates=candidates,
            max_incremental_cost_minor_units=10_000,
        )
    )


def test_frequent_override_reason_is_measurable_and_draft_is_not_auto_applied() -> None:
    observations = (
        observation("O1", reason="break_timing", action_type="call_in", worked=False),
        observation("O2", reason="break_timing", action_type="call_in", worked=False),
        observation("O3", reason="break_timing", action_type="call_in", worked=True),
        observation("O4", reason="skill_context", action_type="extend_shift", worked=True),
        observation("O5", reason="break_timing", action_type="extend_shift", worked=True),
    )
    draft = build_override_learning_draft(observations)

    assert draft.sample_count == 5
    assert draft.completed_outcome_count == 5
    assert draft.reason_counts["break_timing"] == 4
    assert draft.frequent_override_reasons == ("break_timing",)
    assert draft.action_success_rates["call_in"] == Decimal("1") / Decimal("3")
    assert draft.suggested_cost_multipliers["call_in"] == Decimal("1.50")
    assert draft.automatic_apply_permitted is False
    assert draft.human_approval_required is True


def test_future_optimizer_recommendation_changes_by_approved_learning_version() -> None:
    raw = (
        candidate("CALL", "call_in", 100),
        candidate("EXTEND", "extend_shift", 110),
    )
    version_1 = ApprovedOverrideLearningPolicy(
        version="override-learning-v1",
        draft_fingerprint="1" * 64,
        action_cost_multipliers={"call_in": Decimal("1"), "extend_shift": Decimal("1")},
        approved_by="ops-excellence",
        source_ref="learning://sanitized/v1",
        authority_fingerprint="2" * 64,
    )
    version_2 = ApprovedOverrideLearningPolicy(
        version="override-learning-v2",
        draft_fingerprint="3" * 64,
        action_cost_multipliers={"call_in": Decimal("1.50"), "extend_shift": Decimal("1")},
        approved_by="ops-excellence",
        source_ref="learning://sanitized/v2",
        authority_fingerprint="4" * 64,
    )

    proposal_v1 = optimizer(apply_approved_learning_policy(raw, version_1))
    proposal_v2 = optimizer(apply_approved_learning_policy(raw, version_2))

    assert proposal_v1.selected_candidate_ids == ("CALL",)
    assert proposal_v1.incremental_cost_minor_units == 100
    assert proposal_v2.selected_candidate_ids == ("EXTEND",)
    assert proposal_v2.incremental_cost_minor_units == 110
    assert proposal_v1.proposal_fingerprint != proposal_v2.proposal_fingerprint
    assert proposal_v1.automatic_execution_permitted is False
    assert proposal_v2.automatic_execution_permitted is False


def test_sparse_action_evidence_does_not_overfit_multiplier() -> None:
    draft = build_override_learning_draft(
        (
            observation("S1", reason="other", action_type="call_in", worked=False),
            observation("S2", reason="other", action_type="call_in", worked=False),
        )
    )
    assert draft.action_success_rates["call_in"] == Decimal("0")
    assert draft.suggested_cost_multipliers["call_in"] == Decimal("1")


def test_observation_order_does_not_change_learning_fingerprint() -> None:
    a = observation("A", reason="break_timing", action_type="call_in", worked=False)
    b = observation("B", reason="break_timing", action_type="call_in", worked=True)
    c = observation("C", reason="break_timing", action_type="call_in", worked=False)
    left = build_override_learning_draft((a, b, c))
    right = build_override_learning_draft((c, a, b))
    assert left.input_fingerprint == right.input_fingerprint
    assert left.draft_fingerprint == right.draft_fingerprint
