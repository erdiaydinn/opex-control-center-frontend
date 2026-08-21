from __future__ import annotations

from datetime import datetime

from .evidence import EvidenceEnvelope, EvidenceVerification, VerificationDecision
from .models import TargetProgress, TargetStatus


class MissionLifecycleError(ValueError):
    pass


_ALLOWED_PROGRESS: dict[TargetStatus, frozenset[TargetStatus]] = {
    TargetStatus.UNSEEN: frozenset({TargetStatus.SEEN, TargetStatus.STARTED, TargetStatus.EXEMPT, TargetStatus.OVERDUE}),
    TargetStatus.SEEN: frozenset({TargetStatus.STARTED, TargetStatus.EXEMPT, TargetStatus.OVERDUE}),
    TargetStatus.STARTED: frozenset({TargetStatus.PARTIAL, TargetStatus.SUBMITTED, TargetStatus.OVERDUE}),
    TargetStatus.PARTIAL: frozenset({TargetStatus.SUBMITTED, TargetStatus.OVERDUE}),
    TargetStatus.SUBMITTED: frozenset({TargetStatus.REWORK, TargetStatus.VERIFIED}),
    TargetStatus.REWORK: frozenset({TargetStatus.STARTED, TargetStatus.SUBMITTED, TargetStatus.OVERDUE}),
    TargetStatus.VERIFIED: frozenset(),
    TargetStatus.OVERDUE: frozenset({TargetStatus.STARTED, TargetStatus.SUBMITTED, TargetStatus.EXEMPT}),
    TargetStatus.EXEMPT: frozenset(),
}


def transition_progress(progress: TargetProgress, *, to_status: TargetStatus, at: datetime) -> TargetProgress:
    if to_status not in _ALLOWED_PROGRESS[progress.status]:
        raise MissionLifecycleError(f"invalid target transition: {progress.status.value} -> {to_status.value}")
    return progress.model_copy(update={"status": to_status, "updated_at": at})


def submit_evidence(progress: TargetProgress, envelope: EvidenceEnvelope, *, at: datetime) -> TargetProgress:
    if progress.tenant_id != envelope.tenant_id:
        raise MissionLifecycleError("evidence tenant does not match mission target")
    if progress.mission_id != envelope.mission_id or progress.location_id != envelope.location_id:
        raise MissionLifecycleError("evidence mission/location does not match target")
    if progress.status not in {TargetStatus.STARTED, TargetStatus.PARTIAL, TargetStatus.REWORK, TargetStatus.OVERDUE}:
        raise MissionLifecycleError("target is not in a submittable state")
    return progress.model_copy(update={"status": TargetStatus.SUBMITTED, "updated_at": at})


def apply_verification(
    progress: TargetProgress,
    envelope: EvidenceEnvelope,
    verification: EvidenceVerification,
) -> TargetProgress:
    if progress.status is not TargetStatus.SUBMITTED:
        raise MissionLifecycleError("verification requires submitted target state")
    expected = (progress.tenant_id, progress.mission_id, progress.location_id)
    if expected != (verification.tenant_id, verification.mission_id, verification.location_id):
        raise MissionLifecycleError("verification scope does not match mission target")
    if expected != (envelope.tenant_id, envelope.mission_id, envelope.location_id):
        raise MissionLifecycleError("evidence scope does not match mission target")
    if verification.envelope_fingerprint != envelope.fingerprint:
        raise MissionLifecycleError("verification references a different evidence envelope")

    if verification.decision is VerificationDecision.ACCEPT:
        status = TargetStatus.VERIFIED
    else:
        status = TargetStatus.REWORK
    return progress.model_copy(update={"status": status, "updated_at": verification.reviewed_at})
