import pytest

from app.modules.field_intelligence.accountability import (
    AccountabilityRoutingError,
    OrganizationAssignment,
    resolve_reminder_recipients,
)
from app.modules.field_intelligence.models import LocalizedMessage, ReminderAction, ReminderChannel


def action(role=None, location="store-1"):
    return ReminderAction(
        mission_id="mission-1",
        location_id=location,
        step_id="overdue",
        channels=(ReminderChannel.IN_APP,),
        escalate_to_role=role,
        message=LocalizedMessage(values={"tr": "Görev gecikti", "en": "Mission overdue"}),
    )


def assignment(subject, role, locations, tenant="tenant-a", active=True):
    return OrganizationAssignment(
        tenant_id=tenant,
        subject_id=subject,
        role=role,
        location_ids=frozenset(locations),
        active=active,
    )


def test_non_escalated_reminder_routes_only_to_target_subject():
    assert resolve_reminder_recipients(
        action(), tenant_id="tenant-a", target_subject_id="employee-1", assignments=[]
    ) == ("employee-1",)


def test_escalation_routes_only_to_active_manager_covering_target_location():
    recipients = resolve_reminder_recipients(
        action("regional_manager"),
        tenant_id="tenant-a",
        target_subject_id="employee-1",
        assignments=[
            assignment("rm-istanbul", "regional_manager", {"store-1", "store-2"}),
            assignment("rm-ankara", "regional_manager", {"store-3"}),
            assignment("old-rm", "regional_manager", {"store-1"}, active=False),
            assignment("other-tenant", "regional_manager", {"store-1"}, tenant="tenant-b"),
        ],
    )
    assert recipients == ("rm-istanbul",)


def test_missing_authoritative_manager_fails_closed_instead_of_broadcasting():
    with pytest.raises(AccountabilityRoutingError, match="no authoritative escalation recipient"):
        resolve_reminder_recipients(
            action("regional_manager"),
            tenant_id="tenant-a",
            target_subject_id="employee-1",
            assignments=[assignment("rm-other", "regional_manager", {"store-9"})],
        )
