from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from .models import TargetProgress, TargetSnapshot, TargetStatus


class MissionSummaryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MissionSummary:
    total_targets: int
    verified: int
    submitted: int
    rework: int
    in_progress: int
    unseen: int
    overdue: int
    exempt: int
    completion_ratio: float


def summarize_mission(
    *,
    tenant_id: str,
    mission_id: str,
    snapshot: TargetSnapshot,
    progress_rows: list[TargetProgress],
) -> MissionSummary:
    if snapshot.tenant_id != tenant_id:
        raise MissionSummaryError("target snapshot tenant mismatch")
    target_ids = set(snapshot.location_ids)
    rows_by_location: dict[str, TargetProgress] = {}
    for row in progress_rows:
        if row.tenant_id != tenant_id or row.mission_id != mission_id:
            raise MissionSummaryError("progress scope mismatch")
        if row.location_id not in target_ids:
            raise MissionSummaryError("progress contains location outside frozen target snapshot")
        if row.location_id in rows_by_location:
            raise MissionSummaryError("duplicate progress row for target location")
        rows_by_location[row.location_id] = row

    counts = Counter(row.status for row in rows_by_location.values())
    unseen = counts[TargetStatus.UNSEEN] + (len(target_ids) - len(rows_by_location))
    in_progress = sum(
        counts[status]
        for status in (TargetStatus.SEEN, TargetStatus.STARTED, TargetStatus.PARTIAL)
    )
    verified = counts[TargetStatus.VERIFIED]
    exempt = counts[TargetStatus.EXEMPT]
    denominator = max(1, len(target_ids) - exempt)
    completion = verified / denominator

    return MissionSummary(
        total_targets=len(target_ids),
        verified=verified,
        submitted=counts[TargetStatus.SUBMITTED],
        rework=counts[TargetStatus.REWORK],
        in_progress=in_progress,
        unseen=unseen,
        overdue=counts[TargetStatus.OVERDUE],
        exempt=exempt,
        completion_ratio=completion,
    )
