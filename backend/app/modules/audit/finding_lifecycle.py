"""Roadmap 24/60: Audit finding -> corrective action -> verification authority.

The lifecycle is immutable: every operation returns a new aggregate with appended
records. Tenant and exact audit-run provenance stay pinned to the finding.
Evidence references are provenance only; this module does not claim physical
evidence storage or field verification.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any, Mapping
from uuid import UUID, uuid4

from .template_authority import AuditRunSnapshot


class AuditFindingError(ValueError):
    """Raised when a governed finding lifecycle transition is invalid."""


class FindingSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    OBSERVATION = "observation"


class FindingState(StrEnum):
    OPEN = "open"
    ACTION_IN_PROGRESS = "action_in_progress"
    READY_FOR_VERIFICATION = "ready_for_verification"
    CLOSED = "closed"
    REOPENED = "reopened"


class VerificationOutcome(StrEnum):
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class AuditFinding:
    finding_id: UUID
    tenant_id: str
    audit_run_id: UUID
    audit_snapshot_hash: str
    template_key: str
    template_revision: int
    template_hash: str
    question_id: str
    severity: FindingSeverity
    title: str
    description: str
    opened_by: str
    opened_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectiveAction:
    action_id: UUID
    finding_id: UUID
    tenant_id: str
    owner_subject: str
    description: str
    due_at: datetime
    created_by: str
    created_at: datetime


@dataclass(frozen=True, slots=True)
class CorrectiveEvidence:
    evidence_id: UUID
    finding_id: UUID
    action_id: UUID
    tenant_id: str
    evidence_ref: str
    sha256: str
    provenance: tuple[tuple[str, str], ...]
    attached_by: str
    attached_at: datetime


@dataclass(frozen=True, slots=True)
class FindingVerification:
    verification_id: UUID
    finding_id: UUID
    action_id: UUID
    tenant_id: str
    verifier_subject: str
    outcome: VerificationOutcome
    rationale: str
    verified_at: datetime


@dataclass(frozen=True, slots=True)
class FindingReopen:
    reopen_id: UUID
    finding_id: UUID
    tenant_id: str
    reopened_by: str
    reason: str
    reopened_at: datetime


@dataclass(frozen=True, slots=True)
class FindingLifecycle:
    finding: AuditFinding
    actions: tuple[CorrectiveAction, ...] = ()
    evidence: tuple[CorrectiveEvidence, ...] = ()
    verifications: tuple[FindingVerification, ...] = ()
    reopens: tuple[FindingReopen, ...] = ()

    @property
    def state(self) -> FindingState:
        latest_pass = max(
            (row for row in self.verifications if row.outcome is VerificationOutcome.PASSED),
            key=lambda row: row.verified_at,
            default=None,
        )
        latest_failed = max(
            (row for row in self.verifications if row.outcome is VerificationOutcome.FAILED),
            key=lambda row: row.verified_at,
            default=None,
        )
        latest_reopen = max(self.reopens, key=lambda row: row.reopened_at, default=None)

        restart_times = [
            row.verified_at for row in (latest_failed,) if row is not None
        ] + [
            row.reopened_at for row in (latest_reopen,) if row is not None
        ]
        restart_at = max(restart_times, default=None)

        if latest_pass is not None and (restart_at is None or latest_pass.verified_at > restart_at):
            return FindingState.CLOSED

        cycle_actions = tuple(
            row for row in self.actions if restart_at is None or row.created_at > restart_at
        )
        if not cycle_actions:
            if restart_at is not None:
                return FindingState.REOPENED
            return FindingState.OPEN

        latest_action = max(cycle_actions, key=lambda row: row.created_at)
        if any(item.action_id == latest_action.action_id for item in self.evidence):
            return FindingState.READY_FOR_VERIFICATION
        return FindingState.ACTION_IN_PROGRESS


def open_finding(
    run: AuditRunSnapshot,
    *,
    question_id: str,
    severity: FindingSeverity,
    title: str,
    description: str,
    actor: str,
    opened_at: datetime | None = None,
    finding_id: UUID | None = None,
) -> FindingLifecycle:
    question_id = question_id.strip()
    title = title.strip()
    description = description.strip()
    actor = actor.strip()
    if not question_id or question_id not in run.visible_question_ids:
        raise AuditFindingError("finding must reference a visible question in the exact audit snapshot")
    if not title or not description or not actor:
        raise AuditFindingError("title, description and actor are required")
    finding = AuditFinding(
        finding_id=finding_id or uuid4(),
        tenant_id=run.tenant_id,
        audit_run_id=run.audit_run_id,
        audit_snapshot_hash=_hex64(run.snapshot_hash, "audit snapshot hash"),
        template_key=run.template_key,
        template_revision=run.template_revision,
        template_hash=_hex64(run.template_hash, "template hash"),
        question_id=question_id,
        severity=severity,
        title=title,
        description=description,
        opened_by=actor,
        opened_at=_utc(opened_at or datetime.now(UTC)),
    )
    return FindingLifecycle(finding=finding)


def add_corrective_action(
    lifecycle: FindingLifecycle,
    *,
    owner_subject: str,
    description: str,
    due_at: datetime,
    actor: str,
    created_at: datetime | None = None,
    action_id: UUID | None = None,
) -> FindingLifecycle:
    if lifecycle.state is FindingState.CLOSED:
        raise AuditFindingError("closed finding must be explicitly reopened before a new action")
    owner_subject = owner_subject.strip()
    description = description.strip()
    actor = actor.strip()
    if not owner_subject or not description or not actor:
        raise AuditFindingError("owner, description and actor are required")
    created_at = _utc(created_at or datetime.now(UTC))
    due_at = _utc(due_at)
    if due_at <= created_at:
        raise AuditFindingError("corrective action due_at must be after created_at")
    action = CorrectiveAction(
        action_id=action_id or uuid4(),
        finding_id=lifecycle.finding.finding_id,
        tenant_id=lifecycle.finding.tenant_id,
        owner_subject=owner_subject,
        description=description,
        due_at=due_at,
        created_by=actor,
        created_at=created_at,
    )
    return replace(lifecycle, actions=(*lifecycle.actions, action))


def attach_evidence(
    lifecycle: FindingLifecycle,
    *,
    action_id: UUID,
    evidence_ref: str,
    content_sha256: str,
    actor: str,
    provenance: Mapping[str, str] | None = None,
    attached_at: datetime | None = None,
    evidence_id: UUID | None = None,
) -> FindingLifecycle:
    action = _action(lifecycle, action_id)
    evidence_ref = evidence_ref.strip()
    actor = actor.strip()
    if not evidence_ref or not actor:
        raise AuditFindingError("evidence_ref and actor are required")
    provenance_items = tuple(sorted((str(k), str(v)) for k, v in (provenance or {}).items()))
    evidence = CorrectiveEvidence(
        evidence_id=evidence_id or uuid4(),
        finding_id=lifecycle.finding.finding_id,
        action_id=action.action_id,
        tenant_id=lifecycle.finding.tenant_id,
        evidence_ref=evidence_ref,
        sha256=_hex64(content_sha256, "evidence sha256"),
        provenance=provenance_items,
        attached_by=actor,
        attached_at=_utc(attached_at or datetime.now(UTC)),
    )
    return replace(lifecycle, evidence=(*lifecycle.evidence, evidence))


def verify_corrective_action(
    lifecycle: FindingLifecycle,
    *,
    action_id: UUID,
    verifier_subject: str,
    outcome: VerificationOutcome,
    rationale: str,
    verified_at: datetime | None = None,
    verification_id: UUID | None = None,
) -> FindingLifecycle:
    if lifecycle.state is FindingState.CLOSED:
        raise AuditFindingError("closed finding must be reopened before another verification")
    action = _action(lifecycle, action_id)
    verifier_subject = verifier_subject.strip()
    rationale = rationale.strip()
    if not verifier_subject or not rationale:
        raise AuditFindingError("verifier and rationale are required")
    if verifier_subject == action.owner_subject:
        raise AuditFindingError("corrective action owner cannot verify their own action")
    if outcome is VerificationOutcome.PASSED and not any(
        item.action_id == action_id for item in lifecycle.evidence
    ):
        raise AuditFindingError("passed verification requires corrective evidence")
    verification = FindingVerification(
        verification_id=verification_id or uuid4(),
        finding_id=lifecycle.finding.finding_id,
        action_id=action_id,
        tenant_id=lifecycle.finding.tenant_id,
        verifier_subject=verifier_subject,
        outcome=outcome,
        rationale=rationale,
        verified_at=_utc(verified_at or datetime.now(UTC)),
    )
    return replace(lifecycle, verifications=(*lifecycle.verifications, verification))


def reopen_finding(
    lifecycle: FindingLifecycle,
    *,
    actor: str,
    reason: str,
    reopened_at: datetime | None = None,
    reopen_id: UUID | None = None,
) -> FindingLifecycle:
    if lifecycle.state is not FindingState.CLOSED:
        raise AuditFindingError("only a closed finding can be explicitly reopened")
    actor = actor.strip()
    reason = reason.strip()
    if not actor or not reason:
        raise AuditFindingError("reopen actor and reason are required")
    reopen = FindingReopen(
        reopen_id=reopen_id or uuid4(),
        finding_id=lifecycle.finding.finding_id,
        tenant_id=lifecycle.finding.tenant_id,
        reopened_by=actor,
        reason=reason,
        reopened_at=_utc(reopened_at or datetime.now(UTC)),
    )
    return replace(lifecycle, reopens=(*lifecycle.reopens, reopen))


def lifecycle_receipt(lifecycle: FindingLifecycle) -> str:
    """Deterministic receipt for the complete immutable lifecycle history."""
    payload = {
        "finding": _record(lifecycle.finding),
        "actions": [_record(item) for item in lifecycle.actions],
        "evidence": [_record(item) for item in lifecycle.evidence],
        "verifications": [_record(item) for item in lifecycle.verifications],
        "reopens": [_record(item) for item in lifecycle.reopens],
        "state": lifecycle.state.value,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(encoded.encode("utf-8")).hexdigest()


def _action(lifecycle: FindingLifecycle, action_id: UUID) -> CorrectiveAction:
    for action in lifecycle.actions:
        if action.action_id == action_id:
            return action
    raise AuditFindingError("corrective action does not belong to this finding lifecycle")


def _record(value: Any) -> dict[str, Any]:
    return {
        field: (
            data.value if isinstance(data, StrEnum)
            else str(data) if isinstance(data, UUID)
            else data.isoformat() if isinstance(data, datetime)
            else list(data) if isinstance(data, tuple)
            else data
        )
        for field, data in (
            (slot, getattr(value, slot))
            for slot in value.__slots__
        )
    }


def _hex64(value: str, label: str) -> str:
    value = value.strip().lower()
    if len(value) != 64 or any(ch not in "0123456789abcdef" for ch in value):
        raise AuditFindingError(f"{label} must be a 64-character lowercase hex digest")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise AuditFindingError("timestamps must be timezone-aware")
    return value.astimezone(UTC)
