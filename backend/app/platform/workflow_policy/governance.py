from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import WorkflowStatus


class WorkflowGovernanceError(ValueError):
    pass


_ALLOWED_TRANSITIONS: dict[WorkflowStatus, frozenset[WorkflowStatus]] = {
    WorkflowStatus.DRAFT: frozenset({WorkflowStatus.APPROVED, WorkflowStatus.DISABLED}),
    WorkflowStatus.APPROVED: frozenset({WorkflowStatus.EFFECTIVE, WorkflowStatus.DISABLED}),
    WorkflowStatus.EFFECTIVE: frozenset({WorkflowStatus.SUPERSEDED, WorkflowStatus.DISABLED}),
    WorkflowStatus.SUPERSEDED: frozenset(),
    WorkflowStatus.DISABLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class WorkflowGovernanceEvent:
    tenant_id: str
    workflow_id: str
    workflow_version: int
    from_status: WorkflowStatus
    to_status: WorkflowStatus
    actor_id: str
    occurred_at: datetime
    reason: str | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.workflow_id or not self.actor_id:
            raise WorkflowGovernanceError("tenant, workflow and actor are required")
        if self.workflow_version < 1:
            raise WorkflowGovernanceError("workflow version must be positive")
        if self.to_status not in _ALLOWED_TRANSITIONS[self.from_status]:
            raise WorkflowGovernanceError(
                f"invalid workflow governance transition: {self.from_status.value} -> {self.to_status.value}"
            )
        if self.to_status is WorkflowStatus.DISABLED and not (self.reason or "").strip():
            raise WorkflowGovernanceError("disabled workflow requires a reason")


def validate_status_transition(
    current: WorkflowStatus,
    target: WorkflowStatus,
) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise WorkflowGovernanceError(f"invalid workflow governance transition: {current.value} -> {target.value}")
