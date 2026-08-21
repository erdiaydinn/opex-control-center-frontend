import os
import unittest
from datetime import datetime, timezone
from decimal import Decimal

from . import persistence
from .capacity_authority import (
    CapacityWorker,
    EffectiveCapacityRequest,
    build_effective_capacity_snapshot,
)
from .capacity_repository import persist_capacity_snapshot
from .command_center_repository import get_command_center_authority
from .demand_authority import DemandSnapshot
from .demand_repository import persist_demand_snapshot
from .dpi_authority import KpiObservation
from .dpi_service import compute_and_persist_dpi


@unittest.skipUnless(os.getenv("DATABASE_URL"), "PostgreSQL Workforce runtime identity is required")
class WorkforceCommandCenterPostgresTests(unittest.TestCase):
    def test_read_model_joins_exact_demand_and_capacity_fingerprints(self):
        tenant = persistence.tenant_id()
        location = "WH-CC-PG-001"
        at = datetime(2026, 8, 21, 5, 0, tzinfo=timezone.utc)
        demand = DemandSnapshot(
            tenant_id=tenant,
            location_id=location,
            interval_start=at,
            interval_minutes=15,
            model_version="command-center-demand-v1",
            input_fingerprint="6" * 64,
            snapshot_fingerprint="7" * 64,
            base_man_hours=Decimal("2"),
            overhead_man_hours=Decimal("0"),
            required_man_hours=Decimal("2"),
            required_people=Decimal("8"),
            contributions=(),
            labor_standard_refs=(),
        )
        persist_demand_snapshot(demand, actor_subject="command-center-test")

        capacity = build_effective_capacity_snapshot(
            EffectiveCapacityRequest(
                tenant_id=tenant,
                location_id=location,
                interval_start=at,
                interval_minutes=15,
                model_version="command-center-capacity-v1",
                workers=(
                    CapacityWorker(
                        employee_id="CC-E1",
                        scheduled_hours=Decimal("0.25"),
                        skills=frozenset({"picking"}),
                        source_ref="schedule://CC-E1",
                    ),
                    CapacityWorker(
                        employee_id="CC-E2",
                        scheduled_hours=Decimal("0.25"),
                        skills=frozenset({"picking"}),
                        source_ref="schedule://CC-E2",
                    ),
                ),
                source_refs=("schedule://WH-CC-PG-001/2026-08-21T05:00Z",),
            )
        )
        persist_capacity_snapshot(capacity, actor_subject="command-center-test")
        dpi, _ = compute_and_persist_dpi(
            location_id=location,
            kpi_observations=(
                KpiObservation(
                    key="picking_seconds_per_order",
                    actual=Decimal("120"),
                    target=Decimal("120"),
                    direction="lower_is_better",
                    source_ref="kpi://WH-CC-PG-001/picking",
                ),
            ),
            actor_subject="command-center-test",
        )

        result = get_command_center_authority(location)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["interval_start"], at)
        self.assertEqual(result["interval_minutes"], 15)
        self.assertEqual(result["dpi"]["snapshot_fingerprint"], dpi.snapshot_fingerprint)
        self.assertEqual(result["dpi"]["demand_snapshot_fingerprint"], demand.snapshot_fingerprint)
        self.assertEqual(result["dpi"]["capacity_snapshot_fingerprint"], capacity.snapshot_fingerprint)
        self.assertEqual(result["capacity"]["effective_man_hours"], capacity.effective_man_hours)


if __name__ == "__main__":
    unittest.main()
