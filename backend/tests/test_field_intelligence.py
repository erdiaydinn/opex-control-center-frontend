from datetime import datetime, timedelta, timezone

import pytest

from app.modules.field_intelligence.models import (
    LocalizedMessage,
    LocationRecord,
    MissionDefinition,
    MissionPriority,
    MissionStatus,
    ReminderChannel,
    ReminderPolicy,
    ReminderStep,
    ReminderTrigger,
    TargetProgress,
    TargetSelector,
    TargetStatus,
)
from app.modules.field_intelligence.reminders import evaluate_reminders
from app.modules.field_intelligence.targeting import TargetResolutionError, resolve_target_snapshot


NOW = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)


def location(location_id: str, *, tenant="tenant-a", region="Marmara", city="Istanbul", district="Kadikoy", active=True):
    return LocationRecord(
        tenant_id=tenant,
        location_id=location_id,
        country="TR",
        region=region,
        city=city,
        district=district,
        groups=("market",),
        active=active,
    )


def message(text: str) -> LocalizedMessage:
    return LocalizedMessage(values={"tr": text, "en": text})


def test_city_and_district_targeting_is_conjunctive_and_cross_tenant_safe():
    selector = TargetSelector(tenant_id="tenant-a", cities=("Istanbul",), districts=("Kadikoy",))
    snapshot = resolve_target_snapshot(
        [
            location("kadikoy"),
            location("besiktas", district="Besiktas"),
            location("other-tenant", tenant="tenant-b"),
            location("inactive", active=False),
        ],
        selector,
        created_at=NOW,
    )
    assert snapshot.location_ids == ("kadikoy",)


def test_manual_include_can_extend_structured_scope_but_explicit_exclude_wins():
    selector = TargetSelector(
        tenant_id="tenant-a",
        cities=("Istanbul",),
        districts=("Kadikoy",),
        include_location_ids=("ankara",),
        exclude_location_ids=("kadikoy",),
    )
    snapshot = resolve_target_snapshot(
        [location("kadikoy"), location("ankara", region="Anadolu", city="Ankara", district="Cankaya")],
        selector,
        created_at=NOW,
    )
    assert snapshot.location_ids == ("ankara",)


def test_target_snapshot_is_frozen_and_deterministic_for_same_inputs():
    selector = TargetSelector(tenant_id="tenant-a", all_active_locations=True)
    first = resolve_target_snapshot([location("b"), location("a")], selector, created_at=NOW)
    second = resolve_target_snapshot([location("a"), location("b")], selector, created_at=NOW)
    assert first.location_ids == ("a", "b")
    assert first.fingerprint == second.fingerprint


def test_zero_target_selection_fails_closed():
    selector = TargetSelector(tenant_id="tenant-a", cities=("Izmir",))
    with pytest.raises(TargetResolutionError, match="zero active locations"):
        resolve_target_snapshot([location("istanbul")], selector, created_at=NOW)


def build_mission(priority=MissionPriority.NORMAL):
    return MissionDefinition(
        mission_id="lot-check-001",
        tenant_id="tenant-a",
        template_id="lot-check",
        template_version=1,
        title=message("Lot kontrolü"),
        instructions=message("Barkod ve lot bilgisini doğrulayın"),
        priority=priority,
        status=MissionStatus.ACTIVE,
        target_selector=TargetSelector(tenant_id="tenant-a", all_active_locations=True),
        assigned_at=NOW,
        deadline_at=NOW + timedelta(hours=2),
        reminder_policy=ReminderPolicy(
            steps=(
                ReminderStep(
                    step_id="unseen-30m",
                    trigger=ReminderTrigger.AFTER_ASSIGNMENT,
                    offset_minutes=30,
                    channels=(ReminderChannel.IN_APP, ReminderChannel.PUSH),
                    eligible_statuses=(TargetStatus.UNSEEN,),
                    message=message("Göreviniz bekliyor"),
                ),
                ReminderStep(
                    step_id="deadline-15m",
                    trigger=ReminderTrigger.BEFORE_DEADLINE,
                    offset_minutes=15,
                    channels=(ReminderChannel.PUSH,),
                    eligible_statuses=(TargetStatus.UNSEEN, TargetStatus.SEEN, TargetStatus.STARTED, TargetStatus.PARTIAL),
                    message=message("Son 15 dakika"),
                ),
                ReminderStep(
                    step_id="manager-overdue",
                    trigger=ReminderTrigger.AFTER_DEADLINE,
                    offset_minutes=0,
                    channels=(ReminderChannel.IN_APP, ReminderChannel.EMAIL),
                    eligible_statuses=(TargetStatus.OVERDUE,),
                    escalate_to_role="store_manager",
                    message=message("Görev gecikti"),
                ),
            ),
            digest_non_critical=True,
            max_notifications_per_target_per_day=4,
        ),
    )


def test_noncritical_reminders_digest_to_one_due_action():
    mission = build_mission()
    progress = TargetProgress(
        tenant_id="tenant-a",
        mission_id=mission.mission_id,
        location_id="store-1",
        status=TargetStatus.UNSEEN,
        updated_at=NOW,
    )
    actions = evaluate_reminders(mission, progress, now=NOW + timedelta(hours=1, minutes=50))
    assert len(actions) == 1
    assert actions[0].step_id == "unseen-30m"


def test_critical_mission_can_emit_multiple_due_actions_without_digest():
    mission = build_mission(priority=MissionPriority.CRITICAL)
    progress = TargetProgress(
        tenant_id="tenant-a",
        mission_id=mission.mission_id,
        location_id="store-1",
        status=TargetStatus.UNSEEN,
        updated_at=NOW,
    )
    actions = evaluate_reminders(mission, progress, now=NOW + timedelta(hours=1, minutes=50))
    assert [action.step_id for action in actions] == ["unseen-30m", "deadline-15m"]


def test_overdue_escalates_to_authoritative_role_and_sent_step_is_not_replayed():
    mission = build_mission()
    progress = TargetProgress(
        tenant_id="tenant-a",
        mission_id=mission.mission_id,
        location_id="store-1",
        status=TargetStatus.OVERDUE,
        updated_at=NOW + timedelta(hours=2),
    )
    actions = evaluate_reminders(
        mission,
        progress,
        now=NOW + timedelta(hours=2, minutes=1),
        already_sent_step_ids={"unseen-30m", "deadline-15m"},
    )
    assert len(actions) == 1
    assert actions[0].step_id == "manager-overdue"
    assert actions[0].escalate_to_role == "store_manager"


def test_notification_daily_cap_stops_spam():
    mission = build_mission()
    progress = TargetProgress(
        tenant_id="tenant-a",
        mission_id=mission.mission_id,
        location_id="store-1",
        status=TargetStatus.UNSEEN,
        updated_at=NOW,
        notification_count_today=4,
    )
    assert evaluate_reminders(mission, progress, now=NOW + timedelta(hours=1)) == ()


def test_localization_rejects_non_platform_locale():
    with pytest.raises(ValueError, match="unsupported locales"):
        LocalizedMessage(values={"xx": "unsupported"})
