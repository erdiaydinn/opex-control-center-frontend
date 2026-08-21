from datetime import datetime, timezone

import pytest

from app.modules.field_intelligence.models import TargetProgress, TargetSnapshot, TargetStatus
from app.modules.field_intelligence.summary import MissionSummaryError, summarize_mission

NOW = datetime(2026, 8, 16, 11, 0, tzinfo=timezone.utc)


def snapshot():
    return TargetSnapshot(
        tenant_id="tenant-a",
        created_at=NOW,
        location_ids=("a", "b", "c", "d"),
        fingerprint="a" * 64,
    )


def row(location: str, status: TargetStatus, tenant="tenant-a"):
    return TargetProgress(
        tenant_id=tenant,
        mission_id="mission-1",
        location_id=location,
        status=status,
        updated_at=NOW,
    )


def test_summary_uses_frozen_target_denominator_and_counts_missing_rows_as_unseen():
    result = summarize_mission(
        tenant_id="tenant-a",
        mission_id="mission-1",
        snapshot=snapshot(),
        progress_rows=[
            row("a", TargetStatus.VERIFIED),
            row("b", TargetStatus.SUBMITTED),
            row("c", TargetStatus.REWORK),
        ],
    )
    assert result.total_targets == 4
    assert result.verified == 1
    assert result.submitted == 1
    assert result.rework == 1
    assert result.unseen == 1
    assert result.completion_ratio == 0.25


def test_progress_outside_frozen_snapshot_is_rejected():
    with pytest.raises(MissionSummaryError, match="outside frozen"):
        summarize_mission(
            tenant_id="tenant-a",
            mission_id="mission-1",
            snapshot=snapshot(),
            progress_rows=[row("not-targeted", TargetStatus.VERIFIED)],
        )


def test_cross_tenant_progress_cannot_pollute_command_center():
    with pytest.raises(MissionSummaryError, match="scope mismatch"):
        summarize_mission(
            tenant_id="tenant-a",
            mission_id="mission-1",
            snapshot=snapshot(),
            progress_rows=[row("a", TargetStatus.VERIFIED, tenant="tenant-b")],
        )
