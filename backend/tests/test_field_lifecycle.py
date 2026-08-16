from datetime import datetime, timezone

import pytest

from app.modules.field_intelligence.evidence import (
    EvidenceCaptureSource,
    EvidenceItem,
    EvidenceKind,
    EvidencePolicy,
    EvidenceVerification,
    VerificationDecision,
    build_evidence_envelope,
)
from app.modules.field_intelligence.lifecycle import MissionLifecycleError, apply_verification, submit_evidence, transition_progress
from app.modules.field_intelligence.models import TargetProgress, TargetStatus

NOW = datetime(2026, 8, 16, 10, 0, tzinfo=timezone.utc)


def progress(status: TargetStatus) -> TargetProgress:
    return TargetProgress(
        tenant_id="tenant-a",
        mission_id="lot-check-001",
        location_id="store-1",
        status=status,
        updated_at=NOW,
    )


def envelope(tenant="tenant-a", location="store-1"):
    item = EvidenceItem(
        evidence_id="barcode-1",
        tenant_id=tenant,
        mission_id="lot-check-001",
        location_id=location,
        actor_id="employee-1",
        kind=EvidenceKind.BARCODE,
        capture_source=EvidenceCaptureSource.SCANNER,
        captured_at=NOW,
        value="8690000000001",
    )
    return build_evidence_envelope(
        policy=EvidencePolicy(required_kinds=(EvidenceKind.BARCODE,)),
        tenant_id=tenant,
        mission_id="lot-check-001",
        location_id=location,
        actor_id="employee-1",
        submitted_at=NOW,
        items=(item,),
    )


def test_client_cannot_jump_from_unseen_directly_to_verified():
    with pytest.raises(MissionLifecycleError, match="invalid target transition"):
        transition_progress(progress(TargetStatus.UNSEEN), to_status=TargetStatus.VERIFIED, at=NOW)


def test_submission_requires_submittable_state_and_matching_scope():
    with pytest.raises(MissionLifecycleError, match="not in a submittable state"):
        submit_evidence(progress(TargetStatus.UNSEEN), envelope(), at=NOW)
    with pytest.raises(MissionLifecycleError, match="tenant"):
        submit_evidence(progress(TargetStatus.STARTED), envelope(tenant="tenant-b"), at=NOW)


def test_accepting_exact_envelope_moves_submission_to_verified():
    env = envelope()
    submitted = submit_evidence(progress(TargetStatus.STARTED), env, at=NOW)
    verification = EvidenceVerification(
        tenant_id="tenant-a",
        mission_id="lot-check-001",
        location_id="store-1",
        envelope_fingerprint=env.fingerprint,
        reviewer_id="manager-1",
        decision=VerificationDecision.ACCEPT,
        reviewed_at=NOW,
    )
    result = apply_verification(submitted, env, verification)
    assert result.status is TargetStatus.VERIFIED


def test_rework_keeps_history_but_reopens_target():
    env = envelope()
    submitted = submit_evidence(progress(TargetStatus.REWORK), env, at=NOW)
    verification = EvidenceVerification(
        tenant_id="tenant-a",
        mission_id="lot-check-001",
        location_id="store-1",
        envelope_fingerprint=env.fingerprint,
        reviewer_id="manager-1",
        decision=VerificationDecision.REWORK,
        reason="Lot etiketi okunmuyor",
        reviewed_at=NOW,
    )
    result = apply_verification(submitted, env, verification)
    assert result.status is TargetStatus.REWORK


def test_verification_cannot_be_replayed_against_another_envelope():
    env = envelope()
    other = envelope(location="store-2")
    submitted = submit_evidence(progress(TargetStatus.STARTED), env, at=NOW)
    verification = EvidenceVerification(
        tenant_id="tenant-a",
        mission_id="lot-check-001",
        location_id="store-1",
        envelope_fingerprint=other.fingerprint,
        reviewer_id="manager-1",
        decision=VerificationDecision.ACCEPT,
        reviewed_at=NOW,
    )
    with pytest.raises(MissionLifecycleError):
        apply_verification(submitted, env, verification)
