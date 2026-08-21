from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from .models import LocationRecord, MissionDefinition, TargetSnapshot
from .targeting import resolve_target_snapshot


class MissionOccurrence(BaseModel):
    tenant_id: str
    mission_id: str
    occurrence_id: str = Field(min_length=3, max_length=140)
    scheduled_for: datetime
    target_snapshot: TargetSnapshot


def materialize_occurrence(
    mission: MissionDefinition,
    *,
    occurrence_id: str,
    scheduled_for: datetime,
    locations: list[LocationRecord],
) -> MissionOccurrence:
    """Resolve the current hierarchy once, then freeze it for this occurrence."""
    snapshot = resolve_target_snapshot(locations, mission.target_selector, created_at=scheduled_for)
    return MissionOccurrence(
        tenant_id=mission.tenant_id,
        mission_id=mission.mission_id,
        occurrence_id=occurrence_id,
        scheduled_for=scheduled_for,
        target_snapshot=snapshot,
    )
