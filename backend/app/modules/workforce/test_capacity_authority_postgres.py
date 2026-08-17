from datetime import datetime, timezone
from decimal import Decimal
import os

import pytest

from .capacity_authority import (
    CapacityWorker,
    EffectiveCapacityRequest,
    build_effective_capacity_snapshot,
)
from .capacity_repository import (
    CapacityPersistenceError,
    get_latest_capacity_snapshot,
    persist_capacity_snapshot,
)
from .skill_capacity import SkillDemand


pytestmark = pytest.mark.skipif(
    not os.getenv("DATABASE_URL"),
    reason="PostgreSQL Workforce runtime identity is required",
)

AT = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)


def snapshot(tenant_id: str = "tenant-a"):
    request = EffectiveCapacityRequest(
        tenant_id=tenant_id,
        location_id="WH-001",
        interval_start=AT,
        interval_minutes=60,
        model_version="workforce-capacity-v1",
        workers=(
            CapacityWorker(
                employee_id="E01",
                scheduled_hours=Decimal("1"),
                absence_hours=Decimal("0"),
                break_hours=Decimal("0.25"),
                unavailable_hours=Decimal("0"),
                skills=frozenset({"picking"}),
                source_ref="roster://sanitized/E01/2026-08-17T09",
            ),
            CapacityWorker(
                employee_id="E02",
                scheduled_hours=Decimal("1"),
                skills=frozenset({"inbound"}),
                source_ref="roster://sanitized/E02/2026-08-17T09",
            ),
        ),
        skill_demand=SkillDemand(required_hours={"picking": Decimal("1.75")}),
        source_refs=(
            "schedule://sanitized/WH-001/2026-08-17T09",
            "absence://sanitized/WH-001/2026-08-17T09",
            "break://sanitized/WH-001/2026-08-17T09",
            "skills://sanitized/WH-001/2026-08-17T09",
        ),
    )
    return build_effective_capacity_snapshot(request)


def test_runtime_bound_tenant_persists_and_replays_capacity_snapshot() -> None:
    calculated = snapshot()
    first = persist_capacity_snapshot(calculated, actor_subject="capacity-engine")
    replay = persist_capacity_snapshot(calculated, actor_subject="capacity-engine")

    assert first["tenant_id"] == "tenant-a"
    assert first["effective_capacity"] == Decimal("0.75")
    assert first["idempotent_replay"] is False
    assert replay["idempotent_replay"] is True

    latest = get_latest_capacity_snapshot("WH-001")
    assert latest is not None
    assert latest["snapshot_fingerprint"] == calculated.snapshot_fingerprint
    assert latest["scheduled_fte"] == Decimal("2")
    assert latest["break_man_hours"] == Decimal("0.25")
    assert latest["net_available_man_hours"] == Decimal("1.75")
    assert latest["skill_feasible_man_hours"] == Decimal("0.75")
    assert latest["effective_capacity"] == Decimal("0.75")


def test_snapshot_tenant_cannot_override_runtime_authority() -> None:
    with pytest.raises(CapacityPersistenceError, match="does not match runtime tenant authority"):
        persist_capacity_snapshot(snapshot("tenant-b"), actor_subject="capacity-engine")
