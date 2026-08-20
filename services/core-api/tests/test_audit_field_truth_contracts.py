from datetime import UTC, datetime

import pytest

from app.modules.audit.control_contracts import (
    AuditAnswerSemantics,
    AuditEvidenceContract,
    AuditQuestionControl,
)
from app.modules.audit.field_truth import (
    AuditApplicabilityEvidence,
    AuditEvidenceObservation,
    AuditScoredItem,
    evaluate_question_truth,
    score_audit_items,
)
from app.modules.audit.reporting import (
    AuditReportDistributionRequest,
    AuditReportFact,
    AuditReportFinding,
    AuditReportRecipient,
    AuditReportSnapshot,
    build_distribution_plan,
    build_report_artifact,
)


def _control(
    item_key: str,
    *,
    expected: str,
    failure: str,
    modality: str = "OBSERVATION",
    allow_na: bool = False,
    min_refs: int = 0,
    privacy_media: bool = False,
) -> AuditQuestionControl:
    return AuditQuestionControl(
        item_key=item_key,
        evidence_modalities=(modality,),
        answer_semantics=AuditAnswerSemantics(
            expected_answer=expected,
            failure_answer=failure,
            failure_condition=f"{failure} indicates the prohibited condition.",
            allow_not_applicable=allow_na,
            applicability_rule_key="store_dna.rule" if allow_na else None,
        ),
        evidence_contract=AuditEvidenceContract(
            required_modalities=(modality,),
            minimum_evidence_refs=min_refs,
            require_privacy_verified_media=privacy_media,
        ),
    )


@pytest.mark.parametrize(
    ("item_key", "expected", "failure", "answer", "decision"),
    (
        # Sanitized regression cases derived from a real field audit.
        ("front_cleanliness_risk_present", "NO", "YES", "YES", "FAIL"),
        ("facade_clean", "YES", "NO", "NO", "FAIL"),
        ("waste_overflow_present", "NO", "YES", "YES", "FAIL"),
        ("emergency_exit_accessible", "YES", "NO", "YES", "PASS"),
        ("product_on_floor", "NO", "YES", "YES", "FAIL"),
        ("mops_clean", "YES", "NO", "YES", "PASS"),
    ),
)
def test_real_field_question_polarity_is_semantic_not_textual(
    item_key: str,
    expected: str,
    failure: str,
    answer: str,
    decision: str,
) -> None:
    control = _control(item_key, expected=expected, failure=failure)
    result = evaluate_question_truth(
        control,
        answer=answer,
        observation=AuditEvidenceObservation(modalities=("OBSERVATION",)),
    )
    assert result.decision == decision


def test_missing_required_media_is_insufficient_evidence_not_na() -> None:
    control = _control(
        "freezer_frost",
        expected="NO",
        failure="YES",
        modality="VISUAL",
        min_refs=1,
        privacy_media=True,
    )
    result = evaluate_question_truth(
        control,
        answer="NO",
        observation=AuditEvidenceObservation(modalities=("VISUAL",)),
    )
    assert result.decision == "INSUFFICIENT_EVIDENCE"


def test_unproven_not_applicable_fails_closed() -> None:
    control = _control(
        "ice_machine_clean",
        expected="YES",
        failure="NO",
        allow_na=True,
    )
    result = evaluate_question_truth(
        control,
        answer="NOT_APPLICABLE",
        observation=AuditEvidenceObservation(modalities=("OBSERVATION",)),
    )
    assert result.decision == "REVIEW_REQUIRED"
    assert result.reason_code == "UNPROVEN_NOT_APPLICABLE"


def test_not_applicable_requires_positive_non_applicability_proof() -> None:
    control = _control(
        "ice_machine_clean",
        expected="YES",
        failure="NO",
        allow_na=True,
    )
    result = evaluate_question_truth(
        control,
        answer="NOT_APPLICABLE",
        observation=AuditEvidenceObservation(),
        applicability=AuditApplicabilityEvidence(
            evaluated=True,
            applies=False,
            source_refs=("store-dna:asset:ice-machine:absent",),
        ),
    )
    assert result.decision == "NOT_APPLICABLE"


