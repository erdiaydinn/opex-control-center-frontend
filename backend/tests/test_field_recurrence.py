from datetime import datetime, timedelta, timezone

from app.modules.field_intelligence.models import (
    LocalizedMessage,
    LocationRecord,
    MissionDefinition,
    MissionStatus,
    TargetSelector,
)
from app.modules.field_intelligence.recurrence import materialize_occurrence

NOW = datetime(2026, 8, 16, 12, 0, tzinfo=timezone.utc)


def mission():
    text = LocalizedMessage(values={"tr": "Kontrol", "en": "Check"})
    return MissionDefinition(
        mission_id="weekly-fixture-check",
        tenant_id="tenant-a",
        template_id="fixture-check",
        template_version=1,
        title=text,
        instructions=text,
        status=MissionStatus.ACTIVE,
        target_selector=TargetSelector(tenant_id="tenant-a", cities=("Istanbul",)),
        assigned_at=NOW,
        deadline_at=NOW + timedelta(hours=2),
    )


def location(location_id: str):
    return LocationRecord(
        tenant_id="tenant-a",
        location_id=location_id,
        country="TR",
        region="Marmara",
        city="Istanbul",
        district="Kadikoy",
    )


def test_new_location_enters_next_occurrence_without_mutating_previous_snapshot():
    first = materialize_occurrence(
        mission(), occurrence_id="2026-w33", scheduled_for=NOW, locations=[location("a")]
    )
    second = materialize_occurrence(
        mission(),
        occurrence_id="2026-w34",
        scheduled_for=NOW + timedelta(days=7),
        locations=[location("a"), location("b")],
    )
    assert first.target_snapshot.location_ids == ("a",)
    assert second.target_snapshot.location_ids == ("a", "b")
    assert first.target_snapshot.fingerprint != second.target_snapshot.fingerprint
