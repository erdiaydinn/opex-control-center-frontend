from __future__ import annotations

from datetime import datetime, timedelta

from .models import (
    MissionDefinition,
    MissionPriority,
    ReminderAction,
    ReminderStep,
    ReminderTrigger,
    TargetProgress,
)


def _due_at(mission: MissionDefinition, step: ReminderStep) -> datetime:
    offset = timedelta(minutes=step.offset_minutes)
    if step.trigger is ReminderTrigger.AFTER_ASSIGNMENT:
        return mission.assigned_at + offset
    if step.trigger is ReminderTrigger.BEFORE_DEADLINE:
        return mission.deadline_at - offset
    if step.trigger is ReminderTrigger.AFTER_DEADLINE:
        return mission.deadline_at + offset
    if step.trigger is ReminderTrigger.REWORK_REQUIRED:
        return mission.assigned_at
    raise ValueError(f"unsupported reminder trigger: {step.trigger}")


def evaluate_reminders(
    mission: MissionDefinition,
    progress: TargetProgress,
    *,
    now: datetime,
    already_sent_step_ids: set[str] | None = None,
) -> tuple[ReminderAction, ...]:
    if progress.tenant_id != mission.tenant_id or progress.mission_id != mission.mission_id:
        raise ValueError("mission/progress identity mismatch")
    sent = already_sent_step_ids or set()
    if progress.notification_count_today >= mission.reminder_policy.max_notifications_per_target_per_day:
        return ()

    actions: list[ReminderAction] = []
    for step in mission.reminder_policy.steps:
        if step.step_id in sent or progress.status not in step.eligible_statuses:
            continue
        if step.trigger is ReminderTrigger.REWORK_REQUIRED:
            due = progress.updated_at
        else:
            due = _due_at(mission, step)
        if now < due:
            continue
        actions.append(
            ReminderAction(
                mission_id=mission.mission_id,
                location_id=progress.location_id,
                step_id=step.step_id,
                channels=step.channels,
                escalate_to_role=step.escalate_to_role,
                message=step.message,
            )
        )
        if (
            mission.priority is not MissionPriority.CRITICAL
            and mission.reminder_policy.digest_non_critical
        ):
            break
        if progress.notification_count_today + len(actions) >= mission.reminder_policy.max_notifications_per_target_per_day:
            break
    return tuple(actions)
