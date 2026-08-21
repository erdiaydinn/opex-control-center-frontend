from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import WorkflowDefinition, WorkflowStatus
from .simulation import PolicyImpactSummary


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


@dataclass(frozen=True, slots=True)
class WorkflowActivationEvidence:
    tenant_id: str
    workflow_id: str
    workflow_version: int
    impact_fingerprint: str
    simulated_event_count: int
    changed_event_count: int
    high_risk_changed_events: int
    reviewed_by: str
    reviewed_at: datetime
    high_risk_acknowledged: bool = False

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.workflow_id or not self.reviewed_by:
            raise WorkflowGovernanceError("activation evidence requires tenant, workflow and reviewer")
        if self.workflow_version < 1:
            raise WorkflowGovernanceError("activation evidence workflow version must be positive")
        if len(self.impact_fingerprint) != 64 or any(character not in "0123456789abcdef" for character in self.impact_fingerprint):
            raise WorkflowGovernanceError("activation evidence requires a SHA-256 impact fingerprint")
        if self.simulated_event_count < 1:
            raise WorkflowGovernanceError("workflow activation requires at least one simulated event")
        if not 0 <= self.changed_event_count <= self.simulated_event_count:
            raise WorkflowGovernanceError("activation changed-event count is invalid")
        if not 0 <= self.high_risk_changed_events <= self.changed_event_count:
            raise WorkflowGovernanceError("activation high-risk event count is invalid")
        if self.high_risk_changed_events and not self.high_risk_acknowledged:
            raise WorkflowGovernanceError("high-risk workflow impact requires explicit acknowledgment")


def validate_status_transition(
    current: WorkflowStatus,
    target: WorkflowStatus,
) -> None:
    if target not in _ALLOWED_TRANSITIONS[current]:
        raise WorkflowGovernanceError(f"invalid workflow governance transition: {current.value} -> {target.value}")


def validate_effective_promotion(
    candidate: WorkflowDefinition,
    impact: PolicyImpactSummary,
    evidence: WorkflowActivationEvidence,
) -> None:
    """Require reviewed dry-run impact evidence before an approved policy becomes effective."""
    if candidate.status is not WorkflowStatus.APPROVED:
        raise WorkflowGovernanceError("only approved workflow versions may be promoted to effective")
    if (
        impact.tenant_id != candidate.tenant_id
        or evidence.tenant_id != candidate.tenant_id
        or impact.workflow_id != candidate.workflow_id
        or evidence.workflow_id != candidate.workflow_id
        or impact.candidate_version != candidate.version
        or evidence.workflow_version != candidate.version
    ):
        raise WorkflowGovernanceError("workflow activation evidence scope/version mismatch")
    if evidence.impact_fingerprint != impact.impact_fingerprint:
        raise WorkflowGovernanceError("workflow activation evidence fingerprint mismatch")
    if evidence.simulated_event_count != impact.total_events:
        raise WorkflowGovernanceError("workflow activation simulation count mismatch")
    if evidence.changed_event_count != impact.changed_events:
        raise WorkflowGovernanceError("workflow activation changed-event count mismatch")
    if evidence.high_risk_changed_events != impact.high_risk_changed_events:
        raise WorkflowGovernanceError("workflow activation high-risk count mismatch")
    if impact.requires_high_risk_review and not evidence.high_risk_acknowledged:
        raise WorkflowGovernanceError("high-risk workflow impact requires explicit acknowledgment")
