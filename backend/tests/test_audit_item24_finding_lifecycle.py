from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.audit.finding_lifecycle import (
    AuditFindingError,
    FindingSeverity,
    FindingState,
    VerificationOutcome,
    add_corrective_action,
    attach_evidence,
    lifecycle_receipt,
    open_finding,
    reopen_finding,
    verify_corrective_action,
)
from app.modules.audit.template_authority import AuditRunSnapshot


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
RUN_ID = UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa")
FINDING_ID = UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")
ACTION_ID = UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc")
EVIDENCE_ID = UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd")
VERIFY_ID = UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")
REOPEN_ID = UUID("ffffffff-ffff-4fff-8fff-ffffffffffff")


def _run(tenant="tenant-a"):
    return AuditRunSnapshot(
        audit_run_id=RUN_ID,
        tenant_id=tenant,
        template_key="store-safety",
        template_revision=1,
        template_hash="1" * 64,
        answers=(("q_fire_exit", "no"),),
        visible_question_ids=("q_fire_exit",),
        score_awarded=0,
        score_possible=10,
        score_percent=Decimal("0.00"),
        completed_by="auditor@example.com",
        completed_at=NOW,
        snapshot_hash="2" * 64,
    )


def _open():
    return open_finding(
        _run(),
        question_id="q_fire_exit",
        severity=FindingSeverity.CRITICAL,
        title="Fire exit blocked",
        description="Exit route is obstructed.",
        actor="auditor@example.com",
        opened_at=NOW,
        finding_id=FINDING_ID,
    )


def _with_action():
    return add_corrective_action(
        _open(),
        owner_subject="manager@example.com",
        description="Clear the route and mark a no-storage zone.",
        due_at=NOW + timedelta(days=1),
        actor="auditor@example.com",
        created_at=NOW + timedelta(minutes=1),
        action_id=ACTION_ID,
    )


def _with_evidence():
    return attach_evidence(
        _with_action(),
        action_id=ACTION_ID,
        evidence_ref="evidence://private/fire-exit-after",
        content_sha256="3" * 64,
        provenance={"capture": "managed-device", "source": "private-object-store"},
        actor="manager@example.com",
        attached_at=NOW + timedelta(hours=1),
        evidence_id=EVIDENCE_ID,
    )


def test_finding_pins_exact_audit_snapshot_and_visible_question():
    lifecycle = _open()
    assert lifecycle.state is FindingState.OPEN
    assert lifecycle.finding.audit_run_id == RUN_ID
    assert lifecycle.finding.audit_snapshot_hash == "2" * 64
    assert lifecycle.finding.template_revision == 1
    with pytest.raises(AuditFindingError, match="visible question"):
        open_finding(
            _run(),
            question_id="hidden_q",
            severity=FindingSeverity.HIGH,
            title="x",
            description="y",
            actor="auditor@example.com",
            opened_at=NOW,
        )


def test_action_evidence_and_verification_are_governed():
    lifecycle = _with_action()
    assert lifecycle.state is FindingState.ACTION_IN_PROGRESS
    lifecycle = _with_evidence()
    assert lifecycle.state is FindingState.READY_FOR_VERIFICATION

    with pytest.raises(AuditFindingError, match="owner cannot verify"):
        verify_corrective_action(
            lifecycle,
            action_id=ACTION_ID,
            verifier_subject="manager@example.com",
            outcome=VerificationOutcome.PASSED,
            rationale="self approval",
            verified_at=NOW + timedelta(hours=2),
        )

    closed = verify_corrective_action(
        lifecycle,
        action_id=ACTION_ID,
        verifier_subject="auditor2@example.com",
        outcome=VerificationOutcome.PASSED,
        rationale="Evidence and site state verified.",
        verified_at=NOW + timedelta(hours=2),
        verification_id=VERIFY_ID,
    )
    assert closed.state is FindingState.CLOSED
    assert lifecycle.state is FindingState.READY_FOR_VERIFICATION


def test_passed_verification_requires_evidence_and_failed_verification_reopens():
    lifecycle = _with_action()
    with pytest.raises(AuditFindingError, match="requires corrective evidence"):
        verify_corrective_action(
            lifecycle,
            action_id=ACTION_ID,
            verifier_subject="auditor2@example.com",
            outcome=VerificationOutcome.PASSED,
            rationale="looks good",
            verified_at=NOW + timedelta(hours=2),
        )

    failed = verify_corrective_action(
        lifecycle,
        action_id=ACTION_ID,
        verifier_subject="auditor2@example.com",
        outcome=VerificationOutcome.FAILED,
        rationale="Obstruction remains.",
        verified_at=NOW + timedelta(hours=2),
    )
    assert failed.state is FindingState.REOPENED


def test_closed_finding_needs_explicit_reopen_before_new_action():
    closed = verify_corrective_action(
        _with_evidence(),
        action_id=ACTION_ID,
        verifier_subject="auditor2@example.com",
        outcome=VerificationOutcome.PASSED,
        rationale="Verified.",
        verified_at=NOW + timedelta(hours=2),
        verification_id=VERIFY_ID,
    )
    with pytest.raises(AuditFindingError, match="explicitly reopened"):
        add_corrective_action(
            closed,
            owner_subject="manager@example.com",
            description="extra",
            due_at=NOW + timedelta(days=2),
            actor="auditor@example.com",
            created_at=NOW + timedelta(hours=3),
        )

    reopened = reopen_finding(
        closed,
        actor="auditor3@example.com",
        reason="Issue recurred during spot check.",
        reopened_at=NOW + timedelta(hours=4),
        reopen_id=REOPEN_ID,
    )
    assert reopened.state is FindingState.REOPENED
    next_cycle = add_corrective_action(
        reopened,
        owner_subject="manager2@example.com",
        description="Permanent barrier installed.",
        due_at=NOW + timedelta(days=3),
        actor="auditor3@example.com",
        created_at=NOW + timedelta(hours=5),
    )
    assert next_cycle.state is FindingState.ACTION_IN_PROGRESS


def test_history_is_immutable_and_receipt_changes_only_with_appended_events():
    base = _with_evidence()
    base_receipt = lifecycle_receipt(base)
    closed = verify_corrective_action(
        base,
        action_id=ACTION_ID,
        verifier_subject="auditor2@example.com",
        outcome=VerificationOutcome.PASSED,
        rationale="Verified.",
        verified_at=NOW + timedelta(hours=2),
        verification_id=VERIFY_ID,
    )
    assert lifecycle_receipt(base) == base_receipt
    assert lifecycle_receipt(closed) != base_receipt
    assert base.verifications == ()
    assert len(closed.verifications) == 1


def test_failed_verification_allows_a_new_corrective_cycle():
    failed = verify_corrective_action(
        _with_action(),
        action_id=ACTION_ID,
        verifier_subject="auditor2@example.com",
        outcome=VerificationOutcome.FAILED,
        rationale="Still blocked.",
        verified_at=NOW + timedelta(hours=2),
    )
    assert failed.state is FindingState.REOPENED
    next_cycle = add_corrective_action(
        failed,
        owner_subject="manager2@example.com",
        description="Escalated corrective plan.",
        due_at=NOW + timedelta(days=2),
        actor="auditor2@example.com",
        created_at=NOW + timedelta(hours=3),
    )
    assert next_cycle.state is FindingState.ACTION_IN_PROGRESS
