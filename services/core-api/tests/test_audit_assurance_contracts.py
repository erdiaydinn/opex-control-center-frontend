from pathlib import Path

import pytest
from pydantic import ValidationError

from app.modules.audit.schemas import (
    AuditManagerAssuranceDecision,
    AuditStandardsAssuranceDecision,
)

ROOT = Path(__file__).resolve().parents[1]


def test_manager_can_only_confirm_ai_or_auditor() -> None:
    decision = AuditManagerAssuranceDecision(
        expected_version=1,
        disposition="AUDITOR_CONFIRMED",
        reason="Field evidence supports the auditor decision.",
    )
    assert decision.disposition == "AUDITOR_CONFIRMED"

    with pytest.raises(ValidationError):
        AuditManagerAssuranceDecision(
            expected_version=1,
            disposition="STANDARD_CHANGED",
            reason="Manager must not rewrite the standard.",
        )


def test_operations_standards_has_explicit_standard_and_model_dispositions() -> None:
    standard_change = AuditStandardsAssuranceDecision(
        expected_version=2,
        disposition="STANDARD_CHANGED",
        reason="The active standard requires a governed revision.",
    )
    model_review = AuditStandardsAssuranceDecision(
        expected_version=2,
        disposition="MODEL_REVIEW_REQUIRED",
        reason="The AI rule is not calibrated for this evidence pattern.",
    )
    assert standard_change.disposition == "STANDARD_CHANGED"
    assert model_review.disposition == "MODEL_REVIEW_REQUIRED"


def test_assurance_routing_uses_existing_identity_and_notification_authorities() -> None:
    source = (ROOT / "app/modules/audit/assurance.py").read_text(encoding="utf-8")
    assert "platform_notification_outbox" in source
    assert "membership_roles" in source
    assert "r.key = 'audit_standards'" in source
    assert "audit.assurance.manager_review_required" in source
    assert "audit.assurance.operations_standards_review_required" in source
    assert "run.auditor_subject != actor_subject" in source


def test_assurance_case_migration_preserves_unassigned_fail_closed_states() -> None:
    migration = (
        ROOT / "alembic/versions/0048_audit_assurance_routing.py"
    ).read_text(encoding="utf-8")
    assert "MANAGER_UNASSIGNED" in migration
    assert "OPERATIONS_STANDARDS_UNASSIGNED" in migration
    assert "uq_audit_assurance_case_run_item" in migration
    assert "REVOKE DELETE ON TABLE audit_assurance_cases" in migration
