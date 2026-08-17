from datetime import datetime, timezone
from decimal import Decimal

import pytest

from .dpi_authority import (
    DpiAuthorityError,
    DpiRequest,
    KpiObservation,
    build_dpi_snapshot,
)


AT = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
DEMAND_FP = "a" * 64
CAPACITY_FP = "b" * 64


def request(
    *,
    required: str = "10",
    effective: str = "10.7",
    skill_deficit: str = "0",
    kpis: tuple[KpiObservation, ...] = (),
) -> DpiRequest:
    return DpiRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        interval_start=AT,
        model_version="workforce-dpi-v1",
        demand_snapshot_fingerprint=DEMAND_FP,
        capacity_snapshot_fingerprint=CAPACITY_FP,
        required_man_hours=Decimal(required),
        effective_man_hours=Decimal(effective),
        skill_deficit_man_hours=Decimal(skill_deficit),
        kpis=kpis,
        demand_source_ref="workforce-demand://WH-001/2026-08-17T09",
        capacity_source_ref="workforce-capacity://WH-001/2026-08-17T09",
    )


def bad_cycle_time() -> KpiObservation:
    return KpiObservation(
        key="picking_seconds_per_order",
        actual=Decimal("210"),
        target=Decimal("120"),
        direction="lower_is_better",
        source_ref="kpi://sanitized/picking/2026-08-17T09",
    )


def test_acceptance_bad_kpi_with_sufficient_capacity_is_not_manpower_shortage() -> None:
    snapshot = build_dpi_snapshot(request(kpis=(bad_cycle_time(),)))

    assert snapshot.capacity_sufficient is True
    assert snapshot.kpi_bad is True
    assert snapshot.bad_kpi_keys == ("picking_seconds_per_order",)
    assert snapshot.manpower_shortage is False
    assert snapshot.root_cause == "execution_or_process"
    assert snapshot.automatic_extra_people_permitted is False
    assert snapshot.staffing_review_required is False
    assert snapshot.capacity_gap_man_hours == Decimal("0")


def test_true_capacity_shortage_requires_capacity_gap_not_bad_kpi() -> None:
    snapshot = build_dpi_snapshot(
        request(
            required="10",
            effective="8",
            kpis=(bad_cycle_time(),),
        )
    )
    assert snapshot.capacity_sufficient is False
    assert snapshot.manpower_shortage is True
    assert snapshot.root_cause == "manpower_capacity_shortage"
    assert snapshot.staffing_review_required is True
    assert snapshot.automatic_extra_people_permitted is False


def test_skill_mix_gap_is_not_generic_manpower_shortage() -> None:
    snapshot = build_dpi_snapshot(
        request(
            required="10",
            effective="8",
            skill_deficit="2",
            kpis=(bad_cycle_time(),),
        )
    )
    assert snapshot.capacity_sufficient is False
    assert snapshot.manpower_shortage is False
    assert snapshot.root_cause == "skill_mix_constraint"
    assert snapshot.staffing_review_required is True
    assert snapshot.automatic_extra_people_permitted is False


def test_kpi_order_does_not_change_fingerprint() -> None:
    picking = bad_cycle_time()
    otp = KpiObservation(
        key="otp_4_25_pct",
        actual=Decimal("91"),
        target=Decimal("95"),
        direction="higher_is_better",
        source_ref="kpi://sanitized/otp/2026-08-17T09",
    )
    left = build_dpi_snapshot(request(kpis=(picking, otp)))
    right = build_dpi_snapshot(request(kpis=(otp, picking)))

    assert left.input_fingerprint == right.input_fingerprint
    assert left.snapshot_fingerprint == right.snapshot_fingerprint
    assert left.bad_kpi_keys == right.bad_kpi_keys == (
        "otp_4_25_pct",
        "picking_seconds_per_order",
    )


def test_no_demand_produces_zero_dpi_and_no_pressure_signal() -> None:
    snapshot = build_dpi_snapshot(request(required="0", effective="0"))
    assert snapshot.demand_pressure_index == Decimal("0")
    assert snapshot.capacity_sufficient is True
    assert snapshot.manpower_shortage is False
    assert snapshot.root_cause == "no_pressure_signal"


def test_zero_capacity_with_demand_uses_bounded_pressure_sentinel() -> None:
    snapshot = build_dpi_snapshot(request(required="1", effective="0"))
    assert snapshot.demand_pressure_index == Decimal("999")
    assert snapshot.manpower_shortage is True
    assert snapshot.automatic_extra_people_permitted is False


def test_invalid_fingerprint_source_and_naive_time_fail_closed() -> None:
    with pytest.raises(DpiAuthorityError, match="lowercase SHA-256"):
        DpiRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=AT,
            model_version="workforce-dpi-v1",
            demand_snapshot_fingerprint="not-a-sha",
            capacity_snapshot_fingerprint=CAPACITY_FP,
            required_man_hours=Decimal("1"),
            effective_man_hours=Decimal("1"),
            skill_deficit_man_hours=Decimal("0"),
            kpis=(),
            demand_source_ref="demand://x",
            capacity_source_ref="capacity://x",
        )

    with pytest.raises(DpiAuthorityError, match="source refs"):
        DpiRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=AT,
            model_version="workforce-dpi-v1",
            demand_snapshot_fingerprint=DEMAND_FP,
            capacity_snapshot_fingerprint=CAPACITY_FP,
            required_man_hours=Decimal("1"),
            effective_man_hours=Decimal("1"),
            skill_deficit_man_hours=Decimal("0"),
            kpis=(),
            demand_source_ref="",
            capacity_source_ref="capacity://x",
        )

    with pytest.raises(DpiAuthorityError, match="timezone-aware"):
        DpiRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=datetime(2026, 8, 17, 9, 0),
            model_version="workforce-dpi-v1",
            demand_snapshot_fingerprint=DEMAND_FP,
            capacity_snapshot_fingerprint=CAPACITY_FP,
            required_man_hours=Decimal("1"),
            effective_man_hours=Decimal("1"),
            skill_deficit_man_hours=Decimal("0"),
            kpis=(),
            demand_source_ref="demand://x",
            capacity_source_ref="capacity://x",
        )
