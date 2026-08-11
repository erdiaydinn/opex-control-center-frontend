from app.learning_quality import evaluate_learning_example


def test_quality_gate_accepts_reviewed_grounded_correction():
    result = evaluate_learning_example(
        user_message="Is this mandatory for the store?",
        model_answer="I am not sure.",
        target_answer="The reviewed procedure applies to this store and the cited source must be checked for the requested date.",
        reason="incorrect operational interpretation",
        teacher_reviewed=True,
        human_approved=True,
        evidence_ids=["evidence-1"],
        legal_claim=True,
        privacy_safe=True,
    )
    assert result.accepted
    assert result.score == 100
    assert len(result.target_sha256) == 64


def test_quality_gate_blocks_model_self_copy_without_teacher_review():
    text = "Use the approved warehouse process and verify the source before taking operational action."
    result = evaluate_learning_example(
        user_message="What should I do?",
        model_answer=text,
        target_answer=text,
        reason="low confidence",
        teacher_reviewed=False,
        human_approved=True,
    )
    assert not result.accepted
    assert "unchanged_model_answer_without_teacher_review" in result.violations


def test_quality_gate_blocks_legal_claim_without_evidence():
    result = evaluate_learning_example(
        user_message="Is this legally required?",
        model_answer="",
        target_answer="This requirement is binding for the stated date and must be followed by the operation.",
        reason="legal correction",
        teacher_reviewed=True,
        human_approved=True,
        legal_claim=True,
    )
    assert not result.accepted
    assert "legal_claim_without_evidence" in result.violations


def test_quality_gate_blocks_placeholder_and_privacy_failure():
    result = evaluate_learning_example(
        user_message="Explain the process",
        model_answer="",
        target_answer="TODO placeholder answer that will be completed with more operational details later.",
        reason="draft",
        teacher_reviewed=True,
        human_approved=True,
        privacy_safe=False,
    )
    assert not result.accepted
    assert "placeholder_target_not_allowed" in result.violations
    assert "privacy_review_required" in result.violations
