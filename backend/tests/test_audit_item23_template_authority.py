from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from app.modules.audit.template_authority import (
    AuditQuestion,
    AuditTemplateError,
    AuditTemplateStatus,
    BranchCondition,
    BranchOperator,
    create_next_revision,
    draft_template,
    evaluate_audit,
    publish_template,
)


NOW = datetime(2026, 8, 17, 12, 0, tzinfo=timezone.utc)


def _questions(*, conditional_points: int = 5):
    return (
        AuditQuestion(
            question_id="receiving_ok",
            prompt_key="audit.receiving.ok",
            max_points=10,
            scoring=(("yes", 10), ("no", 0)),
        ),
        AuditQuestion(
            question_id="receiving_note",
            prompt_key="audit.receiving.note",
            max_points=0,
            scoring=(),
            show_when=(BranchCondition("receiving_ok", BranchOperator.EQ, "no"),),
        ),
        AuditQuestion(
            question_id="corrective_action_started",
            prompt_key="audit.receiving.corrective_started",
            max_points=conditional_points,
            scoring=(("yes", conditional_points), ("no", 0)),
            show_when=(BranchCondition("receiving_ok", BranchOperator.EQ, "no"),),
        ),
    )


def _published_v1():
    draft = draft_template(
        tenant_id="tenant-a",
        template_key="store-ops",
        revision=1,
        questions=_questions(),
        created_by="auditor-admin",
        created_at=NOW,
    )
    return publish_template(draft, actor="audit-owner", published_at=NOW)


def test_conditional_branching_changes_visible_questions_and_governed_denominator():
    template = _published_v1()
    passing = evaluate_audit(
        template,
        {"receiving_ok": "yes"},
        completed_by="auditor-1",
        completed_at=NOW,
        audit_run_id=UUID("00000000-0000-0000-0000-000000000001"),
    )
    assert passing.visible_question_ids == ("receiving_ok",)
    assert passing.score_awarded == 10
    assert passing.score_possible == 10
    assert passing.score_percent == Decimal("100.00")

    failing = evaluate_audit(
        template,
        {
            "receiving_ok": "no",
            "receiving_note": "dock was blocked",
            "corrective_action_started": "yes",
        },
        completed_by="auditor-1",
        completed_at=NOW,
        audit_run_id=UUID("00000000-0000-0000-0000-000000000002"),
    )
    assert failing.visible_question_ids == (
        "receiving_ok",
        "receiving_note",
        "corrective_action_started",
    )
    assert failing.score_awarded == 5
    assert failing.score_possible == 15
    assert failing.score_percent == Decimal("33.33")


def test_hidden_answers_and_ungoverned_scores_fail_closed():
    template = _published_v1()
    with pytest.raises(AuditTemplateError, match="hidden question"):
        evaluate_audit(
            template,
            {"receiving_ok": "yes", "corrective_action_started": "yes"},
            completed_by="auditor-1",
        )
    with pytest.raises(AuditTemplateError, match="no governed score"):
        evaluate_audit(
            template,
            {
                "receiving_ok": "no",
                "receiving_note": "blocked",
                "corrective_action_started": "maybe",
            },
            completed_by="auditor-1",
        )


def test_branch_conditions_must_reference_earlier_questions():
    invalid = (
        AuditQuestion(
            question_id="child",
            prompt_key="child",
            max_points=1,
            scoring=(("yes", 1),),
            show_when=(BranchCondition("later", BranchOperator.EQ, "yes"),),
        ),
        AuditQuestion(
            question_id="later",
            prompt_key="later",
            max_points=1,
            scoring=(("yes", 1),),
        ),
    )
    with pytest.raises(AuditTemplateError, match="earlier question"):
        draft_template(
            tenant_id="tenant-a",
            template_key="invalid",
            revision=1,
            questions=invalid,
            created_by="owner",
        )


def test_published_revision_is_frozen_and_new_revision_cannot_rewrite_history():
    v1 = _published_v1()
    historical = evaluate_audit(
        v1,
        {
            "receiving_ok": "no",
            "receiving_note": "blocked",
            "corrective_action_started": "yes",
        },
        completed_by="auditor-1",
        completed_at=NOW,
        audit_run_id=UUID("00000000-0000-0000-0000-000000000099"),
    )
    historical_hash = historical.snapshot_hash
    with pytest.raises(FrozenInstanceError):
        v1.revision = 99  # type: ignore[misc]

    v2_draft = create_next_revision(
        v1,
        actor="audit-owner",
        questions=_questions(conditional_points=10),
        created_at=NOW,
    )
    v2 = publish_template(v2_draft, actor="audit-owner", published_at=NOW)
    assert v1.status is AuditTemplateStatus.PUBLISHED
    assert v1.revision == 1
    assert v2.revision == 2
    assert v1.content_hash != v2.content_hash
    assert historical.template_revision == 1
    assert historical.template_hash == v1.content_hash
    assert historical.snapshot_hash == historical_hash
    assert historical.score_awarded == 5
    assert historical.score_possible == 15
    assert historical.score_percent == Decimal("33.33")


def test_draft_or_hash_tampering_cannot_be_used_for_audit_run():
    draft = draft_template(
        tenant_id="tenant-a",
        template_key="store-ops",
        revision=1,
        questions=_questions(),
        created_by="owner",
        created_at=NOW,
    )
    with pytest.raises(AuditTemplateError, match="published"):
        evaluate_audit(draft, {"receiving_ok": "yes"}, completed_by="auditor")

    published = publish_template(draft, actor="owner", published_at=NOW)
    from dataclasses import replace
    tampered = replace(published, content_hash="0" * 64)
    with pytest.raises(AuditTemplateError, match="content hash"):
        evaluate_audit(tampered, {"receiving_ok": "yes"}, completed_by="auditor")
