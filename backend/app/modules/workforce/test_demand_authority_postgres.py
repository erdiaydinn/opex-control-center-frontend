from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .demand_authority import DemandDriver, DemandRequest, LaborStandardVersion
from .demand_repository import (
    DemandPersistenceError,
    build_and_persist_demand,
    register_labor_standard,
)


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

AT = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def test_runtime_bound_tenant_can_register_standard_and_persist_idempotent_snapshot() -> None:
    standard = LaborStandardVersion(
        activity="picking",
        version=1,
        seconds_per_unit=Decimal("45"),
        people=Decimal("1"),
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_ref="labor-study://sanitized/picking-v1",
        approved_by="ops-excellence",
    )
    first_standard = register_labor_standard(standard)
    replay_standard = register_labor_standard(standard)
    assert first_standard["tenant_id"] == "tenant-a"
    assert first_standard["idempotent_replay"] is False
    assert replay_standard["idempotent_replay"] is True

    request = DemandRequest(
        tenant_id="tenant-a",
        location_id="WH-001",
        interval_start=AT,
        interval_minutes=60,
        model_version="workforce-demand-v1",
        drivers=(
            DemandDriver(
                driver_key="orders",
                activity="picking",
                volume=Decimal("80"),
                source_ref="forecast://sanitized/orders/2026-08-17T09",
            ),
        ),
    )
    first_snapshot, first_receipt = build_and_persist_demand(
        request,
        actor_subject="planner-a",
    )
    replay_snapshot, replay_receipt = build_and_persist_demand(
        request,
        actor_subject="planner-a",
    )

    assert first_snapshot == replay_snapshot
    assert first_snapshot.required_man_hours == Decimal("1")
    assert first_snapshot.required_people == Decimal("1")
    assert first_receipt["snapshot_fingerprint"] == first_snapshot.snapshot_fingerprint
    assert first_receipt["idempotent_replay"] is False
    assert replay_receipt["idempotent_replay"] is True


def test_request_cannot_override_server_bound_tenant() -> None:
    request = DemandRequest(
        tenant_id="tenant-b",
        location_id="WH-001",
        interval_start=AT,
        interval_minutes=60,
        model_version="workforce-demand-v1",
        drivers=(),
    )
    with pytest.raises(Exception, match="server-authoritative Workforce tenant"):
        build_and_persist_demand(request, actor_subject="planner-a")


def test_conflicting_same_version_standard_is_not_silently_overwritten() -> None:
    original = LaborStandardVersion(
        activity="packing",
        version=1,
        seconds_per_unit=Decimal("30"),
        people=Decimal("1"),
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_ref="labor-study://sanitized/packing-v1",
        approved_by="ops-excellence",
    )
    register_labor_standard(original)
    conflicting = LaborStandardVersion(
        activity="packing",
        version=1,
        seconds_per_unit=Decimal("25"),
        people=Decimal("1"),
        effective_from=datetime(2026, 8, 1, tzinfo=timezone.utc),
        source_ref="labor-study://sanitized/packing-v1-revised",
        approved_by="ops-excellence",
    )
    with pytest.raises(DemandPersistenceError, match="different immutable authority"):
        register_labor_standard(conflicting)
