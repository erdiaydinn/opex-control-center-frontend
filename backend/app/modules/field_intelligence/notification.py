from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from .models import ReminderAction, ReminderChannel


class NotificationEventStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    DEAD = "dead"


class NotificationDispatchEvent(BaseModel):
    tenant_id: str = Field(min_length=1)
    mission_id: str = Field(min_length=3)
    location_id: str = Field(min_length=1)
    step_id: str = Field(min_length=1)
    recipient_subject: str = Field(min_length=1)
    channel: ReminderChannel
    status: NotificationEventStatus = NotificationEventStatus.PENDING
    idempotency_key: str = Field(min_length=16, max_length=128)
    created_at: datetime


def build_notification_events(
    action: ReminderAction,
    *,
    tenant_id: str,
    recipient_subjects: tuple[str, ...],
    created_at: datetime,
) -> tuple[NotificationDispatchEvent, ...]:
    if not recipient_subjects:
        raise ValueError("notification dispatch requires at least one authoritative recipient")
    events: list[NotificationDispatchEvent] = []
    for recipient in sorted(set(recipient_subjects)):
        for channel in sorted(set(action.channels), key=lambda item: item.value):
            canonical = "|".join(
                [tenant_id, action.mission_id, action.location_id, action.step_id, recipient, channel.value]
            )
            key = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
            events.append(
                NotificationDispatchEvent(
                    tenant_id=tenant_id,
                    mission_id=action.mission_id,
                    location_id=action.location_id,
                    step_id=action.step_id,
                    recipient_subject=recipient,
                    channel=channel,
                    idempotency_key=key,
                    created_at=created_at,
                )
            )
    return tuple(events)
