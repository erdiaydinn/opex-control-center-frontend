from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from .demand_authority import (
    DemandAuthorityError,
    DemandDriver,
    DemandRequest,
    LaborStandardVersion,
    build_demand_snapshot,
)
from .demand_model import DemandOverheads


AT = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)


def standard(
    activity: str,
    *,
    version: int = 1,
    seconds: str = "60",
    effective_from: datetime | None = None,
    effective_until: datetime | None = None,
    source_ref: str | None = None,
) -> LaborStandardVersion:
    return LaborStandardVersion(
        activity=activity,
        version=version,
        seconds_per_unit=Decimal(seconds),
        people=Decimal("1"),
        effective_from=effective_from or AT - timedelta(days=30),
        effective_until=effective_until,
        source_ref=source_ref or f"labor-study://{activity}/v{version}",
        approved_by="ops-excellence",
    )


def request(*drivers: DemandDriver, interval_minutes: int = 60) -> DemandRequest:
    return DemandRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        interval_start=AT,
        interval_minutes=interval_minutes,
        model_version="workforce-demand-v1",
        drivers=tuple(drivers),
        overheads=DemandOverheads(
            fatigue_factor=Decimal("0.10"),
            buffer_tasks=Decimal("0.05"),
            break_time=Decimal("0.05"),
        ),
    )


def test_same_input_model_and_labor_versions_are_bitwise_deterministic() -> None:
    standards = (
        standard("picking", seconds="45"),
        standard("putaway", seconds="90"),
    )
    demand_request = request(
        DemandDriver("orders", "picking", Decimal("80"), "forecast://orders/2026-08-17T08"),
        DemandDriver("inbound", "putaway", Decimal("20"), "forecast://putaway/2026-08-17T08"),
    )

    first = build_demand_snapshot(demand_request, standards)
    second = build_demand_snapshot(demand_request, standards)

    assert first == second
    assert first.input_fingerprint == second.input_fingerprint
    assert first.snapshot_fingerprint == second.snapshot_fingerprint
    assert first.base_man_hours == Decimal("1.5")
    assert first.overhead_man_hours == Decimal("0.300")
    assert first.required_man_hours == Decimal("1.800")
    assert first.required_people == Decimal("1.800")
    assert len(first.contributions) == 2
    assert first.labor_standard_refs == (
        f"picking:v1:{(AT - timedelta(days=30)).isoformat()}",
        f"putaway:v1:{(AT - timedelta(days=30)).isoformat()}",
    )


def test_driver_order_does_not_change_fingerprint_or_required_mh() -> None:
    standards = (standard("picking", seconds="45"), standard("packing", seconds="30"))
    a = DemandDriver("orders", "picking", Decimal("80"), "forecast://orders")
    b = DemandDriver("pack", "packing", Decimal("80"), "forecast://pack")

    left = build_demand_snapshot(request(a, b), standards)
    right = build_demand_snapshot(request(b, a), standards)

    assert left.required_man_hours == right.required_man_hours
    assert left.input_fingerprint == right.input_fingerprint
    assert left.snapshot_fingerprint == right.snapshot_fingerprint


def test_non_zero_demand_without_approved_effective_standard_fails_closed() -> None:
    demand_request = request(
        DemandDriver("orders", "picking", Decimal("1"), "forecast://orders")
    )
    with pytest.raises(DemandAuthorityError, match="no approved effective labor standard"):
        build_demand_snapshot(demand_request, ())


def test_overlapping_effective_standards_fail_closed_instead_of_guessing_latest() -> None:
    demand_request = request(
        DemandDriver("orders", "picking", Decimal("1"), "forecast://orders")
    )
    standards = (
        standard("picking", version=1, seconds="45"),
        standard("picking", version=2, seconds="40"),
    )
    with pytest.raises(DemandAuthorityError, match="ambiguous effective labor standards"):
        build_demand_snapshot(demand_request, standards)


def test_effective_date_selects_exact_standard_version_and_changes_provenance() -> None:
    old = standard(
        "picking",
        version=1,
        seconds="60",
        effective_from=AT - timedelta(days=60),
        effective_until=AT - timedelta(days=1),
    )
    current = standard(
        "picking",
        version=2,
        seconds="45",
        effective_from=AT - timedelta(days=1),
    )
    snapshot = build_demand_snapshot(
        request(DemandDriver("orders", "picking", Decimal("80"), "forecast://orders")),
        (old, current),
    )
    assert snapshot.contributions[0].labor_standard_ref == current.authority_ref
    assert snapshot.contributions[0].seconds_per_unit == Decimal("45")


def test_15_minute_snapshot_converts_required_hours_to_required_people() -> None:
    snapshot = build_demand_snapshot(
        request(
            DemandDriver("orders", "picking", Decimal("10"), "forecast://orders"),
            interval_minutes=15,
        ),
        (standard("picking", seconds="60"),),
    )
    # 10 units * 60 sec = 1/6 MH base; 20% overhead -> 0.2 MH.
    # In a 15-minute interval, 0.2 MH requires 0.8 concurrent people.
    assert snapshot.required_man_hours == Decimal("0.2")
    assert snapshot.required_people == Decimal("0.8")


def test_zero_volume_does_not_require_or_invent_a_labor_standard() -> None:
    snapshot = build_demand_snapshot(
        request(DemandDriver("orders", "picking", Decimal("0"), "forecast://orders")),
        (),
    )
    assert snapshot.required_man_hours == Decimal("0")
    assert snapshot.required_people == Decimal("0")
    assert snapshot.contributions == ()
    assert snapshot.labor_standard_refs == ()


def test_unknown_interval_and_unversioned_model_are_rejected() -> None:
    with pytest.raises(DemandAuthorityError, match="interval_minutes"):
        request(interval_minutes=45)
    with pytest.raises(DemandAuthorityError, match="model_version"):
        DemandRequest(
            tenant_id="tenant-a",
            location_id="WH-001",
            interval_start=AT,
            interval_minutes=60,
            model_version=" ",
            drivers=(),
        )
