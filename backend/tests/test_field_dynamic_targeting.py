from datetime import datetime, timezone

import pytest

from app.modules.field_intelligence.dynamic_targeting import (
    DynamicTargetResolutionError,
    build_dynamic_eligibility,
    resolve_dynamic_target_snapshot,
)
from app.modules.field_intelligence.models import LocationRecord, TargetSelector

NOW = datetime(2026, 8, 16, 13, 0, tzinfo=timezone.utc)


def location(location_id: str, city="Istanbul", tenant="tenant-a"):
    return LocationRecord(
        tenant_id=tenant,
        location_id=location_id,
        country="TR",
        region="Marmara",
        city=city,
        district="Kadikoy",
    )


def test_governed_kpi_eligibility_intersects_with_geographic_scope():
    eligibility = build_dynamic_eligibility(
        tenant_id="tenant-a",
        criterion_id="ops.nsfr.above_threshold",
        source_ref="governed-kpi://ops.nsfr/v3",
        observed_at=NOW,
        location_ids=frozenset({"ist-1", "ank-1"}),
    )
    result = resolve_dynamic_target_snapshot(
        [location("ist-1"), location("ist-2"), location("ank-1", city="Ankara")],
        TargetSelector(tenant_id="tenant-a", cities=("Istanbul",)),
        eligibility,
        created_at=NOW,
    )
    assert result.location_ids == ("ist-1",)
    assert result.fingerprint != eligibility.fingerprint


def test_dynamic_targeting_never_crosses_tenant_boundary():
    eligibility = build_dynamic_eligibility(
        tenant_id="tenant-b",
        criterion_id="inventory.discrepancy",
        source_ref="governed-kpi://inventory/discrepancy",
        observed_at=NOW,
        location_ids=frozenset({"ist-1"}),
    )
    with pytest.raises(DynamicTargetResolutionError, match="tenant"):
        resolve_dynamic_target_snapshot(
            [location("ist-1")],
            TargetSelector(tenant_id="tenant-a", all_active_locations=True),
            eligibility,
            created_at=NOW,
        )


def test_empty_dynamic_intersection_fails_closed():
    eligibility = build_dynamic_eligibility(
        tenant_id="tenant-a",
        criterion_id="inventory.discrepancy",
        source_ref="governed-kpi://inventory/discrepancy",
        observed_at=NOW,
        location_ids=frozenset({"ank-1"}),
    )
    with pytest.raises(DynamicTargetResolutionError, match="intersection is empty"):
        resolve_dynamic_target_snapshot(
            [location("ist-1"), location("ank-1", city="Ankara")],
            TargetSelector(tenant_id="tenant-a", cities=("Istanbul",)),
            eligibility,
            created_at=NOW,
        )
