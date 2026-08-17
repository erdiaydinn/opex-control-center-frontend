from datetime import UTC, datetime

import pytest

from app.platform.workflow_policy.governance import (
    WorkflowGovernanceError,
    WorkflowGovernanceEvent,
    validate_status_transition,
)
from app.platform.workflow_policy.models import WorkflowStatus


NOW = datetime(2026, 8, 16, 12, 0, tzinfo=UTC)


def test_workflow_governance_happy_path_is_explicit() -> None:
    validate_status_transition(WorkflowStatus.DRAFT, WorkflowStatus.APPROVED)
    validate_status_transition(WorkflowStatus.APPROVED, WorkflowStatus.EFFECTIVE)
    validate_status_transition(WorkflowStatus.EFFECTIVE, WorkflowStatus.SUPERSEDED)


def test_effective_workflow_cannot_jump_back_to_draft_or_approved() -> None:
    with pytest.raises(WorkflowGovernanceError, match="invalid"):
        validate_status_transition(WorkflowStatus.EFFECTIVE, WorkflowStatus.DRAFT)
    with pytest.raises(WorkflowGovernanceError, match="invalid"):
        validate_status_transition(WorkflowStatus.EFFECTIVE, WorkflowStatus.APPROVED)


def test_superseded_and_disabled_workflows_are_terminal() -> None:
    for current in (WorkflowStatus.SUPERSEDED, WorkflowStatus.DISABLED):
        with pytest.raises(WorkflowGovernanceError, match="invalid"):
            validate_status_transition(current, WorkflowStatus.EFFECTIVE)


def test_disable_requires_reason_and_actor_scope() -> None:
    with pytest.raises(WorkflowGovernanceError, match="requires a reason"):
        WorkflowGovernanceEvent(
            tenant_id="tenant-a",
            workflow_id="late-order-recovery",
            workflow_version=1,
            from_status=WorkflowStatus.EFFECTIVE,
            to_status=WorkflowStatus.DISABLED,
            actor_id="ops-owner",
            occurred_at=NOW,
        )

    event = WorkflowGovernanceEvent(
        tenant_id="tenant-a",
        workflow_id="late-order-recovery",
        workflow_version=1,
        from_status=WorkflowStatus.EFFECTIVE,
        to_status=WorkflowStatus.DISABLED,
        actor_id="ops-owner",
        occurred_at=NOW,
        reason="rollback during controlled pilot",
    )
    assert event.to_status is WorkflowStatus.DISABLED
