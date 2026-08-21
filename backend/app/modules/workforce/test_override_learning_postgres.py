from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .dpi_authority import DpiRequest, build_dpi_snapshot
from .dpi_repository import persist_dpi_snapshot
from .optimizer_authority import OptimizationCandidate
from .override_learning_repository import (
    get_learning_summary,
    record_manager_override,
    record_override_outcome,
)
from .override_learning_service import (
    compute_and_persist_learning_draft,
    compute_learned_optimizer_proposal,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

LOCATION = "WH-LRN-001"
BASE_PROPOSAL_FP = "a" * 64


def _record_override_evidence() -> None:
    rows = (
        ("manager-1", "break_timing", "call_in", False),
        ("manager-2", "break_timing", "call_in", False),
        ("manager-3", "break_timing", "call_in", True),
        ("manager-4", "break_timing", "call_in", True),
        ("manager-5", "skill_context", "call_in", True),
    )
    for actor, reason, action_type, worked in rows:
        override = record_manager_override(
            location_id=LOCATION,
            optimizer_proposal_fingerprint=BASE_PROPOSAL_FP,
            decision="modified",
            reason_code=reason,
            reason_note=f"sanitized note {actor}",
            observed_action_type=action_type,
            actor_subject=actor,
        )
        record_override_outcome(
            override_id=str(override["id"]),
            worked=worked,
            post_kpi_context_ref=f"kpi://sanitized/post/{actor}",
            kpi_deltas={"picking_seconds_per_order": Decimal("-10" if worked else "5")},
            source_ref=f"outcome://sanitized/{actor}",
            actor_subject="ops-reviewer",
        )


def _persist_manpower_dpi() -> None:
    request = DpiRequest(
        tenant_id="tenant-a",
        location_id=LOCATION,
        interval_start=datetime(2026, 8, 17, 16, 0, tzinfo=timezone.utc),
        model_version="workforce-dpi-v1",
        demand_snapshot_fingerprint="b" * 64,
        capacity_snapshot_fingerprint="c" * 64,
        required_man_hours=Decimal("10"),
        effective_man_hours=Decimal("8"),
        skill_deficit_man_hours=Decimal("0"),
        kpis=(),
        demand_source_ref="workforce-demand://WH-LRN-001",
        capacity_source_ref="workforce-capacity://WH-LRN-001",
    )
    snapshot = build_dpi_snapshot(request)
    persist_dpi_snapshot(
        snapshot,
        kpi_observations=(),
        required_man_hours=request.required_man_hours,
        effective_man_hours=request.effective_man_hours,
        skill_deficit_man_hours=request.skill_deficit_man_hours,
        actor_subject="dpi-engine",
    )


def _raw_candidates() -> tuple[OptimizationCandidate, ...]:
    return (
        OptimizationCandidate(
            candidate_id="CALL",
            action_type="call_in",
            capacity_gain_man_hours=Decimal("2"),
            incremental_cost_minor_units=100,
            source_ref="availability://sanitized/CALL",
        ),
        OptimizationCandidate(
            candidate_id="EXTEND",
            action_type="extend_shift",
            capacity_gain_man_hours=Decimal("2"),
            incremental_cost_minor_units=110,
            source_ref="availability://sanitized/EXTEND",
        ),
    )


def test_override_frequency_and_outcomes_persist_as_non_applying_learning_draft() -> None:
    _record_override_evidence()
    draft, receipt = compute_and_persist_learning_draft(actor_subject="learning-engine")

    assert draft.sample_count == 5
    assert draft.completed_outcome_count == 5
    assert draft.reason_counts["break_timing"] == 4
    assert draft.frequent_override_reasons == ("break_timing",)
    assert draft.automatic_apply_permitted is False
    assert draft.human_approval_required is True
    assert receipt["automatic_apply_permitted"] is False

    summary = get_learning_summary()
    assert summary["latest_draft"]["sample_count"] == 5
    assert summary["latest_draft"]["frequent_override_reasons"] == ["break_timing"]
    assert summary["latest_draft"]["automatic_apply_permitted"] is False
    assert summary["approved_version"] is not None


def test_approved_learning_versions_change_future_optimizer_recommendation() -> None:
    _persist_manpower_dpi()
    raw = _raw_candidates()

    proposal_v1, _, learning_receipt_v1 = compute_learned_optimizer_proposal(
        location_id=LOCATION,
        raw_candidates=raw,
        max_incremental_cost_minor_units=10_000,
        learning_version="override-learning-v1",
        actor_subject="optimizer-engine",
    )
    proposal_v2, _, learning_receipt_v2 = compute_learned_optimizer_proposal(
        location_id=LOCATION,
        raw_candidates=raw,
        max_incremental_cost_minor_units=10_000,
        learning_version="override-learning-v2",
        actor_subject="optimizer-engine",
    )

    assert proposal_v1.selected_candidate_ids == ("CALL",)
    assert proposal_v2.selected_candidate_ids == ("EXTEND",)
    assert proposal_v1.proposal_fingerprint != proposal_v2.proposal_fingerprint
    assert proposal_v1.automatic_execution_permitted is False
    assert proposal_v2.automatic_execution_permitted is False
    assert learning_receipt_v1["learning_version"] == "override-learning-v1"
    assert learning_receipt_v2["learning_version"] == "override-learning-v2"
    assert learning_receipt_v1["learning_authority_fingerprint"] != learning_receipt_v2["learning_authority_fingerprint"]
