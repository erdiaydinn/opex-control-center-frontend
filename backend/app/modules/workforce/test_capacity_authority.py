from datetime import datetime, timezone
from decimal import Decimal

import pytest

from .capacity_authority import (
    CapacityAuthorityError,
    CapacityWorker,
    EffectiveCapacityRequest,
    build_effective_capacity_snapshot,
)
from .skill_capacity import SkillDemand


AT = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def worker(
    employee_id: str,
    *,
    skills: frozenset[str] = frozenset({"picking"}),
    scheduled: str = "1",
    absence: str = "0",
    break_hours: str = "0",
    unavailable: str = "0",
) -> CapacityWorker:
    return CapacityWorker(
        employee_id=employee_id,
        scheduled_hours=Decimal(scheduled),
        absence_hours=Decimal(absence),
        break_hours=Decimal(break_hours),
        unavailable_hours=Decimal(unavailable),
        skills=skills,
        source_ref=f"roster://sanitized/{employee_id}/2026-08-17T09",
    )


def request(*workers: CapacityWorker, skill_demand: SkillDemand | None = None) -> EffectiveCapacityRequest:
    return EffectiveCapacityRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        interval_start=AT,
        interval_minutes=60,
        model_version="workforce-capacity-v1",
        workers=tuple(workers),
        skill_demand=skill_demand,
        source_refs=(
            "schedule://sanitized/WH-001/2026-08-17T09",
            "absence://sanitized/WH-001/2026-08-17T09",
            "break://sanitized/WH-001/2026-08-17T09",
            "skills://sanitized/WH-001/2026-08-17T09",
        ),
    )


def test_acceptance_scheduled_13_fte_becomes_effective_capacity_10_7() -> None:
    workers = tuple(worker(f"E{i:02d}") for i in range(1, 11)) + (
        worker("E11", break_hours="0.3"),
        worker("E12", absence="1"),
        worker("E13", skills=frozenset({"inbound"})),
    )
    snapshot = build_effective_capacity_snapshot(
        request(
            *workers,
            skill_demand=SkillDemand(required_hours={"picking": Decimal("11.7")}),
        )
    )

    assert snapshot.scheduled_fte == Decimal("13")
    assert snapshot.absence_man_hours == Decimal("1")
    assert snapshot.break_man_hours == Decimal("0.3")
    assert snapshot.net_available_man_hours == Decimal("11.7")
    assert snapshot.skill_feasible_man_hours == Decimal("10.7")
    assert snapshot.skill_deficit_man_hours == Decimal("1.0")
    assert snapshot.effective_capacity == Decimal("10.7")
    assert snapshot.skill_deficits == {"picking": Decimal("1.0")}
    assert snapshot.unused_worker_hours["E13"] == Decimal("1")


def test_same_workers_in_different_order_produce_same_fingerprint() -> None:
    a = worker("A", scheduled="1")
    b = worker("B", scheduled="1", break_hours="0.25")
    demand = SkillDemand(required_hours={"picking": Decimal("1.75")})

    left = build_effective_capacity_snapshot(request(a, b, skill_demand=demand))
    right = build_effective_capacity_snapshot(request(b, a, skill_demand=demand))

    assert left.input_fingerprint == right.input_fingerprint
    assert left.snapshot_fingerprint == right.snapshot_fingerprint
    assert left.effective_capacity == right.effective_capacity == Decimal("1.75")


def test_absence_break_and_unavailable_are_distinct_explainable_deductions() -> None:
    snapshot = build_effective_capacity_snapshot(
        request(
            worker(
                "A",
                scheduled="1",
                absence="0.2",
                break_hours="0.1",
                unavailable="0.2",
            )
        )
    )
    assert snapshot.scheduled_man_hours == Decimal("1")
    assert snapshot.absence_man_hours == Decimal("0.2")
    assert snapshot.break_man_hours == Decimal("0.1")
    assert snapshot.unavailable_man_hours == Decimal("0.2")
    assert snapshot.net_available_man_hours == Decimal("0.5")
    assert snapshot.effective_capacity == Decimal("0.5")


def test_15_minute_interval_converts_effective_hours_to_fte() -> None:
    snapshot = build_effective_capacity_snapshot(
        EffectiveCapacityRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=AT,
            interval_minutes=15,
            model_version="workforce-capacity-v1",
            workers=(worker("A", scheduled="0.25"),),
            source_refs=("schedule://sanitized/quarter-hour",),
        )
    )
    assert snapshot.effective_man_hours == Decimal("0.25")
    assert snapshot.effective_capacity == Decimal("1")


def test_skill_mismatch_reduces_effective_capacity_without_erasing_raw_availability() -> None:
    snapshot = build_effective_capacity_snapshot(
        request(
            worker("picker", skills=frozenset({"picking"})),
            worker("receiver", skills=frozenset({"inbound"})),
            skill_demand=SkillDemand(required_hours={"picking": Decimal("2")}),
        )
    )
    assert snapshot.net_available_man_hours == Decimal("2")
    assert snapshot.skill_feasible_man_hours == Decimal("1")
    assert snapshot.skill_deficit_man_hours == Decimal("1")
    assert snapshot.effective_capacity == Decimal("1")


def test_productivity_factor_is_explicit_not_silently_inferred() -> None:
    snapshot = build_effective_capacity_snapshot(
        EffectiveCapacityRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=AT,
            interval_minutes=60,
            model_version="workforce-capacity-v1",
            workers=(worker("A"),),
            source_refs=("schedule://sanitized/a", "productivity://approved/v1"),
            productivity_factor=Decimal("0.9"),
        )
    )
    assert snapshot.net_available_man_hours == Decimal("1")
    assert snapshot.effective_capacity == Decimal("0.9")


def test_invalid_double_deduction_and_naive_timestamp_fail_closed() -> None:
    with pytest.raises(CapacityAuthorityError, match="deductions cannot exceed"):
        worker("A", scheduled="1", absence="0.6", break_hours="0.5")

    with pytest.raises(CapacityAuthorityError, match="timezone-aware"):
        EffectiveCapacityRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=datetime(2026, 8, 17, 9, 0),
            interval_minutes=60,
            model_version="workforce-capacity-v1",
            workers=(worker("A"),),
            source_refs=("schedule://sanitized/a",),
        )