def test_incomplete_audit_cannot_publish_final_score() -> None:
    score = score_audit_items(
        (
            AuditScoredItem(item_key="a", decision="PASS", max_points=1),
            AuditScoredItem(item_key="b", decision="FAIL", max_points=1),
            AuditScoredItem(
                item_key="c",
                decision="INSUFFICIENT_EVIDENCE",
                max_points=1,
            ),
        )
    )
    assert score.completion_state == "INCOMPLETE"
    assert score.provisional_score_pct == 50.0
    assert score.final_score_pct is None


def test_na_is_excluded_from_scoring_denominator() -> None:
    score = score_audit_items(
        (
            AuditScoredItem(item_key="a", decision="PASS", max_points=2),
            AuditScoredItem(item_key="b", decision="FAIL", max_points=2),
            AuditScoredItem(
                item_key="c",
                decision="NOT_APPLICABLE",
                max_points=100,
            ),
        )
    )
    assert score.completion_state == "COMPLETE"
    assert score.applicable_max_points == 4
    assert score.final_score_pct == 50.0


def _report_snapshot() -> AuditReportSnapshot:
    return AuditReportSnapshot(
        audit_run_id="run-1",
        location_id="site-alpha",
        location_display_name="Site Alpha",
        audit_title="Field Audit",
        audited_at=datetime(2026, 4, 6, 10, 0, tzinfo=UTC),
        completed_at=datetime(2026, 4, 6, 11, 0, tzinfo=UTC),
        completion_state="COMPLETE",
        final_score_pct=75.0,
        provisional_score_pct=75.0,
        pass_count=3,
        fail_count=1,
        not_applicable_count=0,
        insufficient_evidence_count=0,
        review_required_count=0,
        facts=(
            AuditReportFact(
                fact_id="score",
                label="Score",
                value="75.0",
                source_refs=("audit-score:run-1",),
            ),
        ),
        findings=(
            AuditReportFinding(
                finding_id="finding-1",
                item_key="front_cleanliness",
                title="Front area requires cleaning",
                risk_class="operational",
                priority="high",
                source_refs=("decision:event-1",),
                evidence_refs=("evidence:redacted-1",),
                privacy_verified_evidence_refs=("evidence:redacted-1",),
            ),
        ),
    )


def test_report_summary_is_grounded_in_snapshot_identity() -> None:
    artifact = build_report_artifact(
        _report_snapshot(),
        template="EXECUTIVE_SUMMARY",
        locale="en",
    )
    assert "Site Alpha" in artifact.executive_summary
    assert "Site Beta" not in artifact.executive_summary
    assert artifact.source_fact_ids == ("score",)
    assert artifact.finding_ids == ("finding-1",)


def test_report_rejects_unverified_media_reference() -> None:
    with pytest.raises(ValueError, match="privacy-verified"):
        AuditReportFinding(
            finding_id="finding-1",
            item_key="front_cleanliness",
            title="Front area requires cleaning",
            risk_class="operational",
            priority="high",
            source_refs=("decision:event-1",),
            evidence_refs=("evidence:raw-1",),
            privacy_verified_evidence_refs=(),
        )


def test_manual_email_distribution_requires_explicit_authority() -> None:
    recipient = AuditReportRecipient(
        source="MANUAL_EMAIL",
        recipient_key="ops@example.com",
        email="ops@example.com",
    )
    with pytest.raises(ValueError, match="explicit authorization"):
        AuditReportDistributionRequest(
            template="STANDARD_AUDIT",
            recipients=(recipient,),
        )

    plan = build_distribution_plan(
        AuditReportDistributionRequest(
            template="STANDARD_AUDIT",
            recipients=(recipient,),
            manual_recipient_authorized=True,
            include_evidence_thumbnails=True,
        )
    )
    assert plan.raw_media_attachment_allowed is False
    assert plan.requires_private_link_delivery is True
    assert plan.targets[0].email == "ops@example.com"
