from datetime import datetime, timezone

from app.modules.field_intelligence.models import LocalizedMessage, ReminderAction, ReminderChannel
from app.modules.field_intelligence.notification import NotificationEventStatus, build_notification_events

NOW = datetime(2026, 8, 16, 13, 30, tzinfo=timezone.utc)


def action():
    return ReminderAction(
        mission_id="mission-1",
        location_id="store-1",
        step_id="deadline-minus-30",
        channels=(ReminderChannel.PUSH, ReminderChannel.IN_APP),
        message=LocalizedMessage(values={"tr": "Göreviniz bekliyor", "en": "Mission pending"}),
    )


def test_same_reminder_recipient_and_channel_produce_stable_idempotency_keys():
    first = build_notification_events(
        action(), tenant_id="tenant-a", recipient_subjects=("employee-1",), created_at=NOW
    )
    second = build_notification_events(
        action(), tenant_id="tenant-a", recipient_subjects=("employee-1",), created_at=NOW
    )
    assert [event.idempotency_key for event in first] == [event.idempotency_key for event in second]
    assert all(event.status is NotificationEventStatus.PENDING for event in first)


def test_duplicate_recipients_are_deduplicated_before_dispatch():
    events = build_notification_events(
        action(),
        tenant_id="tenant-a",
        recipient_subjects=("employee-1", "employee-1"),
        created_at=NOW,
    )
    assert len(events) == 2
    assert {event.channel for event in events} == {ReminderChannel.PUSH, ReminderChannel.IN_APP}


def test_tenant_changes_dispatch_idempotency_namespace():
    a = build_notification_events(action(), tenant_id="tenant-a", recipient_subjects=("employee-1",), created_at=NOW)
    b = build_notification_events(action(), tenant_id="tenant-b", recipient_subjects=("employee-1",), created_at=NOW)
    assert {event.idempotency_key for event in a}.isdisjoint({event.idempotency_key for event in b})
