from __future__ import annotations

from pydantic import BaseModel, Field

from .models import ReminderAction


class OrganizationAssignment(BaseModel):
    tenant_id: str = Field(min_length=1)
    subject_id: str = Field(min_length=1)
    role: str = Field(min_length=1)
    location_ids: frozenset[str] = Field(min_length=1)
    active: bool = True


class AccountabilityRoutingError(LookupError):
    pass


def resolve_reminder_recipients(
    action: ReminderAction,
    *,
    tenant_id: str,
    target_subject_id: str,
    assignments: list[OrganizationAssignment],
) -> tuple[str, ...]:
    """Resolve reminder/escalation subjects using server-authoritative org assignments."""
    if not target_subject_id.strip():
        raise AccountabilityRoutingError("target subject is required")

    if not action.escalate_to_role:
        return (target_subject_id,)

    recipients = sorted(
        {
            assignment.subject_id
            for assignment in assignments
            if assignment.active
            and assignment.tenant_id == tenant_id
            and assignment.role == action.escalate_to_role
            and action.location_id in assignment.location_ids
        }
    )
    if not recipients:
        raise AccountabilityRoutingError("no authoritative escalation recipient for target location")
    return tuple(recipients)
