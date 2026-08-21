from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .capacity_authority import (
    CapacityWorker,
    EffectiveCapacityRequest,
    build_effective_capacity_snapshot,
)
from .capacity_repository import persist_capacity_snapshot
from .demand_authority import DemandSnapshot
from .demand_repository import persist_demand_snapshot
from .dpi_authority import KpiObservation
from .dpi_repository import get_latest_dpi_snapshot
from .dpi_service import compute_and_persist_dpi


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

AT = datetime(2026, 8, 17, 13, 0, tzinfo=timezone.utc)
LOCATION = "WH-DPI-001"


def _seed_governed_inputs() -> tuple[str, str]:
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
                    employee_id=f"DPI-E{i:02d}",
                    scheduled_hours=Decimal("1"),
                    skills=frozenset({"picking"}),
                    source_ref=f"roster://sanitized/DPI-E{i:02d}",
                )
                for i in range(1, 11)
            )
            + (
                CapacityWorker(
                    employee_id="DPI-E11",
                    scheduled_hours=Decimal("0.7"),
                    skills=frozenset({"picking"}),
                    source_ref="roster://sanitized/DPI-E11",
                ),
            ),
            source_refs=(
                "schedule://sanitized/WH-DPI-001/2026-08-17T13",
                "absence://sanitized/WH-DPI-001/2026-08-17T13",
                "break://sanitized/WH-DPI-001/2026-08-17T13",
                "skills://sanitized/WH-DPI-001/2026-08-17T13",
            ),
        )
    )
    persist_capacity_snapshot(capacity, actor_subject="capacity-engine")
    return demand.snapshot_fingerprint, capacity.snapshot_fingerprint


def _bad_kpi() -> KpiObservation:
    return KpiObservation(
        key="picking_seconds_per_order",
        actual=Decimal("210"),
        target=Decimal("120"),
        direction="lower_is_better",
        source_ref="kpi://sanitized/WH-DPI-001/picking/2026-08-17T13",
    )


def test_service_resolves_governed_inputs_and_persists_non_manpower_root_cause() -> None:
    demand_fp, capacity_fp = _seed_governed_inputs()
    snapshot, receipt = compute_and_persist_dpi(
        location_id=LOCATION,
        kpi_observations=(_bad_kpi(),),
        actor_subject="dpi-engine",
    )

    assert snapshot.demand_snapshot_fingerprint == demand_fp
    assert snapshot.capacity_snapshot_fingerprint == capacity_fp
    assert snapshot.capacity_sufficient is True
    assert snapshot.kpi_bad is True
    assert snapshot.manpower_shortage is False
    assert snapshot.root_cause == "execution_or_process"
    assert snapshot.automatic_extra_people_permitted is False
    assert receipt["idempotent_replay"] is False

    replay_snapshot, replay_receipt = compute_and_persist_dpi(
        location_id=LOCATION,
        kpi_observations=(_bad_kpi(),),
        actor_subject="dpi-engine",
    )
    assert replay_snapshot == snapshot
    assert replay_receipt["idempotent_replay"] is True

    latest = get_latest_dpi_snapshot(LOCATION)
    assert latest is not None
    assert latest["root_cause"] == "execution_or_process"
    assert latest["manpower_shortage"] is False
    assert latest["automatic_extra_people_permitted"] is False
    assert latest["required_man_hours"] == Decimal("10")
    assert latest["effective_man_hours"] == Decimal("10.7")
